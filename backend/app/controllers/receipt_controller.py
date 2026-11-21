import hashlib
from datetime import date
from decimal import Decimal

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


@router.post("/upload", response_model=ReceiptUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_receipt(
    user_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please upload an image of the receipt")

    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty")

    # hash of the image so the same receipt doesn't get counted twice
    receipt_hash = hashlib.sha256(file_bytes).hexdigest()
    already_saved = db.scalar(
        select(Transaction).where(Transaction.user_id == user_id, Transaction.receipt_hash == receipt_hash)
    )
    if already_saved:
        raise HTTPException(status.HTTP_409_CONFLICT, "This receipt was already uploaded")

    try:
        result = read_receipt(file_bytes, file.filename)
    except RuntimeError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not read the receipt: {e}") from None

    # amount and date can't be empty in the transactions table
    if result["total_amount"] is None or result["transaction_date"] is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        # can still happen if the same receipt gets uploaded twice really fast
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This receipt was already uploaded") from None

    db.refresh(transaction)

    response = receipt_to_dict(transaction)
    response["requires_review"] = result["requires_review"]
    response["validation_issues"] = result["validation_issues"]
    return response
