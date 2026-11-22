"""Automatic API fuzzing with Schemathesis.

Schemathesis reads the API description FastAPI publishes at /openapi.json and
sends hundreds of generated requests (odd numbers, long strings, missing fields,
wrong types...) to every endpoint. The test fails if any request gets a
500 Internal Server Error, i.e. if any input can crash the server.

New endpoints are covered automatically - no test changes needed.

Not part of the normal `pytest` run (it's slower). Run it with:
    pytest -m fuzz
"""
import bcrypt
import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.checks import not_a_server_error
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

pytestmark = pytest.mark.fuzz

schema = schemathesis.openapi.from_asgi("/openapi.json", app)


@pytest.fixture(scope="module", autouse=True)
def fuzz_database():
    """One throwaway in-memory database shared by all fuzz requests."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    # cheap bcrypt so the fuzzer can hit /register many times quickly
    real_gensalt = bcrypt.gensalt
    bcrypt.gensalt = lambda rounds=4, prefix=b"2b": real_gensalt(rounds, prefix)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    bcrypt.gensalt = real_gensalt
    engine.dispose()


@pytest.fixture(scope="module", autouse=True)
def no_real_ocr():
    """Uploads must never reach the real OCR engine during fuzzing."""
    import app.controllers.receipt_controller as receipt_controller

    original = receipt_controller.read_receipt

    def fake_read_receipt(file_bytes, filename):
        raise RuntimeError("OCR disabled during fuzzing")

    receipt_controller.read_receipt = fake_read_receipt
    yield
    receipt_controller.read_receipt = original


@schema.parametrize()
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=list(HealthCheck),
)
def test_no_endpoint_crashes(case):
    case.call_and_validate(checks=[not_a_server_error])
