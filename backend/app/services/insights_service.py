"""Financial insights and the AI advisor.

Every figure is calculated here in Python from the user's own rows in the
existing tables (users, transactions, categories, budgets). LM Studio is only
used to put those figures into plain language. It never calculates anything,
and a reply that quotes an amount or percentage that is not in the computed
figures is rejected in favour of a template explanation built from the same
figures. The template is also used when LM Studio is off or unreachable, so
insights always work.

What is computed
  income / spending   income = users.monthly_income x months covered (the
                      current month pro-rated); spending = sum of transactions
  categories          spend per category, share of total, highest categories,
                      essential vs discretionary (categories.spend_type)
  monthly pattern     spend per calendar month (empty months included), average
                      over complete months, trend, current-month pace
  budgets             each budget overlapping the period compared with the
                      spending in its own window and category (NULL = overall)
  savings             over-budget categories, large discretionary categories,
                      frequent small purchases, recurring discretionary payments
  recommendations     rule-based, prioritised, derived from the above

Income: transactions in SpendGPT are all spending, so income comes from
users.monthly_income. If it is not set, income-based figures are None and the
report says so instead of guessing.
"""
import calendar
import json
import logging
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.services.anomaly_service import month_label, shift_month
from app.services.lmstudio_service import LMStudioClient, LMStudioError

logger = logging.getLogger(__name__)

DEFAULT_MONTHS = 6
MAX_MONTHS = 24
TOP_CATEGORIES = 3
UNCATEGORISED = "Uncategorised"

BUDGET_WARNING_PCT = 80.0           # "at risk" once 80% of a budget is used
TREND_CHANGE_PCT = 10.0             # +/-10% vs earlier months counts as a trend
DISCRETIONARY_CUT_PCT = 20          # suggested cut for large discretionary categories
MIN_DISCRETIONARY_MONTHLY = 25.0    # only suggest cuts worth at least this per month
SMALL_PURCHASE_MAX = 12.0           # "small" purchase
SMALL_PURCHASE_MIN_COUNT = 6        # visits in the period before it counts as a habit
SMALL_PURCHASE_MIN_MONTHLY = 15.0
SMALL_PURCHASE_CUT_PCT = 50
MAX_SUBSCRIPTIONS = 3
UNCATEGORISED_NOTE_PCT = 20.0
ADVISOR_HISTORY_TURNS = 6
MAX_QUESTION_LENGTH = 500

_CURRENCY_SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$"}
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class UserNotFoundError(LookupError):
    pass


# -- report structure -------------------------------------------------------------------
@dataclass
class CategorySpend:
    category_id: int | None
    category_name: str
    spend_type: str | None          # essential | discretionary | None (uncategorised)
    total: float
    share_pct: float
    transaction_count: int
    monthly_average: float
    recurring_share_pct: float      # share of this category paid by recurring transactions


@dataclass
class MonthSpend:
    month: str                      # YYYY-MM
    label: str                      # November 2026
    total: float
    transaction_count: int
    complete: bool                  # False for the current, unfinished month


@dataclass
class MonthlyPattern:
    months: list[MonthSpend]
    average_complete_month: float | None
    highest_month: str | None
    lowest_month: str | None
    trend: str                      # increasing | decreasing | stable | not_enough_data
    trend_change_pct: float | None
    current_month_spent: float
    current_month_projected: float | None


@dataclass
class BudgetStatus:
    budget_id: int
    category_id: int | None
    category_name: str              # "All spending" for an overall budget
    start_date: date
    end_date: date
    amount_limit: float
    spent: float
    remaining: float
    used_pct: float
    projected: float | None         # projected spend at end_date (active budgets only)
    is_active: bool
    status: str                     # over | at_risk | on_track


@dataclass
class SavingsOpportunity:
    type: str                       # over_budget | discretionary_category | frequent_small_purchases | recurring_payment
    title: str
    explanation: str
    monthly_amount: float
    potential_monthly_saving: float
    category_name: str | None = None
    merchant_name: str | None = None


@dataclass
class Recommendation:
    priority: str                   # high | medium | low
    title: str
    detail: str


