from app.models import TransactionType


AUTO_EXCLUDED_TYPES = {
    TransactionType.transfer,
    TransactionType.credit_card_payment,
    TransactionType.adjustment,
}


def excluded_for_type(transaction_type: TransactionType) -> bool:
    return transaction_type in AUTO_EXCLUDED_TYPES


def sync_type_exclusion(transaction, changed_fields: set[str]) -> None:
    if "transaction_type" in changed_fields and "is_excluded_from_spending" not in changed_fields:
        transaction.is_excluded_from_spending = excluded_for_type(transaction.transaction_type)
