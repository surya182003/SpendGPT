"""Unusual-spending detection.

Student datasets are small, so this uses robust statistics rather than a model
that needs a lot of training data. Every flag carries a plain-language
explanation. Nothing here labels spending as fraud: a flag means "this is
unusual for you, worth a look", never "this is suspicious".

Checks
  amount_outlier     a transaction far above the user's usual amount in that
                     category (robust z-score from the median absolute deviation).
                     Categories with too little history are reported, not judged:
                     comparing e.g. rent with coffee would be meaningless
  possible_duplicate same merchant and amount on the same/next day (non-recurring,
                     and not a habitual same-price purchase such as a daily coffee)
  category_spike     this month's category spend well above its recent monthly average

Flags are stored as notifications in the existing alerts table
(alert_type: large_transaction, possible_duplicate, spending_spike).
"""
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.category import Category
from app.models.transaction import Transaction
from app.services.categorization_service import normalize_text

logger = logging.getLogger(__name__)

MIN_CATEGORY_HISTORY = 5    # earlier transactions in a category before it is judged on its own
ROBUST_Z_THRESHOLD = 3.5    # standard cut-off for MAD-based outliers (Iglewicz & Hoaglin, 1993)
MIN_OUTLIER_EXCESS = 15.0   # ignore "outliers" less than EUR 15 above the typical amount
DUPLICATE_WINDOW_DAYS = 1      # same or next day
HABITUAL_REPEATS = 3           # >= this many earlier identical amounts = a habit (daily coffee), not a duplicate
SPIKE_RATIO = 1.5
MIN_SPIKE_EXCESS = 30.0
SPIKE_LOOKBACK_MONTHS = 3
MIN_SPIKE_HISTORY_MONTHS = 2

ALERT_TYPES = {
    "amount_outlier": "large_transaction",
    "possible_duplicate": "possible_duplicate",
    "category_spike": "spending_spike",
}
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class AnomalyFlag:
    type: str
    severity: str  # low | medium | high
    message: str
    explanation: str
    transaction_id: int | None = None
    category_id: int | None = None
    category_name: str | None = None
    merchant_name: str | None = None
    amount: float | None = None
    typical_amount: float | None = None
    transaction_date: date | None = None
    month: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnomalyReport:
    flags: list[AnomalyFlag]
    transactions_analysed: int
    history_status: str  # ok | limited | insufficient
    notes: list[str] = field(default_factory=list)


def _eur(value: float) -> str:
    return f"€{value:,.2f}"


def _amount(txn) -> float:
    return float(txn.amount)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_label(year: int, month: int) -> str:
    return date(year, month, 1).strftime("%B %Y")


def robust_z_score(value: float, history: list[float], min_history: int) -> float | None:
    """0.6745 * (x - median) / MAD. None when there is too little history."""
    if len(history) < min_history:
        return None
    med = median(history)
    mad = median(abs(x - med) for x in history)
    if mad == 0:
        # Identical past amounts (e.g. a fixed bill): only a doubling counts as extreme.
        return float("inf") if value >= 2 * med and value - med >= MIN_OUTLIER_EXCESS else 0.0
    return 0.6745 * (value - med) / mad


