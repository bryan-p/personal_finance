from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import owned_or_404
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Institution
from app.schemas import InstitutionIn, InstitutionOut, InstitutionPatch
from app.services.institutions import clean_institution_name, normalize_institution_name


router = APIRouter(prefix="/institutions", tags=["institutions"])


@router.get("", response_model=list[InstitutionOut])
def list_institutions(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.scalars(
        select(Institution).where(Institution.user_id == user.id).order_by(Institution.display_name)
    ).all()


@router.post("", response_model=InstitutionOut, status_code=201)
def create_institution(payload: InstitutionIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    display_name = clean_institution_name(payload.display_name)
    if not display_name:
        raise HTTPException(status_code=422, detail="Institution name cannot be blank")
    normalized_name = normalize_institution_name(display_name)
    existing = db.scalar(
        select(Institution).where(
            Institution.user_id == user.id,
            Institution.normalized_name == normalized_name,
        )
    )
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.commit()
        return existing
    item = Institution(
        user_id=user.id,
        display_name=display_name,
        normalized_name=normalized_name,
        is_system=False,
    )
    db.add(item)
    db.commit()
    return item


@router.patch("/{institution_id}", response_model=InstitutionOut)
def update_institution(
    institution_id: UUID,
    payload: InstitutionPatch,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    item = owned_or_404(db, Institution, institution_id, user.id)
    values = payload.model_dump(exclude_unset=True)
    if "display_name" in values:
        display_name = clean_institution_name(values.pop("display_name"))
        if not display_name:
            raise HTTPException(status_code=422, detail="Institution name cannot be blank")
        normalized_name = normalize_institution_name(display_name)
        duplicate = db.scalar(
            select(Institution).where(
                Institution.user_id == user.id,
                Institution.normalized_name == normalized_name,
                Institution.id != item.id,
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="An institution with that name already exists")
        item.display_name = display_name
        item.normalized_name = normalized_name
    for name, value in values.items():
        setattr(item, name, value)
    db.commit()
    return item
