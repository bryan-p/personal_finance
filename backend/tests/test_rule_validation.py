import re
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.rules import router as rules_router
from app.api.rules import validate_rule_pattern
from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.models import (
    Account,
    AccountType,
    Direction,
    DraftTransaction,
    ImportFile,
    MatchField,
    MatchOperator,
    Rule,
    TransactionType,
    User,
)
from app.schemas import RuleIn, RulePatch
from app.services import rules as rule_service


def rule_payload(**changes):
    values = {
        "name": "Coffee shops",
        "priority": 100,
        "is_active": True,
        "match_field": MatchField.description,
        "match_operator": MatchOperator.contains,
        "match_value": "COFFEE",
    }
    return values | changes


@pytest.fixture
def rule_api():
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
            email="rules@example.com",
            password_hash="test",
            display_name="Rule Tester",
        )
        db.add(user)
        db.commit()
        user_id = user.id

    app = FastAPI()
    app.include_router(rules_router)

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
        )

    Base.metadata.drop_all(engine)
    engine.dispose()


def add_rule(rule_api, **changes):
    values = {
        "user_id": rule_api.user_id,
        "name": "Coffee shops",
        "priority": 100,
        "is_active": True,
        "match_field": MatchField.description,
        "match_operator": MatchOperator.contains,
        "match_value": "COFFEE",
    }
    with rule_api.session_factory() as db:
        rule = Rule(**(values | changes))
        db.add(rule)
        db.commit()
        return rule.id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "n" * 161),
        ("match_value", "v" * 501),
        ("merchant_name_override", "m" * 256),
    ],
)
def test_rule_create_rejects_strings_longer_than_model_columns(field, value):
    with pytest.raises(ValidationError):
        RuleIn(**rule_payload(**{field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "n" * 161),
        ("match_value", "v" * 501),
        ("merchant_name_override", "m" * 256),
    ],
)
def test_rule_patch_rejects_strings_longer_than_model_columns(field, value):
    with pytest.raises(ValidationError):
        RulePatch(**{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "name",
        "priority",
        "is_active",
        "match_field",
        "match_operator",
        "match_value",
    ],
)
def test_rule_patch_rejects_explicit_null_for_required_fields(field):
    with pytest.raises(ValidationError, match="Required rule fields cannot be null"):
        RulePatch(**{field: None})


def test_rule_patch_allows_omitted_required_fields_and_nullable_actions():
    assert RulePatch().model_fields_set == set()
    patch = RulePatch(
        category_id=None,
        subcategory_id=None,
        transaction_type=None,
        is_excluded_from_spending=None,
        mark_as_recurring=None,
        merchant_name_override=None,
        note=None,
    )
    assert patch.model_fields_set == {
        "category_id",
        "subcategory_id",
        "transaction_type",
        "is_excluded_from_spending",
        "mark_as_recurring",
        "merchant_name_override",
        "note",
    }


@pytest.mark.parametrize("priority", [-1, 2_147_483_648])
def test_rule_priority_stays_within_postgresql_integer_bounds(priority):
    with pytest.raises(ValidationError):
        RuleIn(**rule_payload(priority=priority))
    with pytest.raises(ValidationError):
        RulePatch(priority=priority)


def test_rule_write_rejects_invalid_regex_with_clear_422():
    with pytest.raises(HTTPException) as raised:
        validate_rule_pattern(MatchOperator.regex, "[unterminated")

    assert raised.value.status_code == 422
    assert "Invalid regular expression" in raised.value.detail


def test_create_rule_route_rejects_invalid_regex(rule_api):
    response = rule_api.client.post(
        "/rules",
        json=rule_payload(
            match_operator=MatchOperator.regex,
            match_value="[unterminated",
        ),
    )

    assert response.status_code == 422
    assert "Invalid regular expression" in response.json()["detail"]


@pytest.mark.parametrize(
    ("stored_operator", "stored_value", "patch"),
    [
        (
            MatchOperator.contains,
            "[unterminated",
            {"match_operator": MatchOperator.regex.value},
        ),
        (
            MatchOperator.regex,
            "COFFEE",
            {"match_value": "[unterminated"},
        ),
    ],
)
def test_patch_rule_route_validates_merged_regex_fields(
    rule_api,
    stored_operator,
    stored_value,
    patch,
):
    rule_id = add_rule(
        rule_api,
        match_operator=stored_operator,
        match_value=stored_value,
    )

    response = rule_api.client.patch(f"/rules/{rule_id}", json=patch)

    assert response.status_code == 422
    assert "Invalid regular expression" in response.json()["detail"]


