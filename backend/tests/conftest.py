"""Shared fixtures.

Every test gets a fresh in-memory SQLite database, so tests never touch
backend/spendgpt.db or the real TiDB/MySQL database and can run in any order.

AI tests also get a fake LM Studio (no server needed). Live LM Studio tests are
in test_lmstudio_live.py and are excluded by default (see pytest.ini).
"""
import os
import tempfile

# Set before `app` is imported (config is read at import time): keeps the app's
# default engine away from backend/spendgpt.db and keeps LM Studio off in tests.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='spendgpt-tests-')}/unused.db"
os.environ.setdefault("LM_STUDIO_ENABLED", "false")

import bcrypt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.services.lmstudio_service import LMStudioConnectionError  # noqa: E402


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


# -- AI test helpers -------------------------------------------------------------------
class FakeLMStudio:
    """Stands in for LMStudioClient and records the messages it was sent."""

    enabled = True
    model = "fake-model"

    def __init__(self, reply="Fake answer from the local model.", json_reply=None, available=True):
        self.reply = reply
        self.json_reply = json_reply if json_reply is not None else {}
        self.available = available
        self.calls: list[list[dict]] = []

    def _check(self):
        if not self.available:
            raise LMStudioConnectionError("Cannot connect to LM Studio (fake offline).")

    def list_models(self):
        self._check()
        return ["fake-model"]

    def is_available(self):
        return self.available

    def status(self):
        if not self.available:
            return {"available": False, "reason": "connection", "models": [], "configured_model": None}
        return {"available": True, "reason": None, "models": ["fake-model"], "configured_model": None}

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        self._check()
        return self.reply

    def chat_json(self, messages, schema, name="result", **kwargs):
        self.calls.append(messages)
        self._check()
        return self.json_reply

    async def alist_models(self):
        return self.list_models()

    async def astatus(self):
        return self.status()

    async def achat(self, messages, **kwargs):
        return self.chat(messages, **kwargs)

    async def achat_json(self, messages, schema, name="result", **kwargs):
        return self.chat_json(messages, schema, name, **kwargs)


@pytest.fixture
def fake_llm():
    return FakeLMStudio()


@pytest.fixture
def offline_llm():
    return FakeLMStudio(available=False)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# Same names and order as the INSERT in database/SpendGPT.sql.
SEED_CATEGORIES = [
    ("Groceries", "Essential"), ("Rent", "Essential"), ("Utilities", "Essential"),
    ("Transport", "Essential"), ("Health", "Essential"), ("Eating Out", "Discretionary"),
    ("Shopping", "Discretionary"), ("Entertainment", "Discretionary"),
    ("Subscriptions", "Discretionary"), ("Other", "Discretionary"),
]


@pytest.fixture
def db(db_session):
    """db_session with the full category list from database/SpendGPT.sql."""
    db_session.add_all(Category(category_name=n, spend_type=t) for n, t in SEED_CATEGORIES)
    db_session.commit()
    return db_session


def create_user(db, email="student@example.com", **fields):
    """Insert a user row directly (no API call)."""
    from app.models.user import User

    user = User(first_name=fields.pop("first_name", "Test"), last_name="Student", email=email,
                password_hash="x", **fields)
    db.add(user)
    db.commit()
    return user


def category_id(db, name):
    return db.scalar(select(Category.category_id).where(Category.category_name == name))