@dataclass
class InsightsReport:
    user_id: int
    currency: str
    period_start: date | None
    period_end: date
    months_covered: float
    history_status: str             # empty | limited | ok
    transaction_count: int
    total_income: float | None
    total_spent: float
    net: float | None
    savings_rate_pct: float | None
    monthly_income: float | None
    average_monthly_spend: float
    savings_goal: float | None
    essential_spent: float
    discretionary_spent: float
    uncategorised_spent: float
    categories: list[CategorySpend]
    top_categories: list[str]
    monthly: MonthlyPattern
    budgets: list[BudgetStatus]
    savings_opportunities: list[SavingsOpportunity]
    recommendations: list[Recommendation]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AIText:
    text: str
    source: str                     # llm | fallback
    reason: str | None = None       # why the fallback was used (LMStudioError.reason, unverified_figures, ...)

    def to_dict(self) -> dict:
        return asdict(self)


# -- small helpers ----------------------------------------------------------------------
def _r(value: float) -> float:
    return round(value + 0.0, 2)


def money(value: float, currency: str = "EUR") -> str:
    symbol = _CURRENCY_SYMBOLS.get(currency)
    return f"{symbol}{value:,.2f}" if symbol else f"{value:,.2f} {currency}"


def _month_key(day: date) -> tuple[int, int]:
    return day.year, day.month


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _spend_type(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    return value if value in ("essential", "discretionary") else None


def _months_between(start: date, today: date) -> float:
    """Calendar months from `start` (a 1st) to `today`; the current month counts pro-rata."""
    full = (today.year - start.year) * 12 + (today.month - start.month)
    return full + today.day / _days_in_month(today.year, today.month)


# -- calculations (pure: no database, no LLM) -------------------------------------------
def compute_insights(
    *,
    user_id: int,
    transactions: list,
    budgets: list,
    categories: dict[int, tuple[str, str | None]],
    today: date,
    months: int = DEFAULT_MONTHS,
    monthly_income: float | None = None,
    savings_goal: float | None = None,
    currency: str = "EUR",
) -> InsightsReport:
    """Build the insights report from plain objects.

    `transactions` are the user's transactions (objects with amount, merchant_name,
    transaction_date, category_id, is_recurring); any dated after `today` are ignored.
    Older ones are still used for budget windows that started before the period.
    `budgets` objects need budget_id, category_id, amount_limit, start_date, end_date.
    `categories` maps category_id -> (category_name, spend_type).
    """
    months = max(1, min(int(months), MAX_MONTHS))
    income = float(monthly_income) if monthly_income and float(monthly_income) > 0 else None
    goal = float(savings_goal) if savings_goal and float(savings_goal) > 0 else None
    fmt = lambda v: money(v, currency)  # noqa: E731

    dated = [t for t in transactions if t.transaction_date and t.transaction_date <= today]
    requested_start = date(*shift_month(today.year, today.month, -(months - 1)), 1)
    in_window = [t for t in dated if t.transaction_date >= requested_start]
    notes: list[str] = []

    if in_window:
        first = min(t.transaction_date for t in in_window)
        period_start = max(requested_start, first.replace(day=1))
        if period_start > requested_start:
            notes.append(f"Your transaction history starts in {month_label(first.year, first.month)}, "
                         f"so the analysis covers less than the requested {months} months.")
    else:
        period_start = None
    window = [t for t in in_window if period_start and t.transaction_date >= period_start]
    months_covered = _months_between(period_start, today) if period_start else 0.0

    # totals -----------------------------------------------------------------------
    total = sum(float(t.amount) for t in window)
    total_income = _r(income * months_covered) if income and months_covered else None
    net = _r(total_income - total) if total_income is not None else None
    savings_rate = _r(net / total_income * 100) if total_income else None
    # Averages use at least one month, so a few days of data don't extrapolate wildly.
    per_month = max(months_covered, 1.0)
    avg_monthly = _r(total / per_month) if window else 0.0

    # categories -------------------------------------------------------------------
    by_category: dict[int | None, list] = defaultdict(list)
    for t in window:
        key = t.category_id if t.category_id in categories else None
        by_category[key].append(t)
    category_rows = []
    split = {"essential": 0.0, "discretionary": 0.0}
    for category_id, rows in by_category.items():
        spent = sum(float(t.amount) for t in rows)
        name, raw_type = categories.get(category_id, (UNCATEGORISED, None))
        spend_type = _spend_type(raw_type)
        if spend_type:
            split[spend_type] += spent
        category_rows.append(CategorySpend(
            category_id=category_id, category_name=name, spend_type=spend_type, total=_r(spent),
            share_pct=_r(spent / total * 100) if total else 0.0, transaction_count=len(rows),
            monthly_average=_r(spent / per_month),
            recurring_share_pct=_r(sum(float(t.amount) for t in rows if getattr(t, "is_recurring", False))
                                   / spent * 100) if spent else 0.0,
        ))
    category_rows.sort(key=lambda c: (-c.total, c.category_name))
    top = [c.category_name for c in category_rows[:TOP_CATEGORIES]]

    monthly = _monthly_pattern(window, period_start, today)
    budget_rows = _budget_statuses(dated, budgets, categories, today, period_start)
    opportunities = _savings_opportunities(window, category_rows, budget_rows, per_month, fmt)

    uncategorised = next((c for c in category_rows if c.category_id is None), None)
    if uncategorised and uncategorised.share_pct >= UNCATEGORISED_NOTE_PCT:
        notes.append(f"{uncategorised.share_pct:.0f}% of your spending has no category, "
                     "so the category figures are incomplete.")
    if income is None:
        notes.append("Your monthly income is not set, so income, net and savings figures can't be calculated.")
    if not window:
        notes.append("No transactions in this period yet. Add transactions or upload receipts to get insights.")

    if not window:
        status = "empty"
    elif len(window) < 10 or months_covered < 2:
        status = "limited"
        notes.append("There is not much history yet, so these insights are a first impression.")
    else:
        status = "ok"

    report = InsightsReport(
        user_id=user_id, currency=currency, period_start=period_start, period_end=today,
        months_covered=round(months_covered, 2), history_status=status, transaction_count=len(window),
        total_income=total_income, total_spent=_r(total), net=net, savings_rate_pct=savings_rate,
        monthly_income=_r(income) if income else None, average_monthly_spend=avg_monthly,
        savings_goal=_r(goal) if goal else None, essential_spent=_r(split["essential"]),
        discretionary_spent=_r(split["discretionary"]), uncategorised_spent=uncategorised.total if uncategorised else 0.0,
        categories=category_rows, top_categories=top, monthly=monthly, budgets=budget_rows,
        savings_opportunities=opportunities, recommendations=[], notes=notes,
    )
    report.recommendations = _recommendations(report, fmt)
    return report


def _monthly_pattern(window: list, period_start: date | None, today: date) -> MonthlyPattern:
    current = _month_key(today)
    if period_start is None:
        return MonthlyPattern([], None, None, None, "not_enough_data", None, 0.0, None)

    totals: dict[tuple[int, int], list] = defaultdict(list)
    for t in window:
        totals[_month_key(t.transaction_date)].append(float(t.amount))

    months: list[MonthSpend] = []
    key = _month_key(period_start)
    while key <= current:
        amounts = totals.get(key, [])
        months.append(MonthSpend(month=f"{key[0]}-{key[1]:02d}", label=month_label(*key), total=_r(sum(amounts)),
                                 transaction_count=len(amounts), complete=key != current))
        key = shift_month(*key, 1)

    complete = [m for m in months if m.complete]
    average = _r(sum(m.total for m in complete) / len(complete)) if complete else None
    highest = max(complete, key=lambda m: m.total).month if complete else None
    lowest = min(complete, key=lambda m: m.total).month if complete else None

    trend, change = "not_enough_data", None
    if len(complete) >= 2:
        last = complete[-1].total
        earlier = sum(m.total for m in complete[:-1]) / (len(complete) - 1)
        if earlier > 0:
            change = _r((last - earlier) / earlier * 100)
            trend = "increasing" if change >= TREND_CHANGE_PCT else "decreasing" if change <= -TREND_CHANGE_PCT \
                else "stable"

    spent_now = months[-1].total
    projected = _r(spent_now / today.day * _days_in_month(*current)) if spent_now else None
    return MonthlyPattern(months, average, highest, lowest, trend, change, spent_now, projected)


def _budget_statuses(transactions: list, budgets: list, categories: dict, today: date,
                     period_start: date | None) -> list[BudgetStatus]:
    """Budgets that overlap the analysis period (or are active today), each compared with
    the spending inside its own date window and category."""
    since = period_start or today.replace(day=1)
    rows = []
    for budget in budgets:
        if budget.end_date < since or budget.start_date > today:
            continue
        window_end = min(budget.end_date, today)
        spent = sum(
            float(t.amount) for t in transactions
            if budget.start_date <= t.transaction_date <= window_end
            and (budget.category_id is None or t.category_id == budget.category_id)
        )
        limit = float(budget.amount_limit)
        active = budget.start_date <= today <= budget.end_date
        projected = None
        if active:
            elapsed = (today - budget.start_date).days + 1
            length = (budget.end_date - budget.start_date).days + 1
            projected = _r(spent / elapsed * length)
        used = spent / limit * 100 if limit else 0.0
        if spent > limit:
            status = "over"
        elif used >= BUDGET_WARNING_PCT or (projected is not None and projected > limit):
            status = "at_risk"
        else:
            status = "on_track"
        name = categories.get(budget.category_id, (UNCATEGORISED, None))[0] if budget.category_id else "All spending"
        rows.append(BudgetStatus(
            budget_id=budget.budget_id, category_id=budget.category_id, category_name=name,
            start_date=budget.start_date, end_date=budget.end_date, amount_limit=_r(limit), spent=_r(spent),
            remaining=_r(limit - spent), used_pct=_r(used), projected=projected, is_active=active, status=status,
        ))
    order = {"over": 0, "at_risk": 1, "on_track": 2}
    rows.sort(key=lambda b: (order[b.status], not b.is_active, -b.used_pct))
    return rows


def _savings_opportunities(window: list, category_rows: list[CategorySpend], budget_rows: list[BudgetStatus],
                           per_month: float, fmt) -> list[SavingsOpportunity]:
    if not window:
        return []
    found: list[SavingsOpportunity] = []

    for b in budget_rows:
        if not b.is_active or b.status == "on_track":
            continue
        overspend = (b.projected or b.spent) - b.amount_limit
        if overspend <= 0:
            continue
        found.append(SavingsOpportunity(
            type="over_budget", category_name=b.category_name,
            title=f"Bring {b.category_name} back within budget",
            explanation=(f"You have spent {fmt(b.spent)} of your {fmt(b.amount_limit)} {b.category_name} budget "
                         f"and are on course for {fmt(b.projected or b.spent)} by {b.end_date.isoformat()}."),
            monthly_amount=_r(b.projected or b.spent), potential_monthly_saving=_r(overspend),
        ))

    for c in category_rows:
        if c.spend_type != "discretionary" or c.monthly_average < MIN_DISCRETIONARY_MONTHLY:
            continue
        saving = c.monthly_average * DISCRETIONARY_CUT_PCT / 100
        found.append(SavingsOpportunity(
            type="discretionary_category", category_name=c.category_name,
            title=f"Trim {c.category_name} by {DISCRETIONARY_CUT_PCT}%",
            explanation=(f"{c.category_name} is non-essential and averages {fmt(c.monthly_average)} a month. "
                         f"Cutting it by {DISCRETIONARY_CUT_PCT}% would save about {fmt(saving)} a month."),
            monthly_amount=c.monthly_average, potential_monthly_saving=_r(saving),
        ))

    small: dict[str, list] = defaultdict(list)
    for t in window:
        if float(t.amount) <= SMALL_PURCHASE_MAX and not getattr(t, "is_recurring", False) and t.merchant_name:
            small[t.merchant_name.strip().lower()].append(t)
    for rows in small.values():
        monthly = sum(float(t.amount) for t in rows) / per_month
        if len(rows) < SMALL_PURCHASE_MIN_COUNT or monthly < SMALL_PURCHASE_MIN_MONTHLY:
            continue
        merchant = rows[-1].merchant_name.strip()
        saving = monthly * SMALL_PURCHASE_CUT_PCT / 100
        found.append(SavingsOpportunity(
            type="frequent_small_purchases", merchant_name=merchant,
            title=f"Small purchases at {merchant} add up",
            explanation=(f"{len(rows)} purchases of {fmt(SMALL_PURCHASE_MAX)} or less at {merchant}, about "
                         f"{fmt(monthly)} a month. Halving them would save about {fmt(saving)} a month."),
            monthly_amount=_r(monthly), potential_monthly_saving=_r(saving),
        ))

    discretionary_ids = {c.category_id for c in category_rows if c.spend_type == "discretionary"}
    recurring: dict[str, list] = defaultdict(list)
    for t in window:
        if getattr(t, "is_recurring", False) and t.category_id in discretionary_ids and t.merchant_name:
            recurring[t.merchant_name.strip().lower()].append(t)
    subscriptions = []
    for rows in recurring.values():
        latest = max(rows, key=lambda t: t.transaction_date)
        subscriptions.append((float(latest.amount), latest.merchant_name.strip()))
    for amount, merchant in sorted(subscriptions, reverse=True)[:MAX_SUBSCRIPTIONS]:
        found.append(SavingsOpportunity(
            type="recurring_payment", merchant_name=merchant,
            title=f"Review your {merchant} payment",
            explanation=(f"{merchant} is a recurring non-essential payment of {fmt(amount)}. "
                         f"If you don't use it much, cancelling would save {fmt(amount)} each time it renews."),
            monthly_amount=_r(amount), potential_monthly_saving=_r(amount),
        ))

    found.sort(key=lambda o: -o.potential_monthly_saving)
    return found


def _recommendations(r: InsightsReport, fmt) -> list[Recommendation]:
    recs: list[Recommendation] = []
    add = lambda p, t, d: recs.append(Recommendation(p, t, d))  # noqa: E731

    if r.history_status == "empty":
        add("high", "Add your spending",
            "There are no transactions in this period. Add transactions or upload receipts so SpendGPT can analyse them.")
        if r.monthly_income is None:
            add("low", "Set your monthly income", "Adding your monthly income lets SpendGPT work out what you save.")
        return recs

    if r.net is not None and r.net < 0:
        add("high", "You are spending more than you earn",
            f"You spent {fmt(r.total_spent)} against an income of {fmt(r.total_income)}, "
            f"a shortfall of {fmt(-r.net)}. Look at the savings ideas below first.")

    for b in r.budgets:
        if not b.is_active:
            continue
        if b.status == "over":
            add("high", f"{b.category_name} budget exceeded",
                f"You have spent {fmt(b.spent)} of {fmt(b.amount_limit)} ({b.used_pct:.0f}%), "
                f"{fmt(-b.remaining)} over, with the budget running until {b.end_date.isoformat()}.")
        elif b.status == "at_risk":
            pace = f" At this pace you'll reach {fmt(b.projected)}." if b.projected else ""
            add("medium", f"{b.category_name} budget at risk",
                f"You have used {b.used_pct:.0f}% ({fmt(b.spent)} of {fmt(b.amount_limit)}).{pace}")

    if r.savings_goal and r.monthly_income:
        surplus = r.monthly_income - r.average_monthly_spend
        if surplus < r.savings_goal:
            add("medium", "Behind your savings goal",
                f"You save about {fmt(max(surplus, 0))} a month on average, short of your "
                f"{fmt(r.savings_goal)} goal by {fmt(r.savings_goal - max(surplus, 0))}.")
        else:
            add("low", "On track for your savings goal",
                f"You save about {fmt(surplus)} a month on average, above your {fmt(r.savings_goal)} goal.")

    if r.monthly.trend == "increasing":
        add("medium", "Spending is rising",
            f"Last month was {r.monthly.trend_change_pct:.0f}% above your earlier monthly average.")

    best = next((o for o in r.savings_opportunities if o.type != "over_budget"), None)
    if best:
        add("medium", best.title, best.explanation)

    # Fixed recurring costs (rent, bills) don't benefit from a budget; suggest the biggest flexible one.
    flexible = next((c for c in r.categories if c.category_id is not None and c.recurring_share_pct < 50), None)
    if not any(b.is_active for b in r.budgets) and flexible:
        add("low", f"Set a budget for {flexible.category_name}",
            f"It is your biggest flexible category at {fmt(flexible.monthly_average)} a month, "
            "and you have no active budget.")

    if r.uncategorised_spent and r.total_spent and r.uncategorised_spent / r.total_spent * 100 >= UNCATEGORISED_NOTE_PCT:
        add("low", "Categorise your transactions",
            f"{fmt(r.uncategorised_spent)} of spending has no category, which makes these insights less precise.")

    if r.monthly_income is None:
        add("low", "Set your monthly income", "Adding your monthly income lets SpendGPT work out what you save.")

    recs.sort(key=lambda x: _PRIORITY_ORDER[x.priority])
    return recs


# -- database -------------------------------------------------------------------------
def build_user_insights(db: Session, user_id: int, *, today: date | None = None,
                        months: int = DEFAULT_MONTHS) -> InsightsReport:
    """Insights for one user, from that user's rows only."""
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(f"User {user_id} not found")
    today = today or date.today()
    months = max(1, min(int(months), MAX_MONTHS))

    period_start = date(*shift_month(today.year, today.month, -(months - 1)), 1)
    budgets = list(db.scalars(select(Budget).where(
        Budget.user_id == user_id, Budget.end_date >= period_start, Budget.start_date <= today,
    )))
    # Budget windows can start before the analysis period, so load from whichever is earlier.
    since = min([period_start] + [b.start_date for b in budgets])
    transactions = list(db.scalars(select(Transaction).where(
        Transaction.user_id == user_id, Transaction.transaction_date >= since, Transaction.transaction_date <= today,
    )))
    categories = {c.category_id: (c.category_name, c.spend_type) for c in db.scalars(select(Category))}

    return compute_insights(
        user_id=user_id, transactions=transactions, budgets=budgets, categories=categories, today=today,
        months=months, monthly_income=user.monthly_income, savings_goal=user.savings_goal,
        currency=user.base_currency or "EUR",
    )


# -- LM Studio: explanations and advisor ------------------------------------------------
_SYSTEM_PROMPT = (
    "You are SpendGPT, a friendly money assistant for a university student. "
    "You are given the student's spending figures as JSON. They were calculated by SpendGPT and are correct.\n"
    "Rules:\n"
    "- Use only the figures in the JSON. Do not calculate, estimate or invent any new numbers.\n"
    "- Quote amounts exactly as they appear, with the currency symbol.\n"
    "- Plain, encouraging language. No jargon, no investment or legal advice, no judgement.\n"
    "- If the data does not answer something, say so instead of guessing."
)
_AMOUNT_RE = re.compile(r"(?:[€£$]|\bEUR\b|\bGBP\b|\bUSD\b)\s?(\d[\d,]*(?:\.\d+)?)"
                        r"|(\d[\d,]*(?:\.\d+)?)\s?(?:€|\bEUR\b)", re.IGNORECASE)
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?%")


def llm_facts(report: InsightsReport) -> dict:
    """The figures sent to the model: aggregates only, no names, emails or raw transactions."""
    fmt = lambda v: money(v, report.currency) if v is not None else None  # noqa: E731
    m = report.monthly
    return {
        "currency": report.currency,
        "period": {"from": report.period_start.isoformat() if report.period_start else None,
                   "to": report.period_end.isoformat(), "months": report.months_covered},
        "history": report.history_status,
        "transactions": report.transaction_count,
        "income": fmt(report.total_income), "monthly_income": fmt(report.monthly_income),
        "spent": fmt(report.total_spent), "net": fmt(report.net),
        "savings_rate_pct": report.savings_rate_pct,
        "average_monthly_spend": fmt(report.average_monthly_spend),
        "monthly_savings_goal": fmt(report.savings_goal),
        "essential_spent": fmt(report.essential_spent), "discretionary_spent": fmt(report.discretionary_spent),
        "categories": [{"name": c.category_name, "type": c.spend_type, "spent": fmt(c.total),
                        "share_pct": c.share_pct, "per_month": fmt(c.monthly_average)} for c in report.categories],
        "top_categories": report.top_categories,
        "months": [{"month": x.label, "spent": fmt(x.total), "complete": x.complete} for x in m.months],
        "trend": m.trend, "trend_change_pct": m.trend_change_pct,
        "average_complete_month": fmt(m.average_complete_month),
        "this_month_so_far": fmt(m.current_month_spent), "this_month_projected": fmt(m.current_month_projected),
        "budgets": [{"category": b.category_name, "limit": fmt(b.amount_limit), "spent": fmt(b.spent),
                     "used_pct": b.used_pct, "projected": fmt(b.projected), "status": b.status,
                     "active": b.is_active, "ends": b.end_date.isoformat()} for b in report.budgets],
        "savings_opportunities": [{"idea": o.title, "detail": o.explanation,
                                   "saving_per_month": fmt(o.potential_monthly_saving)}
                                  for o in report.savings_opportunities],
        "recommendations": [{"priority": x.priority, "title": x.title, "detail": x.detail}
                            for x in report.recommendations],
        "notes": report.notes,
    }


def _allowed_numbers(facts) -> set[float]:
    found: set[float] = set()

    def walk(value):
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            found.add(float(value))
        elif isinstance(value, str):
            for match in re.finditer(r"\d[\d,]*(?:\.\d+)?", value):
                found.add(float(match.group().replace(",", "")))
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v)

    walk(facts)
    return found


