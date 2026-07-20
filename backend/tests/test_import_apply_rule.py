from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.imports import router as imports_router
from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.models import (
    Account,
    AccountType,
    Category,
    Direction,
    DraftTransaction,
    ImportFile,
    ImportStatus,
    MatchField,
    MatchOperator,
    ReviewStatus,
    Rule,
    Subcategory,
    TransactionType,
    User,
)


@pytest.fixture
def import_rule_api():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    with test_session() as db:
        user = User(
            email="review@example.com",
            password_hash="test",
            display_name="Review Tester",
        )
        other_user = User(
            email="other-review@example.com",
            password_hash="test",
            display_name="Other Review Tester",
        )
        db.add_all([user, other_user])
        db.commit()
        user_id = user.id
        other_user_id = other_user.id

    app = FastAPI()
    app.include_router(imports_router)

    def override_get_db():
        with test_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            session_factory=test_session,
            user_id=user_id,
            other_user_id=other_user_id,
        )

    Base.metadata.drop_all(engine)
    engine.dispose()


def add_import(db, user_id, *, status=ImportStatus.review_pending):
    account = Account(
        user_id=user_id,
        name=f"Checking {user_id}",
        institution_id=None,
        account_type=AccountType.checking,
        last_four=None,
        currency="USD",
        statement_cycle_day=None,
        payment_due_day=None,
    )
    db.add(account)
    db.flush()
    import_file = ImportFile(
        user_id=user_id,
        account_id=account.id,
        institution_id=None,
        account_type=AccountType.checking,
        original_filename="transactions.csv",
        storage_path="/tmp/transactions.csv",
        file_hash=uuid4().hex + uuid4().hex,
        status=status,
        error_message=None,
        headers_json=[],
        sample_rows_json=[],
        proposed_mapping_json={},
    )
    db.add(import_file)
    db.flush()
    return account, import_file


def add_draft(
    db,
    *,
    user_id,
    account_id,
    import_id,
    row_index,
    description,
    review_status=ReviewStatus.pending,
    category_id=None,
    subcategory_id=None,
    notes=None,
    recurring_candidate=False,
):
    draft = DraftTransaction(
        user_id=user_id,
        account_id=account_id,
        account_instrument_id=None,
        transaction_date=date(2026, 7, 19),
        posted_date=None,
        description_original=description,
        description_clean=description,
        merchant_name=None,
        amount=Decimal("5.00"),
        direction=Direction.outflow,
        transaction_type=TransactionType.expense,
        category_id=category_id,
        subcategory_id=subcategory_id,
        source_category=None,
        source_transaction_type=None,
        source_card_identifier=None,
        card_last_four=None,
        cardholder_name=None,
        is_excluded_from_spending=False,
        is_recurring=False,
        dedupe_key=f"{row_index:064d}",
        provider_transaction_id=None,
        notes=notes,
        import_file_id=import_id,
        row_index=row_index,
        raw_row_json={},
        recurring_candidate=recurring_candidate,
        review_status=review_status,
    )
    db.add(draft)
    db.flush()
    return draft


