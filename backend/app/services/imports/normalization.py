import hashlib
import re
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    AccountInstrument,
    AmountBehavior,
    Direction,
    DraftTransaction,
    DuplicateStatus,
    ImportFile,
    ImportMapping,
    InstrumentType,
    ProviderCategoryMapping,
    Rule,
    Transaction,
    TransactionType,
)
from app.services.imports.parsing import (
    clean_description,
    normalize_card_identifier,
    parse_amount,
    parse_csv,
    parse_date,
)
from app.services.rules import apply_first_matching_rule


TRANSFER_WORDS = ("ach transfer", "transfer to", "transfer from", "zelle", "venmo", "paypal")
PAYMENT_WORDS = ("payment thank you", "online payment", "autopay", "credit card payment")


def normalized_amount(row: dict, mapping: ImportMapping) -> tuple[Decimal, Direction]:
    behavior = mapping.amount_behavior
    if behavior == AmountBehavior.debit_credit_columns:
        debit = parse_amount(row.get(mapping.debit_column)) if mapping.debit_column else Decimal("0")
        credit = parse_amount(row.get(mapping.credit_column)) if mapping.credit_column else Decimal("0")
        return (abs(debit), Direction.outflow) if debit else (abs(credit), Direction.inflow)
    value = parse_amount(row.get(mapping.amount_column))
    if behavior in (AmountBehavior.charges_positive, AmountBehavior.credits_negative):
        direction = Direction.outflow if value >= 0 else Direction.inflow
    else:
        direction = Direction.inflow if value >= 0 else Direction.outflow
    return abs(value), direction


def detect_type(description: str, direction: Direction) -> tuple[TransactionType, bool]:
    text = description.lower()
    if any(term in text for term in PAYMENT_WORDS):
        return TransactionType.credit_card_payment, True
    if any(term in text for term in TRANSFER_WORDS):
        return TransactionType.transfer, True
    return (TransactionType.income, False) if direction == Direction.inflow else (TransactionType.expense, False)


def recurring_candidate_for(description: str, merchant: str | None, amount: Decimal, history) -> bool:
    key = (merchant or description).strip().lower()
    matches = [
        item for item in history
        if (item.merchant_name or item.description_clean).strip().lower() == key
        and abs(Decimal(item.amount) - amount) <= max(Decimal("5"), amount * Decimal("0.25"))
        and item.transaction_type == TransactionType.expense
        and not item.is_excluded_from_spending
    ]
    return len(matches) >= 2


def make_dedupe_key(user_id, account_id, instrument_id, posted, transacted, amount, direction, description, provider_id=None):
    if provider_id:
        raw = f"{user_id}|{account_id}|provider|{provider_id}"
    else:
        normalized_description = re.sub(r"\W+", "", description.lower())
        raw = "|".join(
            map(str, [user_id, account_id, instrument_id or "", posted or "", transacted, amount, direction.value, normalized_description])
        )
    return hashlib.sha256(raw.encode()).hexdigest()


def _match_instrument(db: Session, import_file: ImportFile, source: str | None, last_four: str | None):
    if not source and not last_four:
        return None
    instruments = db.scalars(
        select(AccountInstrument).where(
            AccountInstrument.user_id == import_file.user_id,
            AccountInstrument.account_id == import_file.account_id,
        )
    ).all()
    for instrument in instruments:
        if source and instrument.source_identifier == source:
            return instrument
        if last_four and instrument.last_four == last_four:
            return instrument
    account = db.get(Account, import_file.account_id)
    kind = InstrumentType.credit_card if account.account_type.value == "credit_card" else InstrumentType.debit_card
    instrument = AccountInstrument(
        user_id=import_file.user_id,
        account_id=import_file.account_id,
        instrument_type=kind,
        display_name=f"Imported card ending {last_four}" if last_four else f"Imported profile {source}",
        last_four=last_four,
        source_identifier=source,
        is_active=False,
    )
    db.add(instrument)
    db.flush()
    return instrument


