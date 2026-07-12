from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.models import AmountBehavior, Direction, MatchField, MatchOperator, TransactionType
from app.services.imports.normalization import detect_type, make_dedupe_key, normalized_amount, recurring_candidate_for
from app.services.rules import apply_first_matching_rule


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


def test_dedupe_key_uses_instrument_when_available():
    common = [uuid4(), uuid4()]
    key_a = make_dedupe_key(*common, uuid4(), None, "2026-07-01", Decimal("5"), Direction.outflow, "Coffee")
    key_b = make_dedupe_key(*common, uuid4(), None, "2026-07-01", Decimal("5"), Direction.outflow, "Coffee")
    assert key_a != key_b


def test_rule_application_has_priority_and_records_rule():
    category = uuid4()
    transaction = SimpleNamespace(
        description_original="NETFLIX.COM 123", merchant_name=None, source_category=None,
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


def test_recurring_candidate_requires_two_similar_prior_expenses():
    history = [
        SimpleNamespace(merchant_name="Netflix", description_clean="NETFLIX", amount=Decimal("15.49"), transaction_type=TransactionType.expense, is_excluded_from_spending=False),
        SimpleNamespace(merchant_name="Netflix", description_clean="NETFLIX", amount=Decimal("15.99"), transaction_type=TransactionType.expense, is_excluded_from_spending=False),
    ]
    assert recurring_candidate_for("NETFLIX", "Netflix", Decimal("15.49"), history) is True
