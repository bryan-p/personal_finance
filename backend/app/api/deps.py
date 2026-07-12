from fastapi import HTTPException
from sqlalchemy.orm import Session


def owned_or_404(db: Session, model, object_id, user_id):
    item = db.get(model, object_id)
    if not item or item.user_id != user_id:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return item


def apply_changes(item, data):
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    return item