def unsupported_figures(text: str, facts: dict) -> list[str]:
    """Amounts and percentages in `text` that don't match any figure in `facts` (rounding allowed)."""
    allowed = _allowed_numbers(facts)
    quoted = [m.group(1) or m.group(2) for m in _AMOUNT_RE.finditer(text)]
    quoted += [m.group(1) for m in _PERCENT_RE.finditer(text)]
    bad = []
    for raw in quoted:
        value = float(raw.replace(",", ""))
        if not any(abs(value - a) <= max(1.0, abs(a) * 0.01) for a in allowed):
            bad.append(raw)
    return bad


def fallback_explanation(report: InsightsReport) -> str:
    """Plain-language summary built only from the report (used when the LLM is unavailable)."""
    fmt = lambda v: money(v, report.currency)  # noqa: E731
    if report.history_status == "empty":
        return ("There are no transactions to analyse yet. Add your spending or upload a receipt and "
                "SpendGPT will show where your money goes.")
    parts = [f"Over the last {report.months_covered:.1f} months you spent {fmt(report.total_spent)} "
             f"across {report.transaction_count} transaction{'s' if report.transaction_count != 1 else ''}, about {fmt(report.average_monthly_spend)} a month."]
    if report.net is not None:
        if report.net >= 0:
            parts.append(f"Your income for the period was {fmt(report.total_income)}, leaving {fmt(report.net)}.")
        else:
            parts.append(f"That is {fmt(-report.net)} more than your income of {fmt(report.total_income)} "
                         "for the period.")
    if report.categories:
        top = report.categories[0]
        parts.append(f"Your biggest category is {top.category_name} at {fmt(top.total)} "
                     f"({top.share_pct:.0f}% of spending).")
    over = [b for b in report.budgets if b.is_active and b.status == "over"]
    risk = [b for b in report.budgets if b.is_active and b.status == "at_risk"]
    if over:
        parts.append("You are over budget on " + ", ".join(b.category_name for b in over) + ".")
    if risk:
        parts.append("Watch your " + ", ".join(b.category_name for b in risk) + " budget.")
    if report.recommendations:
        parts.append(f"Top suggestion: {report.recommendations[0].title}. {report.recommendations[0].detail}")
    return " ".join(parts)