def test_delete_rule_route_clears_draft_reference(rule_api):
    with rule_api.session_factory() as db:
        account = Account(
            user_id=rule_api.user_id,
            name="Checking",
            institution_id=None,
            account_type=AccountType.checking,
            last_four=None,
            currency="USD",
            statement_cycle_day=None,
            payment_due_day=None,
        )
        rule = Rule(
            user_id=rule_api.user_id,
            name="Coffee shops",
            priority=100,
            is_active=True,
            match_field=MatchField.description,
            match_operator=MatchOperator.contains,
            match_value="COFFEE",
        )
        db.add_all([account, rule])
        db.flush()
        import_file = ImportFile(
            user_id=rule_api.user_id,
            account_id=account.id,
            institution_id=None,
            account_type=AccountType.checking,
            original_filename="transactions.csv",
            storage_path="/tmp/transactions.csv",
            file_hash="a" * 64,
            error_message=None,
            headers_json=[],
            sample_rows_json=[],
            proposed_mapping_json={},
        )
        db.add(import_file)
        db.flush()
        draft = DraftTransaction(
            user_id=rule_api.user_id,
            account_id=account.id,
            account_instrument_id=None,
            transaction_date=date(2026, 7, 19),
            posted_date=None,
            description_original="COFFEE SHOP",
            description_clean="COFFEE SHOP",
            merchant_name=None,
            amount=Decimal("5.00"),
            direction=Direction.outflow,
            transaction_type=TransactionType.expense,
            category_id=None,
            subcategory_id=None,
            source_category=None,
            source_transaction_type=None,
            source_card_identifier=None,
            card_last_four=None,
            cardholder_name=None,
            is_excluded_from_spending=False,
            is_recurring=False,
            dedupe_key="b" * 64,
            provider_transaction_id=None,
            notes=None,
            import_file_id=import_file.id,
            row_index=1,
            raw_row_json={},
            recurring_candidate=False,
            applied_rule_id=rule.id,
        )
        db.add(draft)
        db.commit()
        rule_id = rule.id
        draft_id = draft.id

    response = rule_api.client.delete(f"/rules/{rule_id}")

    assert response.status_code == 200
    assert response.json() == {"message": "Rule deleted"}
    with rule_api.session_factory() as db:
        assert db.get(Rule, rule_id) is None
        assert db.get(DraftTransaction, draft_id).applied_rule_id is None


def test_list_rules_route_serializes_legacy_blank_name(rule_api):
    rule_id = add_rule(rule_api, name="")

    response = rule_api.client.get("/rules")

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(rule_id)
    assert response.json()[0]["name"] == ""


@pytest.mark.parametrize("failure", [TimeoutError("timed out"), re.error("invalid")])
def test_regex_timeout_or_match_error_is_treated_as_non_matching(monkeypatch, failure):
    calls = {}

    def fail_search(pattern, value, flags, *, timeout):
        calls.update(pattern=pattern, value=value, flags=flags, timeout=timeout)
        raise failure

    fake_regex = SimpleNamespace(
        IGNORECASE=re.IGNORECASE,
        error=re.error,
        search=fail_search,
    )
    monkeypatch.setattr(rule_service, "regex", fake_regex)
    transaction = SimpleNamespace(description_original="a" * 10_000)
    rule = SimpleNamespace(
        match_field=MatchField.description,
        match_operator=MatchOperator.regex,
        match_value="(a+)+$",
    )

    assert rule_service.rule_matches(transaction, rule) is False
    assert calls["timeout"] == rule_service.REGEX_MATCH_TIMEOUT_SECONDS


def test_real_regex_timeout_is_treated_as_non_matching(monkeypatch):
    assert rule_service.regex is not None
    timeout = 0.000001
    value = "a" * 10_000 + "!"
    pattern = "(a+)+$"
    with pytest.raises(TimeoutError):
        rule_service.regex.search(pattern, value, timeout=timeout)

    monkeypatch.setattr(rule_service, "REGEX_MATCH_TIMEOUT_SECONDS", timeout)
    transaction = SimpleNamespace(description_original=value)
    rule = SimpleNamespace(
        match_field=MatchField.description,
        match_operator=MatchOperator.regex,
        match_value=pattern,
    )

    assert rule_service.rule_matches(transaction, rule) is False
