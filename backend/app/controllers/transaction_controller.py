
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction_schema import TransactionCreate, TransactionResponse


router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.post(
    "/",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED
)
def create_transaction(
    user_id: int,
    payload: TransactionCreate,
    db: Session = Depends(get_db)
):
    # Check whether the user exists
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "User not found"
        )

    transaction = Transaction(
        user_id=user_id,
        category_id=payload.category_id,
        amount=payload.amount,
        merchant_name=payload.merchant_name,
        transaction_date=payload.transaction_date,
        is_recurring=payload.is_recurring,
    )

    db.add(transaction)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Invalid category_id"
        ) from None

    db.refresh(transaction)

    return transaction


@router.get(
    "/user/{user_id}",
    response_model=list[TransactionResponse]
)
def get_user_transactions(
    user_id: int,
    db: Session = Depends(get_db)
):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "User not found"
        )

    statement = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.transaction_date.desc())
    )

    transactions = db.scalars(statement).all()

    return transactions


@router.get(
    "/{transaction_id}",
    response_model=TransactionResponse
)
def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db)
):
    transaction = db.get(Transaction, transaction_id)

    if transaction is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Transaction not found"
        )

    return transaction


@router.delete("/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db)
):
    transaction = db.get(Transaction, transaction_id)

    if transaction is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Transaction not found"
        )

    db.delete(transaction)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Transaction could not be deleted"
        ) from None

    return {"message": "Transaction deleted successfully"}
