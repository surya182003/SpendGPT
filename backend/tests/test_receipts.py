"""Receipt upload + AI receipt endpoints.

The real OCR engine (indra-ocr) is never called: `fake_ocr` swaps out
read_receipt so these tests are fast and don't need the OCR install.
"""
import pytest

from app.models.receipt_item import ReceiptItem
from app.models.transaction import Transaction

UPLOAD = "/api/receipts/upload"


def ocr_result(**overrides):
    result = {
        "merchant_name": "Aldi",
        "transaction_date": "2026-10-07",
        "total_amount": 5.44,  # 1.15 + 3 x 0.80 + 1.89
        "items": [
            {"item_name": "Whole Milk", "quantity": 1.0, "unit_price": 1.15},
            {"item_name": "  Apples  ", "quantity": 3.0, "unit_price": 0.80},
            {"item_name": "Bread", "quantity": 1.0, "unit_price": 1.89},
        ],
        "requires_review": False,
        "validation_issues": [],
    }
    result.update(overrides)
    return result


@pytest.fixture
def fake_ocr(monkeypatch):
    """fake_ocr(result) sets what OCR 'reads'; fake_ocr(error=RuntimeError(...)) makes it fail."""
    calls = []

    def _set(result=None, error=None):
        def _read_receipt(file_bytes, filename):
            calls.append((file_bytes, filename))
            if error:
                raise error
            return result if result is not None else ocr_result()

        monkeypatch.setattr("app.controllers.receipt_controller.read_receipt", _read_receipt)
        return calls

    _set()
    return _set


def upload(client, user_id, content=b"fake-image-bytes", filename="receipt.jpg", content_type="image/jpeg"):
    return client.post(
        UPLOAD,
        data={"user_id": str(user_id)},
        files={"file": (filename, content, content_type)},
    )


# ---------- upload: happy path ----------

def test_upload_creates_transaction_with_items(client, user, fake_ocr, db_session):
    response = upload(client, user["user_id"])
    assert response.status_code == 201
    body = response.json()
    assert body["merchant_name"] == "Aldi"
    assert body["transaction_date"] == "2026-10-07"
    assert body["total_amount"] == 5.44
    assert len(body["items"]) == 3
    assert body["requires_review"] is False
    assert body["validation_issues"] == []

    txn = db_session.get(Transaction, body["transaction_id"])
    assert txn.receipt_hash is not None and len(txn.receipt_hash) == 64


def test_upload_normalizes_item_names(client, user, fake_ocr):
    items = upload(client, user["user_id"]).json()["items"]
    apples = next(i for i in items if "Apples" in i["item_name"])
    assert apples["normalized_name"] == "apples"
    assert apples["quantity"] == 3.0


def test_upload_passes_bytes_and_filename_to_ocr(client, user, fake_ocr):
    calls = fake_ocr()
    upload(client, user["user_id"], content=b"abc123", filename="aldi.png", content_type="image/png")
    assert calls == [(b"abc123", "aldi.png")]


def test_upload_passes_through_review_flags(client, user, fake_ocr):
    fake_ocr(ocr_result(requires_review=True, validation_issues=["Total was taken from a subtotal line."]))
    body = upload(client, user["user_id"]).json()
    assert body["requires_review"] is True
    assert body["validation_issues"] == ["Total was taken from a subtotal line."]


@pytest.mark.parametrize("merchant", [None, ""])
def test_upload_missing_merchant_saved_as_unknown(client, user, fake_ocr, merchant):
    fake_ocr(ocr_result(merchant_name=merchant))
    assert upload(client, user["user_id"]).json()["merchant_name"] == "Unknown"


def test_upload_truncates_long_merchant_and_item_names(client, user, fake_ocr):
    fake_ocr(ocr_result(
        merchant_name="M" * 150,
        items=[{"item_name": "I" * 200, "quantity": 1, "unit_price": 1.0}],
    ))
    body = upload(client, user["user_id"]).json()
    assert len(body["merchant_name"]) == 100
    assert len(body["items"][0]["item_name"]) == 150


def test_upload_with_no_items_still_saves(client, user, fake_ocr):
    fake_ocr(ocr_result(items=[], requires_review=True, validation_issues=["No line items were extracted."]))
    response = upload(client, user["user_id"])
    assert response.status_code == 201
    assert response.json()["items"] == []


