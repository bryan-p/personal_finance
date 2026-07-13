from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apply_changes, owned_or_404
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Account, AccountInstrument, Institution
from app.schemas import (
    APIMessage,
    AccountIn,
    AccountOut,
    AccountPatch,
    InstrumentIn,
    InstrumentOut,
    InstrumentPatch,
)


router = APIRouter(tags=["accounts"])


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.scalars(select(Account).where(Account.user_id == user.id).order_by(Account.name)).all()


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(payload: AccountIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    institution = None
    if payload.institution_id:
        institution = owned_or_404(db, Institution, payload.institution_id, user.id)
    item = Account(user_id=user.id, **payload.model_dump())
    item.institution = institution
    db.add(item)
    db.commit()
    return item


@router.get("/accounts/{account_id}", response_model=AccountOut)
def get_account(account_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return owned_or_404(db, Account, account_id, user.id)


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def update_account(account_id: UUID, payload: AccountPatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Account, account_id, user.id)
    if "institution_id" in payload.model_fields_set:
        item.institution = (
            owned_or_404(db, Institution, payload.institution_id, user.id)
            if payload.institution_id
            else None
        )
    apply_changes(item, payload)
    db.commit()
    return item


@router.delete("/accounts/{account_id}", response_model=APIMessage)
def disable_account(account_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Account, account_id, user.id)
    item.is_active = False
    db.commit()
    return {"message": "Account disabled"}


@router.get("/accounts/{account_id}/instruments", response_model=list[InstrumentOut])
def list_instruments(account_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    owned_or_404(db, Account, account_id, user.id)
    return db.scalars(
        select(AccountInstrument).where(
            AccountInstrument.user_id == user.id, AccountInstrument.account_id == account_id
        ).order_by(AccountInstrument.display_name)
    ).all()


@router.post("/accounts/{account_id}/instruments", response_model=InstrumentOut, status_code=201)
def create_instrument(account_id: UUID, payload: InstrumentIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    owned_or_404(db, Account, account_id, user.id)
    item = AccountInstrument(user_id=user.id, account_id=account_id, **payload.model_dump())
    db.add(item)
    db.commit()
    return item


@router.get("/account-instruments/{instrument_id}", response_model=InstrumentOut)
def get_instrument(instrument_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return owned_or_404(db, AccountInstrument, instrument_id, user.id)


@router.patch("/account-instruments/{instrument_id}", response_model=InstrumentOut)
def update_instrument(instrument_id: UUID, payload: InstrumentPatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, AccountInstrument, instrument_id, user.id)
    apply_changes(item, payload)
    db.commit()
    return item


@router.delete("/account-instruments/{instrument_id}", response_model=APIMessage)
def disable_instrument(instrument_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, AccountInstrument, instrument_id, user.id)
    item.is_active = False
    db.commit()
    return {"message": "Account instrument disabled"}
