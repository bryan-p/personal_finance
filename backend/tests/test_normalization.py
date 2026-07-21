from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import (
    Account,
    AccountType,
    AmountBehavior,
    Direction,
    DraftTransaction,
    ImportFile,
    ImportMapping,
    Institution,
    MatchField,
    MatchOperator,
    ProviderTransactionTypeMapping,
    TransactionType,
    User,
)
from app.services.imports.normalization import (
    detect_type,
    make_dedupe_key,
    normalize_import,
    normalized_amount,
    recurring_candidate_for,
)
from app.services.rules import apply_first_matching_rule, rule_matches
from app.services.transactions import excluded_for_type, sync_type_exclusion


def mapping(**values):
    defaults = dict(amount_behavior=AmountBehavior.signed_amount, amount_column="Amount", debit_column=None, credit_column=None)
    return SimpleNamespace(**(defaults | values))


def test_signed_amount_normalization_uses_absolute_amount_and_direction():
    amount, direction = normalized_amount({"Amount": "-42.50"}, mapping())
    assert amount == Decimal("42.50")
    assert direction == Direction.outflow


def test_credit_card_positive_charge_behavior():
    amount, direction = normalized_amount({"Amount": "42.50"}, mapping(amount_behavior=AmountBehavior.charges_positive))
    assert amount == Decimal("42.50")
    assert direction == Direction.outflow


def test_debit_credit_split_columns():
    amount, direction = normalized_amount(
        {"Debit": "18.20", "Credit": ""},
        mapping(amount_behavior=AmountBehavior.debit_credit_columns, amount_column=None, debit_column="Debit", credit_column="Credit"),
    )
    assert (amount, direction) == (Decimal("18.20"), Direction.outflow)


def test_transfer_and_payment_are_excluded():
    assert detect_type("ACH Transfer to savings", Direction.outflow) == (TransactionType.transfer, True)
    assert detect_type("Payment Thank You", Direction.inflow) == (TransactionType.credit_card_payment, True)
    assert detect_type("Neighborhood market", Direction.outflow) == (TransactionType.expense, False)


def test_type_exclusion_is_recalculated_when_type_changes():
    transaction = SimpleNamespace(
        transaction_type=TransactionType.transfer,
        is_excluded_from_spending=False,
    )
    sync_type_exclusion(transaction, {"transaction_type"})
    assert transaction.is_excluded_from_spending is True

    transaction.transaction_type = TransactionType.expense
    sync_type_exclusion(transaction, {"transaction_type"})
    assert transaction.is_excluded_from_spending is False
    assert excluded_for_type(TransactionType.adjustment) is True


def test_rule_can_match_preserved_provider_transaction_type():
    transaction = SimpleNamespace(source_transaction_type="Sale")
    rule = SimpleNamespace(
        match_field=MatchField.source_transaction_type,
        match_operator=MatchOperator.equals,
        match_value="sale",
    )
    assert rule_matches(transaction, rule) is True


@pytest.mark.parametrize(
    ("match_field", "attribute", "actual", "expected"),
    [
        (MatchField.memo, "memo", "CARD PURCHASE COFFEE SHOP", "coffee shop"),
        (MatchField.source_status, "source_status", "Posted", "posted"),
    ],
)
def test_rule_can_match_preserved_memo_and_status(match_field, attribute, actual, expected):
    transaction = SimpleNamespace(**{attribute: actual})
    rule = SimpleNamespace(
        match_field=match_field,
        match_operator=MatchOperator.contains,
        match_value=expected,
    )

    assert rule_matches(transaction, rule) is True


def test_dedupe_key_uses_instrument_when_available():
    common = [uuid4(), uuid4()]
    key_a = make_dedupe_key(*common, uuid4(), None, "2026-07-01", Decimal("5"), Direction.outflow, "Coffee")
    key_b = make_dedupe_key(*common, uuid4(), None, "2026-07-01", Decimal("5"), Direction.outflow, "Coffee")
    assert key_a != key_b


def test_rule_application_has_priority_and_records_rule():
    category = uuid4()
    transaction = SimpleNamespace(
        description_original="NETFLIX.COM 123", merchant_name=None, source_category=None,
        source_transaction_type=None,
        amount=Decimal("15.49"), direction=Direction.outflow, cardholder_name=None,
        card_last_four=None, account_id=uuid4(), account_instrument_id=None,
        category_id=None, subcategory_id=None, transaction_type=TransactionType.expense,
        is_excluded_from_spending=False, is_recurring=False, notes=None, applied_rule_id=None,
    )
    rule = SimpleNamespace(
        id=uuid4(), match_field=MatchField.description, match_operator=MatchOperator.contains,
        match_value="NETFLIX", category_id=category, subcategory_id=None,
        transaction_type=None, is_excluded_from_spending=None, mark_as_recurring=True,
        merchant_name_override="Netflix", note=None,
    )
    applied = apply_first_matching_rule(transaction, [rule])
    assert applied is rule
    assert transaction.category_id == category
    assert transaction.merchant_name == "Netflix"
    assert transaction.is_recurring is True
    assert transaction.applied_rule_id == rule.id


