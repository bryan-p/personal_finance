#!/usr/bin/env python3
"""Exercise the complete API workflow against the configured local database, then clean up."""
import io
import sys
import uuid
from pathlib import Path

sys.path.insert(0, "backend")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


email = f"smoke-{uuid.uuid4()}@example.com"
client = TestClient(app)
import_id = None
try:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "local-smoke-password", "display_name": "Smoke Test"},
    )
    assert response.status_code == 201, response.text
    assert len(client.get("/categories").json()) == 16

    response = client.post("/institutions", json={"display_name": "Example Bank"})
    assert response.status_code == 201, response.text
    institution_id = response.json()["id"]

    response = client.post(
        "/accounts",
        json={"name": "Test Card", "institution_id": institution_id, "account_type": "credit_card", "currency": "USD", "is_active": True},
    )
    assert response.status_code == 201, response.text
    account_id = response.json()["id"]

    response = client.post(
        f"/accounts/{account_id}/instruments",
        json={"instrument_type": "authorized_user_card", "display_name": "Test user ending 5678", "last_four": "5678", "source_identifier": "xxxx5678", "is_active": True},
    )
    assert response.status_code == 201, response.text

    content = (
        "Date,Description,Amount,Card Last Four,Category,Transaction ID\n"
        "2026-07-01,TEST COFFEE,4.50,5678,Dining,smoke-1\n"
        "2026-07-02,ONLINE PAYMENT,-100.00,5678,Payment,smoke-2\n"
    ).encode()
    response = client.post(
        "/imports/upload",
        data={"account_id": account_id},
        files={"file": ("smoke.csv", io.BytesIO(content), "text/csv")},
    )
    assert response.status_code == 201, response.text
    upload = response.json()
    import_id = upload["id"]
    response = client.post(
        f"/imports/{import_id}/mapping",
        json={
            "institution_id": institution_id,
            "account_type": "credit_card",
            "mapping_name": "Smoke mapping",
            "date_column": "Date",
            "description_column": "Description",
            "amount_column": "Amount",
            "card_last_four_column": "Card Last Four",
            "category_column": "Category",
            "transaction_id_column": "Transaction ID",
            "amount_behavior": "charges_positive",
        },
    )
    assert response.status_code == 200, response.text
    mapping_id = response.json()["id"]
    response = client.post(f"/imports/{import_id}/normalize?mapping_id={mapping_id}")
    assert response.status_code == 200, response.text
    review = client.get(f"/imports/{import_id}/review").json()
    assert len(review) == 2
    assert review[0]["card_last_four"] == "5678"
    assert review[1]["is_excluded_from_spending"] is True
    response = client.post(f"/imports/{import_id}/confirm")
    assert response.status_code == 200, response.text
    assert response.json()["imported_count"] == 2
    assert len(client.get("/transactions").json()) == 2
    assert client.get("/transactions/export").status_code == 200
    assert client.get("/dashboard/summary?start_date=2026-07-01&end_date=2026-07-31").status_code == 200
    assert client.get(f"/dashboard/instrument-summary?account_id={account_id}&start_date=2026-07-01&end_date=2026-07-31").status_code == 200
    print("API smoke test passed: auth → account/card → upload → mapping → review → confirm → dashboard/export")
finally:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            db.execute(delete(User).where(User.id == user.id))
            db.commit()
    if import_id:
        Path("backend/storage/imports", f"{import_id}.csv").unlink(missing_ok=True)
