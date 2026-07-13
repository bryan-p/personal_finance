import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Institution


STARTER_INSTITUTIONS = (
    "Ally Bank",
    "American Express",
    "Bank of America",
    "Barclays",
    "Capital One",
    "Charles Schwab",
    "Chase",
    "Citi",
    "Citizens Bank",
    "Discover",
    "Fidelity",
    "Fifth Third Bank",
    "Goldman Sachs",
    "KeyBank",
    "Navy Federal Credit Union",
    "PNC Bank",
    "Regions Bank",
    "SoFi",
    "Synchrony Bank",
    "TD Bank",
    "Truist",
    "U.S. Bank",
    "USAA",
    "Wells Fargo",
)


def clean_institution_name(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def normalize_institution_name(value: str) -> str:
    return clean_institution_name(value).casefold()


def seed_institutions(db: Session, user_id) -> None:
    existing = set(
        db.scalars(select(Institution.normalized_name).where(Institution.user_id == user_id)).all()
    )
    for name in STARTER_INSTITUTIONS:
        normalized = normalize_institution_name(name)
        if normalized not in existing:
            db.add(
                Institution(
                    user_id=user_id,
                    display_name=name,
                    normalized_name=normalized,
                    is_system=True,
                )
            )
            existing.add(normalized)