# ---------- upload: rejections ----------

def test_upload_unknown_user_is_404(client, fake_ocr):
    assert upload(client, 999).status_code == 404


@pytest.mark.parametrize("content_type", ["application/pdf", "text/plain", "application/octet-stream"])
def test_upload_non_image_is_400(client, user, fake_ocr, content_type):
    assert upload(client, user["user_id"], content_type=content_type).status_code == 400


def test_upload_empty_file_is_400(client, user, fake_ocr):
    assert upload(client, user["user_id"], content=b"").status_code == 400


def test_upload_missing_file_is_422(client, user):
    assert client.post(UPLOAD, data={"user_id": str(user["user_id"])}).status_code == 422


def test_upload_same_image_twice_is_409(client, user, fake_ocr, db_session):
    assert upload(client, user["user_id"]).status_code == 201
    assert upload(client, user["user_id"]).status_code == 409
    assert db_session.query(Transaction).count() == 1


def test_duplicate_check_is_by_content_not_filename(client, user, fake_ocr):
    upload(client, user["user_id"], filename="a.jpg")
    assert upload(client, user["user_id"], filename="b.jpg").status_code == 409


def test_different_users_can_upload_same_image(client, make_user, fake_ocr):
    alice, bob = make_user(), make_user()
    assert upload(client, alice["user_id"]).status_code == 201
    assert upload(client, bob["user_id"]).status_code == 201


def test_duplicate_is_detected_before_running_ocr(client, user, fake_ocr):
    calls = fake_ocr()
    upload(client, user["user_id"])
    upload(client, user["user_id"])
    assert len(calls) == 1


def test_upload_ocr_failure_is_422(client, user, fake_ocr, db_session):
    fake_ocr(error=RuntimeError("Indra OCR returned no text."))
    response = upload(client, user["user_id"])
    assert response.status_code == 422
    assert "Indra OCR returned no text." in response.json()["detail"]
    assert db_session.query(Transaction).count() == 0


@pytest.mark.parametrize("missing", ["total_amount", "transaction_date"])
def test_upload_missing_total_or_date_is_422(client, user, fake_ocr, db_session, missing):
    fake_ocr(ocr_result(**{missing: None}, validation_issues=["Receipt total could not be identified."]))
    response = upload(client, user["user_id"])
    assert response.status_code == 422
    assert response.json()["detail"]["validation_issues"] == ["Receipt total could not be identified."]
    assert db_session.query(Transaction).count() == 0


# ---------- cascade ----------

def test_deleting_receipt_transaction_deletes_its_items(client, user, fake_ocr, db_session):
    txn_id = upload(client, user["user_id"]).json()["transaction_id"]
    assert db_session.query(ReceiptItem).count() == 3

    assert client.delete(f"/api/transactions/{txn_id}").status_code == 200
    db_session.expire_all()
    assert db_session.query(ReceiptItem).count() == 0


# ---------- AI endpoints ----------

