from types import SimpleNamespace
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import apply_changes, owned_or_404
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Rule, Transaction
from app.schemas import APIMessage, RuleIn, RuleOut, RulePatch, RuleTestIn
from app.services.rules import rule_matches


router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.scalars(select(Rule).where(Rule.user_id == user.id).order_by(Rule.priority, Rule.created_at)).all()


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(payload: RuleIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = Rule(user_id=user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    return item


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: UUID, payload: RulePatch, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Rule, rule_id, user.id)
    apply_changes(item, payload)
    db.commit()
    return item


@router.delete("/{rule_id}", response_model=APIMessage)
def delete_rule(rule_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = owned_or_404(db, Rule, rule_id, user.id)
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