def normalize_import(db: Session, import_file: ImportFile, mapping: ImportMapping) -> int:
    with open(import_file.storage_path, "rb") as source:
        _, rows = parse_csv(source.read())
    db.query(DraftTransaction).filter(DraftTransaction.import_file_id == import_file.id).delete()
    rules = db.scalars(
        select(Rule).where(Rule.user_id == import_file.user_id, Rule.is_active.is_(True)).order_by(Rule.priority)
    ).all()
    category_mappings = {
        item.source_category.lower(): item
        for item in db.scalars(
            select(ProviderCategoryMapping).where(
                ProviderCategoryMapping.user_id == import_file.user_id,
                ProviderCategoryMapping.provider_name == mapping.provider_name,
            )
        ).all()
    }
    transaction_history = db.scalars(select(Transaction).where(Transaction.user_id == import_file.user_id)).all()
    existing = {item.dedupe_key for item in transaction_history}
    seen = set()
    duplicates = 0
    for index, row in enumerate(rows, start=1):
        date_value = row.get(mapping.date_column) if mapping.date_column else None
        posted_value = row.get(mapping.post_date_column) if mapping.post_date_column else None
        transacted = parse_date(date_value or posted_value)
        posted = parse_date(posted_value) if posted_value else None
        description = clean_description(row.get(mapping.description_column, ""))
        amount, direction = normalized_amount(row, mapping)
        raw_identifier = None
        for column in (mapping.card_last_four_column, mapping.card_number_column, mapping.account_suffix_column):
            if column and row.get(column):
                raw_identifier = row[column]
                break
        source_identifier, last_four = normalize_card_identifier(raw_identifier)
        instrument = _match_instrument(db, import_file, source_identifier, last_four)
        provider_id = row.get(mapping.transaction_id_column) if mapping.transaction_id_column else None
        dedupe = make_dedupe_key(
            import_file.user_id, import_file.account_id, instrument.id if instrument else None,
            posted, transacted, amount, direction, description, provider_id,
        )
        duplicate = dedupe in existing or dedupe in seen
        duplicates += int(duplicate)
        seen.add(dedupe)
        transaction_type, excluded = detect_type(description, direction)
        source_category = row.get(mapping.category_column) if mapping.category_column else None
        provider_mapping = category_mappings.get((source_category or "").lower())
        draft = DraftTransaction(
            user_id=import_file.user_id,
            import_file_id=import_file.id,
            account_id=import_file.account_id,
            account_instrument_id=instrument.id if instrument else None,
            row_index=index,
            raw_row_json=row,
            transaction_date=transacted,
            posted_date=posted,
            description_original=description,
            description_clean=description,
            merchant_name=row.get(mapping.merchant_column) if mapping.merchant_column else None,
            amount=amount,
            direction=direction,
            transaction_type=transaction_type,
            category_id=provider_mapping.category_id if provider_mapping else None,
            subcategory_id=provider_mapping.subcategory_id if provider_mapping else None,
            source_category=source_category,
            source_card_identifier=source_identifier,
            card_last_four=last_four,
            cardholder_name=row.get(mapping.cardholder_name_column) if mapping.cardholder_name_column else None,
            is_excluded_from_spending=excluded,
            is_recurring=False,
            recurring_candidate=False,
            duplicate_status=DuplicateStatus.duplicate if duplicate else DuplicateStatus.new,
            dedupe_key=dedupe,
            provider_transaction_id=provider_id,
            notes=row.get(mapping.notes_column) if mapping.notes_column else None,
        )
        apply_first_matching_rule(draft, rules, db)
        if draft.transaction_type == TransactionType.expense and not draft.is_excluded_from_spending:
            draft.recurring_candidate = recurring_candidate_for(
                draft.description_clean, draft.merchant_name, draft.amount, transaction_history
            )
        db.add(draft)
    import_file.row_count = len(rows)
    import_file.duplicate_row_count = duplicates
    import_file.status = "review_pending"
    db.flush()
    return len(rows)
