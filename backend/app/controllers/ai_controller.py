# Endpoints for the AI / LLM side of the project.
# They return the receipts saved from OCR as plain JSON so the model can use them directly.

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Path, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models.alert import Alert
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.ai_schema import (
    AlertResponse,
    AnomalyScanResponse,
    CategorizeRequest,
    CategorizeResponse,
    ChatRequest,
    ChatResponse,
    InsightsResponse,
    LMStudioStatusResponse,
    PriceComparisonResponse,
)
from app.schemas.receipt_schema import ReceiptOut
from app.services.anomaly_service import analyse_user, store_alerts
from app.services.basketwatch_service import (
    BasketWatchClient,
    BasketWatchError,
    compare_receipt,
    get_basketwatch_client,
)
from app.services.categorization_service import categorize_transaction
from app.services.insights_service import (
    UserNotFoundError,
    aask_advisor,
    aexplain_insights,
    build_user_insights,
)
from app.services.lmstudio_service import LMStudioClient, get_lmstudio_client

DbId = Annotated[int, Path(gt=0, le=2_147_483_647)]

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
def get_receipt(
    transaction_id: Annotated[int, Path(gt=0, le=2_147_483_647)],
    user_id: Annotated[int, Query(gt=0, le=2_147_483_647)],
    db: Session = Depends(get_db),
):
    statement = select(Transaction).where(
        Transaction.transaction_id == transaction_id,
        Transaction.user_id == user_id,
        Transaction.receipt_hash.is_not(None)
    )

    transaction = db.scalar(statement)

    if transaction is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Receipt not found"
        )

    return receipt_to_dict(transaction)


@router.get("/users/{user_id}/receipts", response_model=list[ReceiptOut])
def get_user_receipts(
    user_id: Annotated[int, Path(gt=0, le=2_147_483_647)],
    limit: Annotated[int, Query(ge=0, le=200)] = 50,
    db: Session = Depends(get_db),
):
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


@router.get("/receipts/{transaction_id}/price-comparison", response_model=PriceComparisonResponse)
def compare_receipt_prices(
    transaction_id: Annotated[int, Path(gt=0, le=2_147_483_647)],
    user_id: Annotated[int, Query(gt=0, le=2_147_483_647)],
    db: Session = Depends(get_db),
    basketwatch: BasketWatchClient = Depends(get_basketwatch_client),
):
    """Compares what was paid for each item with the supermarkets' online prices."""
    if not config.BASKETWATCH_ENABLED:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Price comparison is switched off")

    # same check as get_receipt: it has to be this user's uploaded receipt
    statement = select(Transaction).where(
        Transaction.transaction_id == transaction_id,
        Transaction.user_id == user_id,
        Transaction.receipt_hash.is_not(None)
    )
    transaction = db.scalar(statement)
    if transaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found")

    try:
        return compare_receipt(db, transaction, basketwatch)
    except BasketWatchError as error:
        db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Could not get prices from BasketWatch right now, please try again later",
        ) from error


def _require_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


# -- LM Studio ------------------------------------------------------------------------
@router.get("/status", response_model=LMStudioStatusResponse)
async def lmstudio_status(llm: LMStudioClient = Depends(get_lmstudio_client)):
    """Whether the local LLM is reachable. AI features still work (with fallbacks) when it isn't."""
    return await llm.astatus()


# -- categorisation -------------------------------------------------------------------
@router.post("/categorize", response_model=CategorizeResponse)
def categorize(
    payload: CategorizeRequest,
    db: Session = Depends(get_db),
    llm: LMStudioClient = Depends(get_lmstudio_client),
):
    """Suggest a category for a merchant/description. Nothing is saved."""
    if payload.user_id is not None:
        _require_user(db, payload.user_id)
    result = categorize_transaction(
        db, payload.merchant_name, payload.description,
        user_id=payload.user_id, client=llm, use_llm=payload.use_llm,
    )
    return result.to_dict()


# -- unusual spending and alerts ------------------------------------------------------
@router.post("/users/{user_id}/anomalies/scan", response_model=AnomalyScanResponse)
def scan_anomalies(
    user_id: DbId,
    lookback_days: Annotated[int, Query(ge=1, le=365)] = 90,
    db: Session = Depends(get_db),
):
    """Check the user's recent transactions and store new flags as alerts (no duplicates)."""
    _require_user(db, user_id)
    report = analyse_user(db, user_id, lookback_days=lookback_days)
    created = store_alerts(db, user_id, report.flags)
    return {
        "flags": [f.to_dict() for f in report.flags],
        "transactions_analysed": report.transactions_analysed,
        "history_status": report.history_status,
        "notes": report.notes,
        "alerts_created": len(created),
    }


@router.get("/users/{user_id}/alerts", response_model=list[AlertResponse])
def get_alerts(
    user_id: DbId,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    db: Session = Depends(get_db),
):
    _require_user(db, user_id)
    statement = select(Alert).where(Alert.user_id == user_id)
    if unread_only:
        statement = statement.where(Alert.is_read.is_not(True))
    statement = statement.order_by(Alert.created_at.desc(), Alert.alert_id.desc()).limit(limit)
    return db.scalars(statement).all()


@router.patch("/users/{user_id}/alerts/{alert_id}/read", response_model=AlertResponse)
def mark_alert_read(user_id: DbId, alert_id: DbId, db: Session = Depends(get_db)):
    alert = db.scalar(select(Alert).where(Alert.alert_id == alert_id, Alert.user_id == user_id))
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    alert.is_read = True
    db.commit()
    db.refresh(alert)
    return alert


# -- financial insights and advisor ---------------------------------------------------
async def _insights(db: Session, user_id: int, months: int):
    try:
        return await run_in_threadpool(build_user_insights, db, user_id, months=months)
    except UserNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found") from None


@router.get("/users/{user_id}/insights", response_model=InsightsResponse)
async def get_insights(
    user_id: DbId,
    months: Annotated[int, Query(ge=1, le=24)] = 6,
    explain: bool = True,
    db: Session = Depends(get_db),
    llm: LMStudioClient = Depends(get_lmstudio_client),
):
    """Figures calculated from the user's records, plus (optionally) a plain-language explanation."""
    report = await _insights(db, user_id, months)
    body = report.to_dict()
    body["explanation"] = (await aexplain_insights(report, llm)).to_dict() if explain else None
    return body


@router.post("/users/{user_id}/chat", response_model=ChatResponse)
async def chat_with_advisor(
    user_id: DbId,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    llm: LMStudioClient = Depends(get_lmstudio_client),
):
    """Ask the AI advisor about your own spending. Answers use only your calculated figures."""
    report = await _insights(db, user_id, payload.months)
    history = [turn.model_dump() for turn in payload.history]
    try:
        answer = await aask_advisor(report, payload.question, llm, history)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    return {"answer": answer.text, "source": answer.source, "reason": answer.reason}