def test_apply_rule_updates_only_matching_pending_drafts(import_rule_api):
    with import_rule_api.session_factory() as db:
        account, import_file = add_import(db, import_rule_api.user_id)
        old_category = Category(
            user_id=import_rule_api.user_id,
            name="Old category",
            is_system=False,
        )
        new_category = Category(
            user_id=import_rule_api.user_id,
            name="New category",
            is_system=False,
        )
        db.add_all([old_category, new_category])
        db.flush()
        old_subcategory = Subcategory(
            user_id=import_rule_api.user_id,
            category_id=old_category.id,
            name="Old subcategory",
            is_system=False,
        )
        db.add(old_subcategory)
        db.flush()
        rule = Rule(
            user_id=import_rule_api.user_id,
            name="Coffee transfers",
            priority=100,
            is_active=True,
            match_field=MatchField.description,
            match_operator=MatchOperator.contains,
            match_value="COFFEE",
            category_id=new_category.id,
            subcategory_id=None,
            transaction_type=TransactionType.transfer,
            is_excluded_from_spending=None,
            mark_as_recurring=True,
            merchant_name_override="Coffee Shop",
            note="Applied by rule",
        )
        db.add(rule)
        db.flush()
        pending = add_draft(
            db,
            user_id=import_rule_api.user_id,
            account_id=account.id,
            import_id=import_file.id,
            row_index=1,
            description="COFFEE SHOP",
            category_id=old_category.id,
            subcategory_id=old_subcategory.id,
            notes="Existing note",
        )
        edited = add_draft(
            db,
            user_id=import_rule_api.user_id,
            account_id=account.id,
            import_id=import_file.id,
            row_index=2,
            description="COFFEE ROASTER",
            review_status=ReviewStatus.edited,
        )
        skipped = add_draft(
            db,
            user_id=import_rule_api.user_id,
            account_id=account.id,
            import_id=import_file.id,
            row_index=3,
            description="COFFEE CART",
            review_status=ReviewStatus.skipped,
        )
        approved = add_draft(
            db,
            user_id=import_rule_api.user_id,
            account_id=account.id,
            import_id=import_file.id,
            row_index=4,
            description="COFFEE KIOSK",
            review_status=ReviewStatus.approved,
        )
        unmatched = add_draft(
            db,
            user_id=import_rule_api.user_id,
            account_id=account.id,
            import_id=import_file.id,
            row_index=5,
            description="GROCERY STORE",
        )
        db.commit()
        import_id = import_file.id
        rule_id = rule.id
        pending_id = pending.id
        edited_id = edited.id
        skipped_id = skipped.id
        approved_id = approved.id
        unmatched_id = unmatched.id
        new_category_id = new_category.id

    response = import_rule_api.client.post(
        f"/imports/{import_id}/draft-transactions/apply-rule",
        json={"rule_id": str(rule_id)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["matched"] == 4
    assert payload["updated"] == 1
    assert payload["skipped_reviewed"] == 3
    assert len(payload["drafts"]) == 1
    assert payload["drafts"][0]["id"] == str(pending_id)
    assert payload["drafts"][0]["review_status"] == ReviewStatus.pending.value
    assert payload["drafts"][0]["rule_applied"] is True

    with import_rule_api.session_factory() as db:
        saved_pending = db.get(DraftTransaction, pending_id)
        assert saved_pending.category_id == new_category_id
        assert saved_pending.subcategory_id is None
        assert saved_pending.transaction_type == TransactionType.transfer
        assert saved_pending.is_excluded_from_spending is True
        assert saved_pending.is_recurring is True
        assert saved_pending.merchant_name == "Coffee Shop"
        assert saved_pending.notes == "Existing note\nApplied by rule"
        assert saved_pending.applied_rule_id == rule_id
        assert saved_pending.review_status == ReviewStatus.pending

        untouched_statuses = {
            edited_id: ReviewStatus.edited,
            skipped_id: ReviewStatus.skipped,
            approved_id: ReviewStatus.approved,
            unmatched_id: ReviewStatus.pending,
        }
        for untouched_id, expected_status in untouched_statuses.items():
            untouched = db.get(DraftTransaction, untouched_id)
            assert untouched.category_id is None
            assert untouched.applied_rule_id is None
            assert untouched.review_status == expected_status


@pytest.mark.parametrize("target", ["import", "rule"])
def test_apply_rule_hides_other_users_resources(import_rule_api, target):
    with import_rule_api.session_factory() as db:
        _, own_import = add_import(db, import_rule_api.user_id)
        _, other_import = add_import(db, import_rule_api.other_user_id)
        own_rule = Rule(
            user_id=import_rule_api.user_id,
            name="Own rule",
            priority=100,
            is_active=True,
            match_field=MatchField.description,
            match_operator=MatchOperator.contains,
            match_value="COFFEE",
        )
        other_rule = Rule(
            user_id=import_rule_api.other_user_id,
            name="Other rule",
            priority=100,
            is_active=True,
            match_field=MatchField.description,
            match_operator=MatchOperator.contains,
            match_value="COFFEE",
        )
        db.add_all([own_rule, other_rule])
        db.commit()
        import_id = other_import.id if target == "import" else own_import.id
        rule_id = own_rule.id if target == "import" else other_rule.id

    response = import_rule_api.client.post(
        f"/imports/{import_id}/draft-transactions/apply-rule",
        json={"rule_id": str(rule_id)},
    )

    assert response.status_code == 404


def test_apply_rule_rejects_inactive_rule(import_rule_api):
    with import_rule_api.session_factory() as db:
        _, import_file = add_import(db, import_rule_api.user_id)
        rule = Rule(
            user_id=import_rule_api.user_id,
            name="Inactive rule",
            priority=100,
            is_active=False,
            match_field=MatchField.description,
            match_operator=MatchOperator.contains,
            match_value="COFFEE",
        )
        db.add(rule)
        db.commit()
        import_id = import_file.id
        rule_id = rule.id

    response = import_rule_api.client.post(
        f"/imports/{import_id}/draft-transactions/apply-rule",
        json={"rule_id": str(rule_id)},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Inactive rules cannot be applied"}


def test_apply_rule_rejects_import_not_awaiting_review(import_rule_api):
    with import_rule_api.session_factory() as db:
        _, import_file = add_import(
            db,
            import_rule_api.user_id,
            status=ImportStatus.mapped,
        )
        rule = Rule(
            user_id=import_rule_api.user_id,
            name="Coffee rule",
            priority=100,
            is_active=True,
            match_field=MatchField.description,
            match_operator=MatchOperator.contains,
            match_value="COFFEE",
        )
        db.add(rule)
        db.commit()
        import_id = import_file.id
        rule_id = rule.id

    response = import_rule_api.client.post(
        f"/imports/{import_id}/draft-transactions/apply-rule",
        json={"rule_id": str(rule_id)},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Import is not awaiting review"}


def test_apply_rule_recalculates_recurring_candidate(import_rule_api):
    with import_rule_api.session_factory() as db:
        account, import_file = add_import(db, import_rule_api.user_id)
        rule = Rule(
            user_id=import_rule_api.user_id,
            name="Coffee transfers",
            priority=100,
            is_active=True,
            match_field=MatchField.description,
            match_operator=MatchOperator.contains,
            match_value="COFFEE",
            transaction_type=TransactionType.transfer,
        )
        db.add(rule)
        db.flush()
        draft = add_draft(
            db,
            user_id=import_rule_api.user_id,
            account_id=account.id,
            import_id=import_file.id,
            row_index=1,
            description="COFFEE SHOP",
            recurring_candidate=True,
        )
        db.commit()
        import_id = import_file.id
        rule_id = rule.id
        draft_id = draft.id

    response = import_rule_api.client.post(
        f"/imports/{import_id}/draft-transactions/apply-rule",
        json={"rule_id": str(rule_id)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["drafts"][0]["id"] == str(draft_id)
    assert payload["drafts"][0]["transaction_type"] == TransactionType.transfer.value
    assert payload["drafts"][0]["is_excluded_from_spending"] is True
    assert payload["drafts"][0]["recurring_candidate"] is False

    with import_rule_api.session_factory() as db:
        saved = db.get(DraftTransaction, draft_id)
        assert saved.recurring_candidate is False
