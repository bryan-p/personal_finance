from datetime import date
from decimal import Decimal
from uuid import UUID

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Account, AccountInstrument, Category, DraftTransaction, ImportStatus, ImportFile, Transaction, TransactionType
from app.services.dashboard import summary_payload


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def bounds(start_date: date | None, end_date: date | None):
    today = date.today()
    start = start_date or today.replace(day=1)
    end = end_date or (start + relativedelta(months=1) - relativedelta(days=1))
    return start, end


def scoped(user_id, start, end, account_id=None, instrument_id=None, category_id=None, subcategory_id=None):
    clauses = [Transaction.user_id == user_id, Transaction.transaction_date.between(start, end)]
    if account_id:
        clauses.append(Transaction.account_id == account_id)
    if instrument_id:
        clauses.append(Transaction.account_instrument_id == instrument_id)
    if category_id:
        clauses.append(Transaction.category_id == category_id)
    if subcategory_id:
        clauses.append(Transaction.subcategory_id == subcategory_id)
    return clauses


@router.get("/summary")
def summary(
    start_date: date | None = None, end_date: date | None = None, account_id: UUID | None = None,
    account_instrument_id: UUID | None = None, category_id: UUID | None = None, subcategory_id: UUID | None = None,
    db: Session = Depends(get_db), user=Depends(get_current_user),
):
    start, end = bounds(start_date, end_date)
    clauses = scoped(user.id, start, end, account_id, account_instrument_id, category_id, subcategory_id)
    spending = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        *clauses, Transaction.transaction_type == TransactionType.expense,
        Transaction.direction == "outflow", Transaction.is_excluded_from_spending.is_(False)
    ))
    income = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        *clauses, Transaction.transaction_type == TransactionType.income,
        Transaction.direction == "inflow", Transaction.is_excluded_from_spending.is_(False)
    ))
    recurring = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        *clauses, Transaction.transaction_type == TransactionType.expense,
        Transaction.direction == "outflow", Transaction.is_recurring.is_(True),
        Transaction.is_excluded_from_spending.is_(False)
    ))
    uncategorized = db.scalar(select(func.count()).select_from(Transaction).where(*clauses, Transaction.category_id.is_(None)))
    review_needed = db.scalar(select(func.count()).select_from(DraftTransaction).join(ImportFile).where(
        DraftTransaction.user_id == user.id,
        DraftTransaction.review_status == "pending",
        ImportFile.status == ImportStatus.review_pending,
    ))
    return summary_payload(start, end, spending, income, recurring, uncategorized, review_needed)


@router.get("/category-breakdown")
def category_breakdown(start_date: date | None = None, end_date: date | None = None, account_id: UUID | None = None, account_instrument_id: UUID | None = None, category_id: UUID | None = None, subcategory_id: UUID | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    start, end = bounds(start_date, end_date)
    rows = db.execute(
        select(func.coalesce(Category.name, "Uncategorized"), func.sum(Transaction.amount))
        .select_from(Transaction).outerjoin(Category)
        .where(*scoped(user.id, start, end, account_id, account_instrument_id, category_id, subcategory_id), Transaction.transaction_type == "expense", Transaction.direction == "outflow", Transaction.is_excluded_from_spending.is_(False))
        .group_by(Category.name).order_by(func.sum(Transaction.amount).desc())
    ).all()
    return [{"category": name, "amount": amount} for name, amount in rows]


@router.get("/monthly-trends")
def monthly_trends(months: int = 12, account_id: UUID | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    start = date.today().replace(day=1) - relativedelta(months=max(1, min(months, 36)) - 1)
    month = func.date_trunc("month", Transaction.transaction_date)
    clauses = [Transaction.user_id == user.id, Transaction.transaction_date >= start]
    if account_id:
        clauses.append(Transaction.account_id == account_id)
    rows = db.execute(
        select(
            month,
            func.sum(case((Transaction.transaction_type == "income", Transaction.amount), else_=0)),
            func.sum(case(((Transaction.transaction_type == "expense") & (Transaction.is_excluded_from_spending.is_(False)), Transaction.amount), else_=0)),
        ).where(*clauses).group_by(month).order_by(month)
    ).all()
    return [{"month": period.date(), "income": income, "spending": spending} for period, income, spending in rows]


@router.get("/recurring")
def recurring_dashboard(start_date: date | None = None, end_date: date | None = None, account_id: UUID | None = None, account_instrument_id: UUID | None = None, category_id: UUID | None = None, subcategory_id: UUID | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    start, end = bounds(start_date, end_date)
    merchant = func.coalesce(Transaction.merchant_name, Transaction.description_clean)
    rows = db.execute(
        select(merchant, func.sum(Transaction.amount)).where(
            *scoped(user.id, start, end, account_id, account_instrument_id, category_id, subcategory_id), Transaction.is_recurring.is_(True),
            Transaction.transaction_type == "expense", Transaction.is_excluded_from_spending.is_(False)
        ).group_by(merchant).order_by(func.sum(Transaction.amount).desc())
    ).all()
    return [{"merchant": name, "amount": amount} for name, amount in rows]


@router.get("/account-summary")
def account_summary(start_date: date | None = None, end_date: date | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    start, end = bounds(start_date, end_date)
    rows = db.execute(
        select(Account.id, Account.name, func.sum(Transaction.amount)).join(Transaction).where(
            *scoped(user.id, start, end), Transaction.transaction_type == "expense", Transaction.is_excluded_from_spending.is_(False)
        ).group_by(Account.id, Account.name).order_by(func.sum(Transaction.amount).desc())
    ).all()
    return [{"account_id": account_id, "account": name, "amount": amount} for account_id, name, amount in rows]


@router.get("/instrument-summary")
def instrument_summary(account_id: UUID, start_date: date | None = None, end_date: date | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    start, end = bounds(start_date, end_date)
    label = func.coalesce(AccountInstrument.display_name, "Parent account / unassigned")
    rows = db.execute(
        select(AccountInstrument.id, label, func.sum(Transaction.amount)).select_from(Transaction)
        .outerjoin(AccountInstrument, Transaction.account_instrument_id == AccountInstrument.id)
        .where(
            *scoped(user.id, start, end, account_id), Transaction.transaction_type == "expense",
            Transaction.direction == "outflow", Transaction.is_excluded_from_spending.is_(False)
        ).group_by(AccountInstrument.id, label).order_by(func.sum(Transaction.amount).desc())
    ).all()
    return [{"instrument_id": instrument_id, "instrument": name, "amount": amount} for instrument_id, name, amount in rows]
