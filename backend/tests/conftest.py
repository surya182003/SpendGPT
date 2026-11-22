"""Shared test setup: a throwaway SQLite database and a fake LM Studio.

No LM Studio server, MySQL/TiDB database or OCR model is needed for the
automated tests. Live LM Studio tests are in test_lmstudio_live.py and are
excluded by default (see pytest.ini).
"""
import os
import sys
import tempfile
from pathlib import Path

# Must be set before `app` is imported: config is read at import time.
_TMP = tempfile.mkdtemp(prefix="spendgpt-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ.setdefault("LM_STUDIO_ENABLED", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.services.lmstudio_service import LMStudioConnectionError  # noqa: E402


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


# -- database -------------------------------------------------------------------------
# Same names and order as the INSERT in database/SpendGPT.sql.
SEED_CATEGORIES = [
    ("Groceries", "Essential"), ("Rent", "Essential"), ("Utilities", "Essential"),
    ("Transport", "Essential"), ("Health", "Essential"), ("Eating Out", "Discretionary"),
    ("Shopping", "Discretionary"), ("Entertainment", "Discretionary"),
    ("Subscriptions", "Discretionary"), ("Other", "Discretionary"),
]


def reset_database(categories=SEED_CATEGORIES):
    """Drop and recreate every table, then seed the categories table."""
    import app.models  # noqa: F401  (registers every model, incl. Budget/Alert, on Base.metadata)
    from app.database import Base, SessionLocal, engine
    from app.models.category import Category

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        session.add_all(Category(category_name=n, spend_type=t) for n, t in categories)
        session.commit()


@pytest.fixture
def db():
    from app.database import SessionLocal

    reset_database()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_user(db, email="student@example.com", **fields):
    from app.models.user import User

    user = User(first_name=fields.pop("first_name", "Test"), last_name="Student", email=email,
                password_hash="x", **fields)
    db.add(user)
    db.commit()
    return user


def category_id(db, name):
    from sqlalchemy import select

    from app.models.category import Category

    return db.scalar(select(Category.category_id).where(Category.category_name == name))
