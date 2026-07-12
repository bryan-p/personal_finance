from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apply_changes, owned_or_404
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import (
    Account,
    DraftTransaction,
    ImportFile,
    ImportMapping,
    ImportStatus,
    ReviewStatus,
    Transaction,
)
from app.schemas import APIMessage, BulkDraftPatch, DraftPatch, MappingIn, MappingOut, MappingPatch
from app.services.imports.normalization import normalize_import
from app.services.imports.parsing import (
    detect_mapping,
    detect_provider,
    file_hash,
    header_signature,
    parse_csv,
)


router = APIRouter(tags=["imports"])
settings = get_settings()


def import_summary(item: ImportFile):
    return {
        "id": item.id,
        "account_id": item.account_id,
        "provider_name": item.provider_name,
        "account_type": item.account_type,
        "original_filename": item.original_filename,
        "file_hash": item.file_hash,
        "status": item.status,
        "row_count": item.row_count,
        "duplicate_row_count": item.duplicate_row_count,
        "imported_row_count": item.imported_row_count,
        "is_duplicate_file": item.is_duplicate_file,
        "error_message": item.error_message,
        "uploaded_at": item.uploaded_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.post("/imports/upload", status_code=201)
async def upload_import(
    account_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    account = owned_or_404(db, Account, account_id, user.id)
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb} MB")
    if not file.filename or not file.filename.lower().endswith((".csv", ".txt")):
        raise HTTPException(status_code=400, detail="Upload a CSV file")
    try:
        headers, rows = parse_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    digest = file_hash(content)
    prior = db.scalar(
        select(ImportFile).where(
            ImportFile.user_id == user.id,
            ImportFile.file_hash == digest,
            ImportFile.status != ImportStatus.cancelled,
        ).order_by(ImportFile.created_at.desc())
    )
    signature = header_signature(headers)
    saved = db.scalar(
        select(ImportMapping).where(
            ImportMapping.user_id == user.id, ImportMapping.header_signature == signature
        ).order_by(ImportMapping.updated_at.desc())
    )
    detected_provider, provider_confidence = detect_provider(headers)
    proposed = (
        {name: getattr(saved, name) for name in MappingIn.model_fields if hasattr(saved, name)}
        if saved
        else detect_mapping(headers, rows[:10])
    )
    provider = saved.provider_name if saved else detected_provider or account.provider_name
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    item = ImportFile(
        user_id=user.id,
        account_id=account.id,
        provider_name=provider,
        account_type=account.account_type,
        original_filename=Path(file.filename).name,
        storage_path="",
        file_hash=digest,
        status=ImportStatus.uploaded,
        row_count=len(rows),
        headers_json=headers,
        sample_rows_json=rows[:10],
        proposed_mapping_json=proposed,
        is_duplicate_file=prior is not None,
    )
    db.add(item)
    db.flush()
    path = settings.upload_path / f"{item.id}.csv"
    path.write_bytes(content)
    item.storage_path = str(path)
    db.commit()
    return {
        **import_summary(item),
        "headers": headers,
        "sample_rows": rows[:10],
        "header_signature": signature,
        "proposed_mapping": proposed,
        "provider_detection": {
            "provider_name": detected_provider,
            "confidence": provider_confidence,
            "saved_mapping_id": saved.id if saved else None,
        },
        "duplicate_of_import_id": prior.id if prior else None,
    }


@router.get("/imports")
def list_imports(db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = db.scalars(
        select(ImportFile).where(ImportFile.user_id == user.id).order_by(ImportFile.created_at.desc())
    ).all()
    return [import_summary(item) for item in items]


@router.get("/imports/{import_id}")
def get_import(import_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, ImportFile, import_id, user.id)
    return {
        **import_summary(item),
        "headers": item.headers_json,
        "sample_rows": item.sample_rows_json,
        "proposed_mapping": item.proposed_mapping_json,
        "header_signature": header_signature(item.headers_json),
    }


@router.get("/imports/{import_id}/preview")
def preview_import(import_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, ImportFile, import_id, user.id)
    return {"headers": item.headers_json, "sample_rows": item.sample_rows_json, "proposed_mapping": item.proposed_mapping_json}


@router.post("/imports/{import_id}/mapping", response_model=MappingOut)
def save_import_mapping(import_id: UUID, payload: MappingIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, ImportFile, import_id, user.id)
    values = payload.model_dump()
    values["header_signature"] = header_signature(item.headers_json)
    mapping = ImportMapping(user_id=user.id, **values)
    db.add(mapping)
    item.provider_name = mapping.provider_name
    item.account_type = mapping.account_type
    item.status = ImportStatus.mapped
    db.commit()
    return mapping


@router.post("/imports/{import_id}/normalize")
def normalize(
    import_id: UUID,
    mapping_id: UUID,
    force_duplicate_file: bool = Query(False),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    item = owned_or_404(db, ImportFile, import_id, user.id)
    mapping = owned_or_404(db, ImportMapping, mapping_id, user.id)
    if item.is_duplicate_file and not force_duplicate_file:
        raise HTTPException(status_code=409, detail="This file was already uploaded. Confirm to continue anyway.")
    try:
        count = normalize_import(db, item, mapping)
        db.commit()
    except ValueError as exc:
        db.rollback()
        item = owned_or_404(db, ImportFile, import_id, user.id)
        item.status = ImportStatus.failed
        item.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"import_id": item.id, "status": item.status, "draft_count": count, "duplicate_count": item.duplicate_row_count}


def draft_dict(item: DraftTransaction):
    return {column.name: getattr(item, column.name) for column in item.__table__.columns if column.name != "raw_row_json"} | {"rule_applied": item.applied_rule_id is not None}


@router.get("/imports/{import_id}/review")
def review_import(
    import_id: UUID,
    instrument_id: UUID | None = None,
    duplicate_status: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    owned_or_404(db, ImportFile, import_id, user.id)
    query = select(DraftTransaction).where(DraftTransaction.user_id == user.id, DraftTransaction.import_file_id == import_id)
    if instrument_id:
        query = query.where(DraftTransaction.account_instrument_id == instrument_id)
    if duplicate_status:
        query = query.where(DraftTransaction.duplicate_status == duplicate_status)
    rows = db.scalars(query.order_by(DraftTransaction.row_index)).all()
    return [draft_dict(row) for row in rows]


@router.patch("/imports/{import_id}/draft-transactions/{draft_transaction_id}")
def update_draft(import_id: UUID, draft_transaction_id: UUID, payload: DraftPatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    owned_or_404(db, ImportFile, import_id, user.id)
    item = owned_or_404(db, DraftTransaction, draft_transaction_id, user.id)
    if item.import_file_id != import_id:
        raise HTTPException(status_code=404, detail="Draft transaction not found in this import")
    apply_changes(item, payload)
    if "review_status" not in payload.model_fields_set:
        item.review_status = ReviewStatus.edited
    if item.transaction_type.value in ("transfer", "credit_card_payment", "adjustment"):
        item.is_excluded_from_spending = True
    db.commit()
    return draft_dict(item)


@router.post("/imports/{import_id}/bulk-update")
def bulk_update_drafts(import_id: UUID, payload: BulkDraftPatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    owned_or_404(db, ImportFile, import_id, user.id)
    rows = db.scalars(
        select(DraftTransaction).where(
            DraftTransaction.user_id == user.id,
            DraftTransaction.import_file_id == import_id,
            DraftTransaction.id.in_(payload.ids),
        )
    ).all()
    for item in rows:
        apply_changes(item, payload.changes)
        item.review_status = payload.changes.review_status or ReviewStatus.edited
    db.commit()
    return {"updated": len(rows)}


@router.post("/imports/{import_id}/confirm")
def confirm_import(import_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, ImportFile, import_id, user.id)
    if item.status != ImportStatus.review_pending:
        raise HTTPException(status_code=409, detail="Import is not ready for confirmation")
    drafts = db.scalars(
        select(DraftTransaction).where(
            DraftTransaction.import_file_id == import_id,
            DraftTransaction.user_id == user.id,
            DraftTransaction.review_status != ReviewStatus.skipped,
        )
    ).all()
    imported = 0
    for draft in drafts:
        if draft.duplicate_status.value == "duplicate" and draft.review_status != ReviewStatus.approved:
            continue
        values = {
            column.name: getattr(draft, column.name)
            for column in Transaction.__table__.columns
            if column.name not in {"id", "created_at", "updated_at", "recurring_series_id"}
            and hasattr(draft, column.name)
        }
        db.add(Transaction(**values))
        imported += 1
    item.imported_row_count = imported
    item.status = ImportStatus.confirmed
    db.commit()
    return {"import_id": item.id, "status": item.status, "imported_count": imported}


@router.post("/imports/{import_id}/cancel", response_model=APIMessage)
def cancel_import(import_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, ImportFile, import_id, user.id)
    if item.status == ImportStatus.confirmed:
        raise HTTPException(status_code=409, detail="A confirmed import cannot be cancelled")
    item.status = ImportStatus.cancelled
    db.commit()
    return {"message": "Import cancelled"}


@router.get("/mappings", response_model=list[MappingOut])
def list_mappings(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.scalars(select(ImportMapping).where(ImportMapping.user_id == user.id).order_by(ImportMapping.updated_at.desc())).all()


@router.post("/mappings", response_model=MappingOut, status_code=201)
def create_mapping(payload: MappingIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not payload.header_signature:
        raise HTTPException(status_code=422, detail="header_signature is required")
    item = ImportMapping(user_id=user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    return item


@router.patch("/mappings/{mapping_id}", response_model=MappingOut)
def update_mapping(mapping_id: UUID, payload: MappingPatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, ImportMapping, mapping_id, user.id)
    apply_changes(item, payload)
    db.commit()
    return item


@router.delete("/mappings/{mapping_id}", response_model=APIMessage)
def delete_mapping(mapping_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, ImportMapping, mapping_id, user.id)
    db.delete(item)
    db.commit()
    return {"message": "Mapping deleted"}