def _explain_messages(report: InsightsReport) -> list[dict]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": (
            "Explain these figures to me in under 180 words: how much I spent and on what, how my months "
            "compare, how I'm doing against my budgets, and the two or three most useful things I could do. "
            "Plain text, no headings.\n\n" + json.dumps(llm_facts(report), ensure_ascii=False)
        )},
    ]


def _advisor_messages(report: InsightsReport, question: str, history: list[dict] | None) -> list[dict]:
    messages = [{"role": "system", "content": _SYSTEM_PROMPT + (
        "\n- Answer the student's question about their own money in under 150 words.\n\n"
        "Figures:\n" + json.dumps(llm_facts(report), ensure_ascii=False)
    )}]
    for turn in (history or [])[-ADVISOR_HISTORY_TURNS:]:
        role, content = turn.get("role"), str(turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:MAX_QUESTION_LENGTH * 4]})
    messages.append({"role": "user", "content": question})
    return messages


def _clean_question(question: str | None) -> str:
    question = (question or "").strip()
    if not question:
        raise ValueError("Please ask a question.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise ValueError(f"Questions can be at most {MAX_QUESTION_LENGTH} characters.")
    return question


def _advisor_fallback(report: InsightsReport, reason: str) -> str:
    intro = ("The AI advisor isn't available right now, so here is a summary of your figures instead."
             if reason != "unverified_figures" else
             "I couldn't give a reliable answer to that, so here is a summary of your figures instead.")
    return f"{intro} {fallback_explanation(report)}"


def _verified(report: InsightsReport, text: str, fallback) -> AIText:
    """Accept the model's reply only if every amount/percentage it quotes is in the report."""
    bad = unsupported_figures(text, llm_facts(report))
    if bad:
        logger.warning("LLM reply quoted figures not in the report (%s); using the fallback", ", ".join(bad[:5]))
        return AIText(fallback("unverified_figures"), "fallback", "unverified_figures")
    return AIText(text, "llm")


def _explain_fallback(report: InsightsReport):
    return lambda _reason: fallback_explanation(report)


def _explain_skip(report: InsightsReport, client) -> AIText | None:
    if report.history_status == "empty":
        return AIText(fallback_explanation(report), "fallback", "no_data")
    if client is None:
        return AIText(fallback_explanation(report), "fallback", "disabled")
    return None


def explain_insights(report: InsightsReport, client: LMStudioClient | None) -> AIText:
    """Plain-language explanation of the report (LM Studio, or the template fallback)."""
    skipped = _explain_skip(report, client)
    if skipped:
        return skipped
    try:
        text = client.chat(_explain_messages(report), temperature=0.3, max_tokens=400)
    except LMStudioError as exc:
        logger.info("Insight explanation unavailable: %s", exc.reason)
        return AIText(fallback_explanation(report), "fallback", exc.reason)
    return _verified(report, text, _explain_fallback(report))


async def aexplain_insights(report: InsightsReport, client: LMStudioClient | None) -> AIText:
    skipped = _explain_skip(report, client)
    if skipped:
        return skipped
    try:
        text = await client.achat(_explain_messages(report), temperature=0.3, max_tokens=400)
    except LMStudioError as exc:
        logger.info("Insight explanation unavailable: %s", exc.reason)
        return AIText(fallback_explanation(report), "fallback", exc.reason)
    return _verified(report, text, _explain_fallback(report))


def ask_advisor(report: InsightsReport, question: str, client: LMStudioClient | None,
                history: list[dict] | None = None) -> AIText:
    """Answer a question about the user's own finances. Raises ValueError for an empty/over-long question.

    `history` is the earlier chat as [{"role": "user"|"assistant", "content": str}]; only the
    last few turns are sent.
    """
    question = _clean_question(question)
    fallback = lambda reason: _advisor_fallback(report, reason)  # noqa: E731
    if client is None:
        return AIText(fallback("disabled"), "fallback", "disabled")
    try:
        text = client.chat(_advisor_messages(report, question, history), temperature=0.3, max_tokens=350)
    except LMStudioError as exc:
        logger.info("Advisor unavailable: %s", exc.reason)
        return AIText(fallback(exc.reason), "fallback", exc.reason)
    return _verified(report, text, fallback)


async def aask_advisor(report: InsightsReport, question: str, client: LMStudioClient | None,
                       history: list[dict] | None = None) -> AIText:
    question = _clean_question(question)
    fallback = lambda reason: _advisor_fallback(report, reason)  # noqa: E731
    if client is None:
        return AIText(fallback("disabled"), "fallback", "disabled")
    try:
        text = await client.achat(_advisor_messages(report, question, history), temperature=0.3, max_tokens=350)
    except LMStudioError as exc:
        logger.info("Advisor unavailable: %s", exc.reason)
        return AIText(fallback(exc.reason), "fallback", exc.reason)
    return _verified(report, text, fallback)
