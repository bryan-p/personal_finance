from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import apply_changes, owned_or_404
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Category, Institution, ProviderCategoryMapping, Subcategory
from app.schemas import (
    APIMessage,
    CategoryIn,
    CategoryOut,
    CategoryPatch,
    ProviderCategoryMappingIn,
    ProviderCategoryMappingOut,
    SubcategoryIn,
    SubcategoryOut,
)


router = APIRouter(tags=["categories"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.scalars(
        select(Category).options(selectinload(Category.subcategories)).where(Category.user_id == user.id).order_by(Category.sort_order, Category.name)
    ).all()


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(payload: CategoryIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = Category(user_id=user.id, is_system=False, **payload.model_dump())
    db.add(item)
    db.commit()
    return item


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: UUID, payload: CategoryPatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Category, category_id, user.id)
    apply_changes(item, payload)
    db.commit()
    return item


@router.delete("/categories/{category_id}", response_model=APIMessage)
def disable_category(category_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Category, category_id, user.id)
    item.is_active = False
    db.commit()
    return {"message": "Category disabled"}


@router.post("/subcategories", response_model=SubcategoryOut, status_code=201)
def create_subcategory(payload: SubcategoryIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    owned_or_404(db, Category, payload.category_id, user.id)
    item = Subcategory(user_id=user.id, is_system=False, **payload.model_dump())
    db.add(item)
    db.commit()
    return item


@router.patch("/subcategories/{subcategory_id}", response_model=SubcategoryOut)
def update_subcategory(subcategory_id: UUID, payload: CategoryPatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Subcategory, subcategory_id, user.id)
    apply_changes(item, payload)
    db.commit()
    return item


@router.delete("/subcategories/{subcategory_id}", response_model=APIMessage)
def disable_subcategory(subcategory_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Subcategory, subcategory_id, user.id)
    item.is_active = False
    db.commit()
    return {"message": "Subcategory disabled"}


@router.get("/provider-category-mappings", response_model=list[ProviderCategoryMappingOut])
def list_provider_mappings(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.scalars(select(ProviderCategoryMapping).where(ProviderCategoryMapping.user_id == user.id)).all()


@router.post("/provider-category-mappings", response_model=ProviderCategoryMappingOut, status_code=201)
def create_provider_mapping(payload: ProviderCategoryMappingIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    owned_or_404(db, Category, payload.category_id, user.id)
    institution = owned_or_404(db, Institution, payload.institution_id, user.id)
    item = ProviderCategoryMapping(user_id=user.id, **payload.model_dump())
    item.institution = institution
    db.add(item)
    db.commit()
    return item
