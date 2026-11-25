"""AI steps run when a transaction is saved (manual entry or receipt upload).

Both steps are best-effort: if one fails, it is logged and the transaction is
still saved, so the AI layer can never break the existing endpoints. Neither
step calls the LLM, so saving never waits on LM Studio.
"""
import logging

from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.services.anomaly_service import check_new_transaction, store_alerts
from app.services.categorization_service import categorize_receipt, categorize_transaction

logger = logging.getLogger(__name__)


def suggest_category_id(db: Session, user_id: int, merchant_name: str | None,
                        items: list[dict] | None = None) -> int | None:
    """category_id from history/rules/ML, or None when nothing is confident.

    The "Other" default is not applied automatically: the transaction stays
    uncategorised so the user can choose.
    """
    try:
        if items is not None:
            result = categorize_receipt(db, merchant_name, items, user_id=user_id)
        else:
            result = categorize_transaction(db, merchant_name, user_id=user_id)
    except Exception:  # noqa: BLE001 - categorisation must never block a save
        logger.exception("Automatic categorisation failed for user %s", user_id)
        return None
    return result.category_id if result.source != "default" else None


def check_and_store_alerts(db: Session, transaction: Transaction) -> int:
    """Store unusual-spending alerts for a just-saved transaction. Returns how many were created."""
    try:
        flags = check_new_transaction(db, transaction)
        return len(store_alerts(db, transaction.user_id, flags))
    except Exception:  # noqa: BLE001 - the transaction is already saved
        db.rollback()
        logger.exception("Anomaly check failed for transaction %s", transaction.transaction_id)
        return 0
