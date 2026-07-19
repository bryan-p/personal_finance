from types import SimpleNamespace
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import apply_changes, owned_or_404
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import (
    Category,
    DraftTransaction,
    MatchOperator,
    Rule,
    Subcategory,
    Transaction,
)
from app.schemas import APIMessage, RuleIn, RuleOut, RulePatch, RuleTestIn
from app.services.rules import rule_matches, validate_regex_pattern


router = APIRouter(prefix="/rules", tags=["rules"])


def validate_rule_selection(
    db: Session,
    user_id: UUID,
    category_id: UUID | None,
    subcategory_id: UUID | None,
) -> None:
    if subcategory_id is not None and category_id is None:
        raise HTTPException(
            status_code=422,
            detail="A category is required when selecting a subcategory",
        )
    if category_id is not None:
        owned_or_404(db, Category, category_id, user_id)
    if subcategory_id is not None:
        subcategory = owned_or_404(db, Subcategory, subcategory_id, user_id)
        if subcategory.category_id != category_id:
            raise HTTPException(
                status_code=422,
                detail="Subcategory must belong to the selected category",
            )


def validate_rule_pattern(
    match_operator: MatchOperator,
    match_value: str,
) -> None:
    if match_operator != MatchOperator.regex:
        return
    try:
        validate_regex_pattern(match_value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.scalars(select(Rule).where(Rule.user_id == user.id).order_by(Rule.priority, Rule.created_at)).all()


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(payload: RuleIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    validate_rule_pattern(payload.match_operator, payload.match_value)
    validate_rule_selection(
        db, user.id, payload.category_id, payload.subcategory_id
    )
    item = Rule(user_id=user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    return item


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: UUID, payload: RulePatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Rule, rule_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    category_id = changes.get("category_id", item.category_id)
    subcategory_id = changes.get("subcategory_id", item.subcategory_id)
    match_operator = changes.get("match_operator", item.match_operator)
    match_value = changes.get("match_value", item.match_value)
    validate_rule_pattern(match_operator, match_value)
    validate_rule_selection(db, user.id, category_id, subcategory_id)
    apply_changes(item, payload)
    db.commit()
    return item


@router.delete("/{rule_id}", response_model=APIMessage)
def delete_rule(rule_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Rule, rule_id, user.id)
    db.execute(
        update(DraftTransaction)
        .where(
            DraftTransaction.user_id == user.id,
            DraftTransaction.applied_rule_id == item.id,
        )
        .values(applied_rule_id=None)
    )
    db.delete(item)
    db.commit()
    return {"message": "Rule deleted"}


@router.post("/test")
def test_rule(payload: RuleTestIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    candidate = SimpleNamespace(**payload.rule.model_dump())
    transactions = db.scalars(
        select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.transaction_date.desc()).limit(1000)
    ).all()
    matches = [item for item in transactions if rule_matches(item, candidate, db)][: payload.limit]
    return {
        "match_count": len(matches),
        "matches": [
            {"id": item.id, "transaction_date": item.transaction_date, "description": item.description_clean, "amount": item.amount}
            for item in matches
        ],
    }
