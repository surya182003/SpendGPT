# Endpoints for the AI / LLM side of the project.
# They return the receipts saved from OCR as plain JSON so the model can use them directly.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.receipt_schema import ReceiptOut

router = APIRouter(prefix="/api/ai", tags=["ai"])


# converts a saved transaction + its items into the json the AI model gets
def receipt_to_dict(transaction):
    items = []
    for item in transaction.items:
        items.append({
            "item_name": item.item_name,
            "normalized_name": item.normalized_name,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
        })

    category_name = None
    if transaction.category:
        category_name = transaction.category.category_name

    return {
        "transaction_id": transaction.transaction_id,
        "user_id": transaction.user_id,
        "merchant_name": transaction.merchant_name,
        "transaction_date": transaction.transaction_date,
        "total_amount": float(transaction.amount),
        "category_id": transaction.category_id,
        "category_name": category_name,
        "items": items,
    }


@router.get("/receipts/{transaction_id}", response_model=ReceiptOut)
def get_receipt(transaction_id: int, db: Session = Depends(get_db)):
    transaction = db.get(Transaction, transaction_id)

    if transaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found")

    return receipt_to_dict(transaction)


@router.get("/users/{user_id}/receipts", response_model=list[ReceiptOut])
def get_user_receipts(user_id: int, limit: int = 50, db: Session = Depends(get_db)):
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # only transactions with a receipt_hash came from an uploaded receipt
    statement = (
        select(Transaction)
        .where(Transaction.user_id == user_id, Transaction.receipt_hash.is_not(None))
        .order_by(Transaction.transaction_date.desc())
        .limit(limit)
    )
    transactions = db.scalars(statement).all()

    return [receipt_to_dict(t) for t in transactions]