def test_ai_get_receipt(client, user, fake_ocr):
    uploaded = upload(client, user["user_id"]).json()
    response = client.get(f"/api/ai/receipts/{uploaded['transaction_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["transaction_id"] == uploaded["transaction_id"]
    assert body["items"] == uploaded["items"]
    assert "requires_review" not in body


def test_ai_get_receipt_unknown_is_404(client):
    assert client.get("/api/ai/receipts/999").status_code == 404


def test_ai_receipt_includes_category_name(client, user, fake_ocr, categories, db_session):
    txn_id = upload(client, user["user_id"]).json()["transaction_id"]
    txn = db_session.get(Transaction, txn_id)
    txn.category_id = categories[0]["category_id"]
    db_session.commit()

    body = client.get(f"/api/ai/receipts/{txn_id}").json()
    assert body["category_name"] == "Groceries"


def test_ai_user_receipts_excludes_manual_transactions(client, user, fake_ocr):
    client.post(
        "/api/transactions/",
        params={"user_id": user["user_id"]},
        json={"merchant_name": "Manual", "amount": "5.00", "transaction_date": "2026-11-01"},
    )
    upload(client, user["user_id"])

    body = client.get(f"/api/ai/users/{user['user_id']}/receipts").json()
    assert [r["merchant_name"] for r in body] == ["Aldi"]


def test_ai_user_receipts_newest_first_and_limit(client, user, fake_ocr):
    for i, day in enumerate(["2026-09-01", "2026-11-01", "2026-10-01"]):
        fake_ocr(ocr_result(transaction_date=day))
        upload(client, user["user_id"], content=f"image-{i}".encode())

    body = client.get(f"/api/ai/users/{user['user_id']}/receipts").json()
    assert [r["transaction_date"] for r in body] == ["2026-11-01", "2026-10-01", "2026-09-01"]

    limited = client.get(f"/api/ai/users/{user['user_id']}/receipts", params={"limit": 2}).json()
    assert len(limited) == 2


def test_ai_user_receipts_only_that_user(client, make_user, fake_ocr):
    alice, bob = make_user(), make_user()
    upload(client, alice["user_id"])
    assert client.get(f"/api/ai/users/{bob['user_id']}/receipts").json() == []


def test_ai_user_receipts_unknown_user_is_404(client):
    assert client.get("/api/ai/users/999/receipts").status_code == 404


def test_ai_user_receipts_limit_zero_returns_nothing(client, user, fake_ocr):
    upload(client, user["user_id"])
    assert client.get(f"/api/ai/users/{user['user_id']}/receipts", params={"limit": 0}).json() == []


@pytest.mark.xfail(
    strict=True,
    reason="BUG: a negative limit isn't rejected; SQLite treats LIMIT -1 as 'no limit' and returns everything. "
    "Use limit: int = Query(50, ge=1, le=200).",
)
def test_ai_user_receipts_negative_limit_is_422(client, user):
    assert client.get(f"/api/ai/users/{user['user_id']}/receipts", params={"limit": -1}).status_code == 422


# ---------- bad input never crashes the server ----------

HUGE_ID = 10**23  # bigger than any database integer column


@pytest.mark.xfail(
    strict=True,
    reason="BUG: IDs larger than 64 bits crash the server (500, SQLite OverflowError). "
    "Bound IDs, e.g. Annotated[int, Field(gt=0, le=2_147_483_647)].",
)
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda c, u: upload(c, HUGE_ID), id="upload-huge-user_id"),
        pytest.param(lambda c, u: c.get(f"/api/ai/receipts/{HUGE_ID}"), id="ai-receipt-huge-id"),
        pytest.param(lambda c, u: c.get(f"/api/ai/users/{HUGE_ID}/receipts"), id="ai-receipts-huge-user_id"),
        pytest.param(lambda c, u: c.get(f"/api/ai/users/{u}/receipts", params={"limit": HUGE_ID}), id="ai-receipts-huge-limit"),
    ],
)
def test_huge_ids_do_not_crash_the_server(client, user, fake_ocr, call):
    assert call(client, user["user_id"]).status_code in (404, 422)


def test_upload_non_numeric_user_id_is_422(client, fake_ocr):
    response = client.post(UPLOAD, data={"user_id": "abc"}, files={"file": ("r.jpg", b"x", "image/jpeg")})
    assert response.status_code == 422


# ---------- upload limits ----------

@pytest.mark.xfail(
    strict=True,
    reason="BUG: no upload size limit - the whole file is read into memory, so huge uploads can exhaust "
    "server memory. Reject files over e.g. 10 MB with 413.",
)
def test_upload_over_size_limit_is_rejected(client, user, fake_ocr):
    twenty_mb = b"\xff\xd8\xff" + b"0" * (20 * 1024 * 1024)
    assert upload(client, user["user_id"], content=twenty_mb).status_code == 413


@pytest.mark.xfail(
    strict=True,
    reason="BUG: only the client-sent Content-Type is checked, not the file itself. A text file labelled "
    "image/jpeg reaches OCR. Check the file's magic bytes (JPEG starts FF D8 FF, PNG with 89 50 4E 47).",
)
def test_upload_text_file_pretending_to_be_image_is_400(client, user, fake_ocr):
    calls = fake_ocr()
    response = upload(client, user["user_id"], content=b"this is not an image", content_type="image/jpeg")
    assert response.status_code == 400
    assert calls == []
