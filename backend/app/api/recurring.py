from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import owned_or_404
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import RecurringSeries, RecurringStatus
from app.schemas import RecurringManualIn, RecurringPatch
from app.services.recurring import suggest_recurring


router = APIRouter(prefix="/recurring", tags=["recurring"])


def series_dict(item):
    return {column.name: getattr(item, column.name) for column in item.__table__.columns}


@router.get("")
def list_recurring(status: RecurringStatus | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    query = select(RecurringSeries).where(RecurringSeries.user_id == user.id)
    if status:
        query = query.where(RecurringSeries.status == status)
    rows = db.scalars(query.order_by(RecurringSeries.expected_amount.desc())).all()
    monthly_total = sum(
        float(item.expected_amount) * {"weekly": 52 / 12, "quarterly": 1 / 3, "annual": 1 / 12}.get(item.cadence.value, 1)
        for item in rows if item.status == RecurringStatus.approved
    )
    return {"items": [series_dict(item) for item in rows], "monthly_total": round(monthly_total, 2)}


@router.get("/suggestions")
def suggestions(db: Session = Depends(get_db), user=Depends(get_current_user)):
    suggest_recurring(db, user.id)
    db.commit()
    rows = db.scalars(
        select(RecurringSeries).where(RecurringSeries.user_id == user.id, RecurringSeries.status == RecurringStatus.suggested).order_by(RecurringSeries.expected_amount.desc())
    ).all()
    return [series_dict(item) for item in rows]


@router.post("/{series_id}/approve")
def approve(series_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, RecurringSeries, series_id, user.id)
    item.status = RecurringStatus.approved
    db.commit()
    return series_dict(item)


@router.post("/{series_id}/reject")
def reject(series_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, RecurringSeries, series_id, user.id)
    item.status = RecurringStatus.rejected
    db.commit()
    return series_dict(item)


@router.patch("/{series_id}")
def update_series(series_id: UUID, payload: RecurringPatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, RecurringSeries, series_id, user.id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    return series_dict(item)


@router.post("/manual", status_code=201)
def manual(payload: RecurringManualIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = RecurringSeries(user_id=user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    return series_dict(item)
