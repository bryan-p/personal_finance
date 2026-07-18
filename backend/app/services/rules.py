import re
from decimal import Decimal, InvalidOperation


def rule_matches(transaction, rule, db=None) -> bool:
    field = rule.match_field.value
    if field == "description":
        actual = transaction.description_original
    elif field == "merchant":
        actual = transaction.merchant_name
    elif field == "source_category":
        actual = transaction.source_category
    elif field == "source_transaction_type":
        actual = transaction.source_transaction_type
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
        try:
            return re.search(expected, str(actual), re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def apply_first_matching_rule(transaction, rules, db=None):
    for rule in rules:
        if not rule_matches(transaction, rule, db):
            continue
        if rule.category_id is not None:
            if rule.category_id != transaction.category_id and rule.subcategory_id is None:
                transaction.subcategory_id = None
            transaction.category_id = rule.category_id
        if rule.subcategory_id is not None:
            transaction.subcategory_id = rule.subcategory_id
        if rule.transaction_type is not None:
            transaction.transaction_type = rule.transaction_type
        if rule.is_excluded_from_spending is not None:
            transaction.is_excluded_from_spending = rule.is_excluded_from_spending
        if rule.mark_as_recurring is not None:
            transaction.is_recurring = rule.mark_as_recurring
        if rule.merchant_name_override:
            transaction.merchant_name = rule.merchant_name_override
        if rule.note:
            transaction.notes = "\n".join(filter(None, [transaction.notes, rule.note]))
        transaction.applied_rule_id = rule.id
        return rule
    return None