# -- single transaction ------------------------------------------------------------------
def check_transaction(txn, history: list, category_names: dict[int, str] | None = None) -> list[AnomalyFlag]:
    """Flags for one transaction compared with the same user's *earlier* transactions.

    `history` must not contain `txn`. Objects only need amount, merchant_name,
    transaction_date, category_id, is_recurring and transaction_id attributes.
    """
    names = category_names or {}
    flags: list[AnomalyFlag] = []
    amount = _amount(txn)
    category = names.get(txn.category_id) if txn.category_id else None
    label = category or "uncategorised"
    merchant = txn.merchant_name or "an unknown merchant"

    same_category = [_amount(h) for h in history if h.category_id == txn.category_id]
    z = robust_z_score(amount, same_category, MIN_CATEGORY_HISTORY)
    if z is not None and z > ROBUST_Z_THRESHOLD:
        typical = median(same_category)
        if amount - typical >= MIN_OUTLIER_EXCESS:
            ratio = amount / typical if typical > 0 else float("inf")
            severity = "high" if ratio >= 4 else "medium" if ratio >= 2.5 else "low"
            times = f"{ratio:.1f}x" if ratio != float("inf") else "far above"
            flags.append(AnomalyFlag(
                type="amount_outlier",
                severity=severity,
                message=f"Unusually large {label} payment: {_eur(amount)} at {merchant}.",
                explanation=(
                    f"This is {times} your typical {label} spending of {_eur(typical)} "
                    f"(based on {len(same_category)} earlier transactions). It may be a planned one-off; "
                    "if you don't recognise it, check it against your bank statement."
                ),
                transaction_id=txn.transaction_id, category_id=txn.category_id, category_name=category,
                merchant_name=txn.merchant_name, amount=round(amount, 2), typical_amount=round(typical, 2),
                transaction_date=txn.transaction_date,
            ))

    key = normalize_text(txn.merchant_name)
    same_price = [
        h for h in history
        if key and normalize_text(h.merchant_name) == key and abs(_amount(h) - amount) < 0.005 and h.transaction_date
    ]
    if txn.transaction_date and not getattr(txn, "is_recurring", False) and len(same_price) < HABITUAL_REPEATS:
        for other in reversed(same_price):
            if abs((txn.transaction_date - other.transaction_date).days) <= DUPLICATE_WINDOW_DAYS:
                flags.append(AnomalyFlag(
                    type="possible_duplicate",
                    severity="medium",
                    message=f"Possible duplicate: {_eur(amount)} at {merchant} recorded twice.",
                    explanation=(
                        f"The same amount at the same merchant was also recorded on "
                        f"{other.transaction_date.isoformat()}. If you only paid once, delete one of them."
                    ),
                    transaction_id=txn.transaction_id, category_id=txn.category_id, category_name=category,
                    merchant_name=txn.merchant_name, amount=round(amount, 2),
                    transaction_date=txn.transaction_date,
                ))
                break
    return flags


# -- whole history ----------------------------------------------------------------------
def _category_spikes(transactions: list, today: date, names: dict[int, str]) -> tuple[list[AnomalyFlag], list[str]]:
    current = (today.year, today.month)
    previous = [shift_month(*current, -i) for i in range(1, SPIKE_LOOKBACK_MONTHS + 1)]
    totals: dict[tuple, dict[int | None, float]] = {}
    for txn in transactions:
        key = (txn.transaction_date.year, txn.transaction_date.month)
        if key == current or key in previous:
            bucket = totals.setdefault(key, {})
            bucket[txn.category_id] = bucket.get(txn.category_id, 0.0) + _amount(txn)

    history_months = [m for m in previous if m in totals]
    if len(history_months) < MIN_SPIKE_HISTORY_MONTHS:
        return [], [f"Monthly category comparisons need at least {MIN_SPIKE_HISTORY_MONTHS} earlier months of data."]

    flags = []
    for category_id, spent in totals.get(current, {}).items():
        average = sum(totals[m].get(category_id, 0.0) for m in history_months) / len(history_months)
        if spent - average < MIN_SPIKE_EXCESS or (average and spent / average < SPIKE_RATIO):
            continue
        label = names.get(category_id, "Uncategorised")
        ratio = spent / average if average else None
        severity = "medium" if ratio is None else "high" if ratio >= 2.5 else "medium" if ratio >= 1.8 else "low"
        compared = (
            f"{ratio:.1f}x your {len(history_months)}-month average of {_eur(average)}" if ratio
            else f"with nothing spent on it in the previous {len(history_months)} months"
        )
        flags.append(AnomalyFlag(
            type="category_spike",
            severity=severity,
            message=f"{label} spending in {month_label(*current)} is {_eur(spent)} so far.",
            explanation=f"That is already {compared}, and the month is not over yet.",
            category_id=category_id, category_name=names.get(category_id), amount=round(spent, 2),
            typical_amount=round(average, 2), month=f"{current[0]}-{current[1]:02d}",
        ))
    return flags, []


