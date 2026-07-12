from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from statistics import median

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cadence, RecurringSeries, RecurringStatus, Transaction, TransactionType


def cadence_for_days(days: float):
    if 5 <= days <= 9:
        return Cadence.weekly
    if 25 <= days <= 36:
        return Cadence.monthly
    if 75 <= days <= 105:
        return Cadence.quarterly
    if 330 <= days <= 400:
        return Cadence.annual
    return None


def next_date(last, cadence):
    if cadence == Cadence.weekly:
        return last + timedelta(days=7)
    if cadence == Cadence.monthly:
        return last + relativedelta(months=1)
    if cadence == Cadence.quarterly:
        return last + relativedelta(months=3)
    if cadence == Cadence.annual:
        return last + relativedelta(years=1)
    return None


def suggest_recurring(db: Session, user_id):
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == TransactionType.expense,
            Transaction.direction == "outflow",
            Transaction.is_excluded_from_spending.is_(False),
        ).order_by(Transaction.transaction_date)
    ).all()
    groups = defaultdict(list)
    for item in transactions:
        merchant = (item.merchant_name or item.description_clean).strip().lower()
        groups[merchant].append(item)
    existing = {
        item.merchant_name.lower(): item
        for item in db.scalars(select(RecurringSeries).where(RecurringSeries.user_id == user_id)).all()
    }
    created = []
    for merchant, items in groups.items():
        if len(items) < 3 or merchant in existing:
            continue
        intervals = [(right.transaction_date - left.transaction_date).days for left, right in zip(items, items[1:])]
        cadence = cadence_for_days(median(intervals))
        amounts = [Decimal(item.amount) for item in items]
        expected = sum(amounts) / len(amounts)
        variability = max(abs(amount - expected) for amount in amounts)
        if not cadence or variability > max(Decimal("5"), expected * Decimal("0.25")):
            continue
        series = RecurringSeries(
            user_id=user_id,
            merchant_name=items[-1].merchant_name or items[-1].description_clean,
            category_id=items[-1].category_id,
            subcategory_id=items[-1].subcategory_id,
            expected_amount=expected.quantize(Decimal("0.01")),
            amount_variability=variability.quantize(Decimal("0.01")),
            cadence=cadence,
            status=RecurringStatus.suggested,
            first_seen_date=items[0].transaction_date,
            last_seen_date=items[-1].transaction_date,
            next_expected_date=next_date(items[-1].transaction_date, cadence),
        )
        db.add(series)
        created.append(series)
    db.flush()
    return created

