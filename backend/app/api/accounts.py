from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import apply_changes, owned_or_404
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import (
    Account,
    AccountInstrument,
    DraftTransaction,
    ImportFile,
    Institution,
    RecurringSeries,
    RecurringStatus,
    Transaction,
)
from app.schemas import (
    APIMessage,
    AccountDeletionImpact,
    AccountDeletionResult,
    AccountIn,
    AccountOut,
    AccountPatch,
    InstrumentIn,
    InstrumentOut,
    InstrumentPatch,
)
from app.services.deletions import purge_uploads, restore_uploads, stage_uploads, upload_paths


router = APIRouter(tags=["accounts"])
settings = get_settings()


def account_deletion_impact(db: Session, item: Account) -> dict:
    imports = db.scalars(
        select(ImportFile).where(
            ImportFile.user_id == item.user_id,
            ImportFile.account_id == item.id,
        )
    ).all()

    def count(model) -> int:
        return db.scalar(
            select(func.count()).select_from(model).where(
                model.user_id == item.user_id,
                model.account_id == item.id,
            )
        ) or 0

    files = upload_paths([import_file.storage_path for import_file in imports], settings.upload_path)
    return {
        "account_id": item.id,
        "account_name": item.name,
        "transaction_count": count(Transaction),
        "draft_transaction_count": count(DraftTransaction),
        "instrument_count": count(AccountInstrument),
        "import_count": len(imports),
        "upload_file_count": len(files),
    }


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


@router.get("/accounts/{account_id}/deletion-impact", response_model=AccountDeletionImpact)
def get_account_deletion_impact(
    account_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    item = owned_or_404(db, Account, account_id, user.id)
    try:
        return account_deletion_impact(db, item)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/accounts/{account_id}", response_model=AccountDeletionResult)
def delete_account(account_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Account, account_id, user.id)
    imports = db.scalars(
        select(ImportFile).where(
            ImportFile.user_id == user.id,
            ImportFile.account_id == account_id,
        )
    ).all()
    try:
        impact = account_deletion_impact(db, item)
        staged_uploads = stage_uploads(
            [import_file.storage_path for import_file in imports],
            settings.upload_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Could not prepare uploaded CSV files for deletion") from exc

    try:
        db.execute(
            delete(Account).where(
                Account.id == account_id,
                Account.user_id == user.id,
            )
        )
        db.execute(
            delete(RecurringSeries).where(
                RecurringSeries.user_id == user.id,
                RecurringSeries.status == RecurringStatus.suggested,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        try:
            restore_uploads(staged_uploads)
        except OSError:
            pass
        raise

    try:
        deleted_file_count = purge_uploads(staged_uploads)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Account deleted, but one or more quarantined CSV files could not be removed",
        ) from exc
    return {**impact, "deleted_file_count": deleted_file_count}


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
