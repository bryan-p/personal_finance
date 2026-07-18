from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import apply_changes, owned_or_404
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import (
    Category,
    Institution,
    ProviderCategoryMapping,
    ProviderTransactionTypeMapping,
    Subcategory,
)
from app.schemas import (
    APIMessage,
    CategoryIn,
    CategoryOut,
    CategoryPatch,
    ProviderCategoryMappingIn,
    ProviderCategoryMappingOut,
    ProviderTransactionTypeMappingIn,
    ProviderTransactionTypeMappingOut,
    SubcategoryIn,
    SubcategoryOut,
)


router = APIRouter(tags=["categories"])


def validate_category_selection(
    db: Session, user_id, category_id: UUID, subcategory_id: UUID | None
) -> None:
    owned_or_404(db, Category, category_id, user_id)
    if not subcategory_id:
        return
    subcategory = owned_or_404(db, Subcategory, subcategory_id, user_id)
    if subcategory.category_id != category_id:
        raise HTTPException(
            status_code=422,
            detail="Subcategory must belong to the selected category",
        )


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
    validate_category_selection(
        db, user.id, payload.category_id, payload.subcategory_id
    )
    institution = owned_or_404(db, Institution, payload.institution_id, user.id)
    source_category = payload.source_category.strip()
    if not source_category:
        raise HTTPException(status_code=422, detail="Institution category is required")
    existing = db.scalar(
        select(ProviderCategoryMapping).where(
            ProviderCategoryMapping.user_id == user.id,
            ProviderCategoryMapping.institution_id == payload.institution_id,
            func.lower(ProviderCategoryMapping.source_category) == source_category.lower(),
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A mapping for this institution category already exists",
        )
    item = ProviderCategoryMapping(
        user_id=user.id,
        **(payload.model_dump() | {"source_category": source_category}),
    )
    item.institution = institution
    db.add(item)
    db.commit()
    return item


@router.delete("/provider-category-mappings/{mapping_id}", response_model=APIMessage)
def delete_provider_mapping(
    mapping_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    item = owned_or_404(db, ProviderCategoryMapping, mapping_id, user.id)
    db.delete(item)
    db.commit()
    return {"message": "Institution category mapping deleted"}


@router.get(
    "/provider-transaction-type-mappings",
    response_model=list[ProviderTransactionTypeMappingOut],
)
def list_provider_type_mappings(
    db: Session = Depends(get_db), user=Depends(get_current_user)
):
    return db.scalars(
        select(ProviderTransactionTypeMapping)
        .where(ProviderTransactionTypeMapping.user_id == user.id)
        .order_by(
            ProviderTransactionTypeMapping.institution_id,
            ProviderTransactionTypeMapping.source_transaction_type,
        )
    ).all()


@router.post(
    "/provider-transaction-type-mappings",
    response_model=ProviderTransactionTypeMappingOut,
    status_code=201,
)
def create_provider_type_mapping(
    payload: ProviderTransactionTypeMappingIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    institution = owned_or_404(db, Institution, payload.institution_id, user.id)
    source_transaction_type = payload.source_transaction_type.strip()
    if not source_transaction_type:
        raise HTTPException(status_code=422, detail="Provider transaction type is required")
    existing = db.scalar(
        select(ProviderTransactionTypeMapping).where(
            ProviderTransactionTypeMapping.user_id == user.id,
            ProviderTransactionTypeMapping.institution_id == payload.institution_id,
            func.lower(ProviderTransactionTypeMapping.source_transaction_type)
            == source_transaction_type.lower(),
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A mapping for this provider transaction type already exists",
        )
    item = ProviderTransactionTypeMapping(
        user_id=user.id,
        **(
            payload.model_dump()
            | {"source_transaction_type": source_transaction_type}
        ),
    )
    item.institution = institution
    db.add(item)
    db.commit()
    return item


@router.delete(
    "/provider-transaction-type-mappings/{mapping_id}", response_model=APIMessage
)
def delete_provider_type_mapping(
    mapping_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    item = owned_or_404(db, ProviderTransactionTypeMapping, mapping_id, user.id)
    db.delete(item)
    db.commit()
    return {"message": "Provider transaction type mapping deleted"}
