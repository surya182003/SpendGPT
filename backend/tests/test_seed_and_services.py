import os
from pathlib import Path

import bcrypt
import pytest
from sqlalchemy.orm import sessionmaker

import app.seed as seed_module
import app.services.ocr_service as ocr_service
from app.models.user import User


# ---------- seed script ----------

@pytest.fixture
def seed_into_test_db(engine, monkeypatch):
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module, "SessionLocal", sessionmaker(bind=engine, autoflush=False))
    return seed_module.seed


def test_seed_creates_demo_users(seed_into_test_db, db_session):
    seed_into_test_db()
    emails = sorted(u.email for u in db_session.query(User))
    assert emails == ["demo@example.com", "test@example.com"]


def test_seed_twice_does_not_duplicate(seed_into_test_db, db_session):
    seed_into_test_db()
    seed_into_test_db()
    assert db_session.query(User).count() == 2


def test_seed_does_not_overwrite_existing_user(seed_into_test_db, db_session):
    db_session.add(User(first_name="Mine", last_name="Own", email="demo@example.com", password_hash="keep-me"))
    db_session.commit()
    seed_into_test_db()
    db_session.expire_all()
    assert db_session.query(User).filter_by(email="demo@example.com").one().password_hash == "keep-me"


def test_seeded_demo_user_can_log_in(seed_into_test_db, client):
    seed_into_test_db()
    response = client.post("/api/auth/login", json={"email": "demo@example.com", "password": "DemoPass123"})
    assert response.status_code == 200


def test_seed_stores_hashed_passwords(seed_into_test_db, db_session):
    seed_into_test_db()
    for user in db_session.query(User):
        assert bcrypt.checkpw(b"DemoPass123", user.password_hash.encode()) or bcrypt.checkpw(
            b"TestPass123", user.password_hash.encode()
        )


# ---------- OCR service (temp-file handling; the OCR engine itself is faked) ----------

@pytest.fixture
def fake_process_receipt(monkeypatch):
    seen = {}

    def _fake(path):
        seen["path"] = Path(path)
        seen["existed"] = Path(path).is_file()
        seen["content"] = Path(path).read_bytes()
        return {"ok": True}

    monkeypatch.setattr(ocr_service, "process_receipt", _fake)
    return seen


def test_read_receipt_writes_bytes_to_temp_file(fake_process_receipt):
    assert ocr_service.read_receipt(b"image-bytes", "receipt.png") == {"ok": True}
    assert fake_process_receipt["existed"]
    assert fake_process_receipt["content"] == b"image-bytes"


@pytest.mark.parametrize(("filename", "suffix"), [("r.png", ".png"), ("r.JPEG", ".JPEG"), ("noext", ".jpg"), (None, ".jpg")])
def test_read_receipt_keeps_file_extension(fake_process_receipt, filename, suffix):
    ocr_service.read_receipt(b"x", filename)
    assert fake_process_receipt["path"].suffix == suffix


def test_read_receipt_deletes_temp_file(fake_process_receipt):
    ocr_service.read_receipt(b"x", "r.jpg")
    assert not fake_process_receipt["path"].exists()


def test_read_receipt_deletes_temp_file_even_when_ocr_fails(monkeypatch):
    seen = {}

    def _boom(path):
        seen["path"] = path
        raise RuntimeError("Indra OCR returned no text.")

    monkeypatch.setattr(ocr_service, "process_receipt", _boom)
    with pytest.raises(RuntimeError):
        ocr_service.read_receipt(b"x", "r.jpg")
    assert not os.path.exists(seen["path"])
