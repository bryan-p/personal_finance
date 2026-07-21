import re
from decimal import Decimal, InvalidOperation

from app.services.transactions import sync_type_exclusion

try:
    import regex
except ImportError:  # pragma: no cover - production installs it from requirements.txt
    regex = None


REGEX_MATCH_TIMEOUT_SECONDS = 0.1


def validate_regex_pattern(pattern: str) -> None:
    if regex is None:
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from None
        raise ValueError(
            "Regular expression rules are unavailable because the 'regex' package is not installed"
        )
    try:
        regex.compile(pattern, regex.IGNORECASE)
    except regex.error as exc:
        raise ValueError(f"Invalid regular expression: {exc}") from None


def rule_matches(transaction, rule, db=None) -> bool:
    field = rule.match_field.value
    if field == "description":
        actual = transaction.description_original
    elif field == "memo":
        actual = transaction.memo
    elif field == "merchant":
        actual = transaction.merchant_name
    elif field == "source_category":
        actual = transaction.source_category
    elif field == "source_transaction_type":
        actual = transaction.source_transaction_type
    elif field == "source_status":
        actual = transaction.source_status
    elif field == "amount":
        actual = transaction.amount
    elif field == "direction":
        actual = transaction.direction.value
    elif field == "cardholder_name":
        actual = transaction.cardholder_name
    elif field == "card_last_four":
        actual = transaction.card_last_four
    elif field == "account" and db:
        from app.models import Account
        actual = db.get(Account, transaction.account_id).name
    elif field == "account_instrument" and db and transaction.account_instrument_id:
        from app.models import AccountInstrument
        actual = db.get(AccountInstrument, transaction.account_instrument_id).display_name
    else:
        actual = None
    if actual is None:
        return False
    operator = rule.match_operator.value
    expected = rule.match_value
    if operator in ("greater_than", "less_than"):
        try:
            left, right = Decimal(str(actual)), Decimal(expected)
        except InvalidOperation:
            return False
        return left > right if operator == "greater_than" else left < right
    left, right = str(actual).lower(), expected.lower()
    if operator == "contains":
        return right in left
    if operator == "equals":
        return left == right
    if operator == "starts_with":
        return left.startswith(right)
    if operator == "regex":
        # Never fall back to stdlib re for matching: it cannot enforce a timeout.
        if regex is None:
            return False
        try:
            return regex.search(
                expected,
                str(actual),
                regex.IGNORECASE,
                timeout=REGEX_MATCH_TIMEOUT_SECONDS,
            ) is not None
        except (regex.error, TimeoutError):
            return False
    return False


def apply_rule(transaction, rule) -> None:
    changed_fields = set()
    if rule.category_id is not None:
        if rule.category_id != transaction.category_id and rule.subcategory_id is None:
            transaction.subcategory_id = None
        transaction.category_id = rule.category_id
    if rule.subcategory_id is not None:
        transaction.subcategory_id = rule.subcategory_id
    if rule.transaction_type is not None:
        transaction.transaction_type = rule.transaction_type
        changed_fields.add("transaction_type")
    if rule.is_excluded_from_spending is not None:
        transaction.is_excluded_from_spending = rule.is_excluded_from_spending
        changed_fields.add("is_excluded_from_spending")
    sync_type_exclusion(transaction, changed_fields)
    if rule.mark_as_recurring is not None:
        transaction.is_recurring = rule.mark_as_recurring
    if rule.merchant_name_override:
        transaction.merchant_name = rule.merchant_name_override
    if rule.note:
        transaction.notes = "\n".join(filter(None, [transaction.notes, rule.note]))
    transaction.applied_rule_id = rule.id


def apply_first_matching_rule(transaction, rules, db=None):
    for rule in rules:
        if not rule_matches(transaction, rule, db):
            continue
        apply_rule(transaction, rule)
        return rule
    return None