def test_rule_category_override_clears_a_subcategory_from_another_category():
    transaction = SimpleNamespace(
        description_original="CORNER STORE",
        merchant_name=None,
        source_category="Shopping",
        source_transaction_type="Sale",
        amount=Decimal("15.49"),
        direction=Direction.outflow,
        cardholder_name=None,
        card_last_four=None,
        account_id=uuid4(),
        account_instrument_id=None,
        category_id=uuid4(),
        subcategory_id=uuid4(),
        transaction_type=TransactionType.expense,
        is_excluded_from_spending=False,
        is_recurring=False,
        notes=None,
        applied_rule_id=None,
    )
    replacement_category = uuid4()
    rule = SimpleNamespace(
        id=uuid4(),
        match_field=MatchField.description,
        match_operator=MatchOperator.contains,
        match_value="CORNER",
        category_id=replacement_category,
        subcategory_id=None,
        transaction_type=None,
        is_excluded_from_spending=None,
        mark_as_recurring=None,
        merchant_name_override=None,
        note=None,
    )

    apply_first_matching_rule(transaction, [rule])

    assert transaction.category_id == replacement_category
    assert transaction.subcategory_id is None


def test_provider_transaction_type_mapping_is_applied_during_normalization(tmp_path: Path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    csv_path = tmp_path / "provider-types.csv"
    csv_path.write_text(
        "Date,Description,Original Description,Category,Type,Status,Amount\n"
        "2026-02-25,SANDALS R US,CARD PURCHASE SANDALS R US,Shopping,Sale,Posted,-16.99\n"
    )

    with Session(engine) as db:
        user = User(email="types@example.com", password_hash="test", display_name="Types")
        db.add(user)
        db.flush()
        institution = Institution(
            user_id=user.id,
            display_name="Example Bank",
            normalized_name="example bank",
            is_system=False,
        )
        db.add(institution)
        db.flush()
        account = Account(
            user_id=user.id,
            name="Checking",
            institution_id=institution.id,
            account_type=AccountType.checking,
            currency="USD",
        )
        db.add(account)
        db.flush()
        import_file = ImportFile(
            user_id=user.id,
            account_id=account.id,
            institution_id=institution.id,
            account_type=AccountType.checking,
            original_filename=csv_path.name,
            storage_path=str(csv_path),
            file_hash="a" * 64,
            headers_json=["Date", "Description", "Original Description", "Category", "Type", "Status", "Amount"],
            sample_rows_json=[],
            proposed_mapping_json={},
        )
        mapping = ImportMapping(
            user_id=user.id,
            institution_id=institution.id,
            account_type=AccountType.checking,
            mapping_name="Provider types",
            header_signature="b" * 64,
            date_column="Date",
            description_column="Description",
            memo_column="Original Description",
            category_column="Category",
            provider_type_column="Type",
            status_column="Status",
            amount_column="Amount",
            amount_behavior=AmountBehavior.signed_amount,
        )
        type_mapping = ProviderTransactionTypeMapping(
            user_id=user.id,
            institution_id=institution.id,
            source_transaction_type="Sale",
            transaction_type=TransactionType.refund,
        )
        db.add_all([import_file, mapping, type_mapping])
        db.flush()

        assert normalize_import(db, import_file, mapping) == 1
        draft = db.scalar(select(DraftTransaction))
        assert draft is not None
        assert draft.source_category == "Shopping"
        assert draft.source_transaction_type == "Sale"
        assert draft.memo == "CARD PURCHASE SANDALS R US"
        assert draft.source_status == "Posted"
        assert draft.transaction_type == TransactionType.refund
        assert draft.is_excluded_from_spending is False


def test_recurring_candidate_requires_two_similar_prior_expenses():
    history = [
        SimpleNamespace(merchant_name="Netflix", description_clean="NETFLIX", amount=Decimal("15.49"), transaction_type=TransactionType.expense, is_excluded_from_spending=False),
        SimpleNamespace(merchant_name="Netflix", description_clean="NETFLIX", amount=Decimal("15.99"), transaction_type=TransactionType.expense, is_excluded_from_spending=False),
    ]
    assert recurring_candidate_for("NETFLIX", "Netflix", Decimal("15.49"), history) is True