def detect_anomalies(
    transactions: list,
    *,
    category_names: dict[int, str] | None = None,
    today: date | None = None,
    lookback_days: int = 90,
) -> AnomalyReport:
    """Analyse one user's transactions. Only transactions in the lookback window are flagged,
    but all earlier ones are used as their history."""
    today = today or date.today()
    names = category_names or {}
    since = today - timedelta(days=lookback_days)
    ordered = sorted((t for t in transactions if t.transaction_date <= today),
                     key=lambda t: (t.transaction_date, t.transaction_id or 0))

    notes: list[str] = []
    if len(ordered) < MIN_CATEGORY_HISTORY:
        notes.append(
            f"Only {len(ordered)} transaction(s) recorded. Unusual-spending checks start after "
            f"{MIN_CATEGORY_HISTORY} transactions in a category."
        )
    flags: list[AnomalyFlag] = []
    for index, txn in enumerate(ordered):
        if txn.transaction_date >= since:
            flags.extend(check_transaction(txn, ordered[:index], names))

    counts: dict[int | None, int] = {}
    for txn in ordered:
        counts[txn.category_id] = counts.get(txn.category_id, 0) + 1
    thin = sorted(names.get(c, "Uncategorised") for c, n in counts.items() if n <= MIN_CATEGORY_HISTORY)
    if thin and len(ordered) >= MIN_CATEGORY_HISTORY:
        notes.append(f"Not enough history yet to judge unusual amounts in: {', '.join(thin)}.")

    spikes, spike_notes = _category_spikes(ordered, today, names)
    flags.extend(spikes)
    notes.extend(spike_notes)

    status = "insufficient" if len(ordered) < MIN_CATEGORY_HISTORY else "limited" if spike_notes else "ok"
    flags.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 3), -(f.amount or 0)))
    return AnomalyReport(flags=flags, transactions_analysed=len(ordered), history_status=status, notes=notes)


# -- database helpers -------------------------------------------------------------------
def category_name_map(db: Session) -> dict[int, str]:
    return {c.category_id: c.category_name for c in db.scalars(select(Category))}


def user_transactions(db: Session, user_id: int, until: date | None = None, days: int = 365) -> list[Transaction]:
    until = until or date.today()
    return list(db.scalars(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.transaction_date >= until - timedelta(days=days),
            Transaction.transaction_date <= until,
        )
    ))


def analyse_user(db: Session, user_id: int, *, today: date | None = None, lookback_days: int = 90) -> AnomalyReport:
    today = today or date.today()
    return detect_anomalies(user_transactions(db, user_id, today), category_names=category_name_map(db),
                            today=today, lookback_days=lookback_days)


def check_new_transaction(db: Session, txn: Transaction) -> list[AnomalyFlag]:
    """Flags for a just-saved transaction against the user's earlier transactions."""
    history = [
        t for t in db.scalars(
            select(Transaction).where(
                Transaction.user_id == txn.user_id,
                Transaction.transaction_id != txn.transaction_id,
                Transaction.transaction_date <= txn.transaction_date,
                Transaction.transaction_date >= txn.transaction_date - timedelta(days=365),
            )
        )
    ]
    history.sort(key=lambda t: (t.transaction_date, t.transaction_id))
    return check_transaction(txn, history, category_name_map(db))


def _alert_message(flag: AnomalyFlag) -> str:
    return f"{flag.message} {flag.explanation}"


def store_alerts(db: Session, user_id: int, flags: list[AnomalyFlag]) -> list[Alert]:
    """Save flags to the alerts table, skipping ones that were already stored.

    Transaction flags are deduplicated on (user, alert_type, transaction). Category
    spikes are deduplicated per user, category and month.
    """
    created = []
    for flag in flags:
        alert_type = ALERT_TYPES.get(flag.type)
        if alert_type is None:
            continue
        query = select(Alert.alert_id).where(Alert.user_id == user_id, Alert.alert_type == alert_type)
        if flag.transaction_id is not None:
            query = query.where(Alert.related_transaction_id == flag.transaction_id)
        elif flag.month:
            # "<Category> spending in <Month YYYY>" identifies the category and month.
            query = query.where(Alert.message.startswith(flag.message.split(" is ")[0]))
        if db.scalar(query.limit(1)) is not None:
            continue
        alert = Alert(user_id=user_id, alert_type=alert_type, message=_alert_message(flag), is_read=False,
                      related_transaction_id=flag.transaction_id)
        db.add(alert)
        created.append(alert)
    if created:
        db.commit()
        for alert in created:
            db.refresh(alert)
        logger.info("Stored %d anomaly alert(s) for user %s", len(created), user_id)
    return created
