from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.categories import router as categories_router
from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.models import Category, Subcategory, User


@pytest.fixture
def category_api():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    with test_session() as db:
        user = User(
            email="categories@example.com",
            password_hash="test",
            display_name="Category Tester",
        )
        db.add(user)
        db.commit()
        user_id = user.id

    app = FastAPI()
    app.include_router(categories_router)

    def override_get_db():
        with test_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            session_factory=test_session,
            user_id=user_id,
        )

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_create_category_rejects_duplicate_name(category_api):
    with category_api.session_factory() as db:
        db.add(
            Category(
                user_id=category_api.user_id,
                name="Utilities",
                is_system=False,
            )
        )
        db.commit()

    response = category_api.client.post("/categories", json={"name": "Utilities"})

    assert response.status_code == 409
    assert response.json() == {"detail": "A category with this name already exists"}


def test_create_category_handles_commit_time_duplicate(category_api, monkeypatch):
    with category_api.session_factory() as db:
        db.add(
            Category(
                user_id=category_api.user_id,
                name="Utilities",
                is_system=False,
            )
        )
        db.commit()

    monkeypatch.setattr(Session, "scalar", lambda _db, _statement: None)

    response = category_api.client.post("/categories", json={"name": "Utilities"})

    assert response.status_code == 409
    assert response.json() == {"detail": "A category with this name already exists"}
    with category_api.session_factory() as db:
        assert db.query(Category).filter_by(name="Utilities").count() == 1


def test_create_subcategory_rejects_duplicate_name_in_parent(category_api):
    with category_api.session_factory() as db:
        category = Category(
            user_id=category_api.user_id,
            name="Home",
            is_system=False,
        )
        db.add(category)
        db.flush()
        db.add(
            Subcategory(
                user_id=category_api.user_id,
                category_id=category.id,
                name="Utilities",
                is_system=False,
            )
        )
        db.commit()
        category_id = category.id

    response = category_api.client.post(
        "/subcategories",
        json={"category_id": str(category_id), "name": "Utilities"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "A subcategory with this name already exists in the selected category"
    }


def test_create_subcategory_handles_commit_time_duplicate(category_api, monkeypatch):
    with category_api.session_factory() as db:
        category = Category(
            user_id=category_api.user_id,
            name="Home",
            is_system=False,
        )
        db.add(category)
        db.flush()
        db.add(
            Subcategory(
                user_id=category_api.user_id,
                category_id=category.id,
                name="Utilities",
                is_system=False,
            )
        )
        db.commit()
        category_id = category.id

    monkeypatch.setattr(Session, "scalar", lambda _db, _statement: None)

    response = category_api.client.post(
        "/subcategories",
        json={"category_id": str(category_id), "name": "Utilities"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "A subcategory with this name already exists in the selected category"
    }
    with category_api.session_factory() as db:
        assert db.query(Subcategory).filter_by(
            category_id=category_id,
            name="Utilities",
        ).count() == 1
