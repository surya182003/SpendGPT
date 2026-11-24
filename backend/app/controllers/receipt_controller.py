import hashlib
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.controllers.ai_controller import receipt_to_dict
from app.database import get_db
from app.models.receipt_item import ReceiptItem
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.receipt_schema import ReceiptUploadResponse
from app.services.ocr_service import read_receipt

router = APIRouter(prefix="/api/receipts", tags=["receipts"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

JPEG_SIGNATURE = b"\xff\xd8\xff"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@router.post("/upload", response_model=ReceiptUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_receipt(
    user_id: Annotated[int, Form(gt=0, le=2_147_483_647)],
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if file.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Please upload a JPEG or PNG image of the receipt",
        )

    # Read only up to 10 MB + 1 byte to detect oversized uploads.
    file_bytes = file.file.read(MAX_FILE_SIZE + 1)

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "File too large. Maximum upload size is 10 MB.",
        )

    if not file_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty")

    # Check the actual file signature instead of trusting the client.
    if file.content_type == "image/jpeg" and not file_bytes.startswith(JPEG_SIGNATURE):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JPEG image")

    if file.content_type == "image/png" and not file_bytes.startswith(PNG_SIGNATURE):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid PNG image")

    # Hash of the image so the same receipt doesn't get counted twice.
    receipt_hash = hashlib.sha256(file_bytes).hexdigest()
    already_saved = db.scalar(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.receipt_hash == receipt_hash,
        )
    )
    if already_saved:
        raise HTTPException(status.HTTP_409_CONFLICT, "This receipt was already uploaded")

    try:
        result = read_receipt(file_bytes, file.filename)
    except RuntimeError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Could not read the receipt: {e}",
        ) from None

    # Amount and date can't be empty in the transactions table.
    if result["total_amount"] is None or result["transaction_date"] is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {
                "message": "Could not find the total or the date on this receipt",
                "validation_issues": result["validation_issues"],
            },
        )

    merchant = result["merchant_name"]
    if not merchant:
        merchant = "Unknown"

    transaction = Transaction(
        user_id=user_id,
        amount=Decimal(str(result["total_amount"])),
        merchant_name=merchant[:100],
        transaction_date=date.fromisoformat(result["transaction_date"]),
        receipt_hash=receipt_hash,
    )

    for item in result["items"]:
        name = item["item_name"][:150]
        quantity = Decimal(str(item["quantity"]))
        price = Decimal(str(item["unit_price"]))

        receipt_item = ReceiptItem(
            item_name=name,
            normalized_name=name.strip().lower(),
            quantity=quantity,
            unit_price=price,
        )
        transaction.items.append(receipt_item)

    db.add(transaction)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This receipt was already uploaded") from None

    db.refresh(transaction)

    response = receipt_to_dict(transaction)
    response["requires_review"] = result["requires_review"]
    response["validation_issues"] = result["validation_issues"]
    return response
