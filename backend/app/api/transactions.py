import csv
import io
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import apply_changes, owned_or_404
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Transaction, TransactionType
from app.schemas import BulkTransactionPatch, TransactionPatch


router = APIRouter(prefix="/transactions", tags=["transactions"])


def transaction_query(user_id, start_date=None, end_date=None, account_id=None, instrument_id=None, category_id=None, subcategory_id=None, transaction_type=None, search=None):
    query = select(Transaction).where(Transaction.user_id == user_id)
    if start_date:
        query = query.where(Transaction.transaction_date >= start_date)
    if end_date:
        query = query.where(Transaction.transaction_date <= end_date)
    if account_id:
        query = query.where(Transaction.account_id == account_id)
    if instrument_id:
        query = query.where(Transaction.account_instrument_id == instrument_id)
    if category_id:
        query = query.where(Transaction.category_id == category_id)
    if subcategory_id:
        query = query.where(Transaction.subcategory_id == subcategory_id)
    if transaction_type:
        query = query.where(Transaction.transaction_type == transaction_type)
    if search:
        query = query.where(or_(Transaction.description_clean.ilike(f"%{search}%"), Transaction.merchant_name.ilike(f"%{search}%")))
    return query


def as_dict(item):
    return {column.name: getattr(item, column.name) for column in item.__table__.columns}


@router.get("")
def list_transactions(
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: UUID | None = None,
    account_instrument_id: UUID | None = None,
    category_id: UUID | None = None,
    subcategory_id: UUID | None = None,
    transaction_type: TransactionType | None = None,
    search: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = transaction_query(user.id, start_date, end_date, account_id, account_instrument_id, category_id, subcategory_id, transaction_type, search)
    rows = db.scalars(query.order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc()).limit(limit).offset(offset)).all()
    return [as_dict(item) for item in rows]


@router.get("/export")
def export_transactions(
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: UUID | None = None,
    account_instrument_id: UUID | None = None,
    category_id: UUID | None = None,
    subcategory_id: UUID | None = None,
    transaction_type: TransactionType | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = db.scalars(transaction_query(user.id, start_date, end_date, account_id, account_instrument_id, category_id, subcategory_id, transaction_type, search).order_by(Transaction.transaction_date)).all()
    output = io.StringIO()
    fields = [
        "transaction_date", "posted_date", "description", "merchant", "amount", "direction",
        "transaction_type", "account_id", "account_instrument_id", "category_id", "subcategory_id",
        "source_category", "card_last_four", "cardholder_name", "excluded_from_spending", "is_recurring", "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in rows:
        writer.writerow({
            "transaction_date": item.transaction_date,
            "posted_date": item.posted_date or "",
            "description": item.description_clean,
            "merchant": item.merchant_name or "",
            "amount": item.amount,
            "direction": item.direction.value,
            "transaction_type": item.transaction_type.value,
            "account_id": item.account_id,
            "account_instrument_id": item.account_instrument_id or "",
            "category_id": item.category_id or "",
            "subcategory_id": item.subcategory_id or "",
            "source_category": item.source_category or "",
            "card_last_four": item.card_last_four or "",
            "cardholder_name": item.cardholder_name or "",
            "excluded_from_spending": item.is_excluded_from_spending,
            "is_recurring": item.is_recurring,
            "notes": item.notes or "",
        })
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )


@router.get("/{transaction_id}")
def get_transaction(transaction_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return as_dict(owned_or_404(db, Transaction, transaction_id, user.id))


@router.patch("/{transaction_id}")
def update_transaction(transaction_id: UUID, payload: TransactionPatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Transaction, transaction_id, user.id)
    apply_changes(item, payload)
    if item.transaction_type.value in ("transfer", "credit_card_payment", "adjustment"):
        item.is_excluded_from_spending = True
    db.commit()
    return as_dict(item)


@router.post("/bulk-update")
def bulk_update(payload: BulkTransactionPatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.scalars(select(Transaction).where(Transaction.user_id == user.id, Transaction.id.in_(payload.ids))).all()
    for item in rows:
        apply_changes(item, payload.changes)
    db.commit()
    return {"updated": len(rows)}

