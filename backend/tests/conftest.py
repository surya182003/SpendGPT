"""Shared fixtures.

Every test gets a fresh in-memory SQLite database, so tests never touch
backend/spendgpt.db or the real TiDB/MySQL database and can run in any order.
"""
import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.category import Category


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch):
    """bcrypt's default cost (12) makes every register ~0.25s; cost 4 is plenty for tests."""
    real_gensalt = bcrypt.gensalt
    monkeypatch.setattr(bcrypt, "gensalt", lambda rounds=4, prefix=b"2b": real_gensalt(rounds, prefix))


@pytest.fixture
def engine():
    # StaticPool keeps one connection, so the in-memory DB survives across sessions.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ignores foreign keys unless asked; turn them on to behave like MySQL.
    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    """Direct DB access for arranging data and checking what was saved."""
    session = sessionmaker(bind=engine, autoflush=False)()
    yield session
    session.close()


@pytest.fixture
def client(engine):
    TestSession = sessionmaker(bind=engine, autoflush=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # No "with" block: skips the lifespan hook, which would create tables in the real DB.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(client):
    """Factory: make_user(email="x@y.com") -> registered user dict."""
    counter = {"n": 0}

    def _make(email=None, password="password123", first_name="Test", last_name="User"):
        counter["n"] += 1
        email = email or f"user{counter['n']}@example.com"
        response = client.post(
            "/api/auth/register",
            json={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "password": password,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["user"]

    return _make


@pytest.fixture
def user(make_user):
    return make_user()


@pytest.fixture
def categories(db_session):
    """Categories aren't created by app.seed, so tests insert their own."""
    rows = [
        Category(category_name="Groceries", spend_type="essential"),
        Category(category_name="Entertainment", spend_type="discretionary"),
    ]
    db_session.add_all(rows)
    db_session.commit()
    return [{"category_id": c.category_id, "category_name": c.category_name} for c in rows]
