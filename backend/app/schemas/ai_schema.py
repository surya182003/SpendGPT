"""Request/response schemas for the AI endpoints (/api/ai/*)."""
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

UserId = Annotated[int, Field(gt=0, le=2_147_483_647)]


# -- LM Studio ------------------------------------------------------------------------
class LMStudioStatusResponse(BaseModel):
    available: bool
    reason: str | None
    models: list[str]
    configured_model: str | None


# -- categorisation -------------------------------------------------------------------
class CategorizeRequest(BaseModel):
    merchant_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    user_id: UserId | None = Field(default=None, description="Use this user's earlier categorisations first")
    use_llm: bool = Field(default=False, description="Ask LM Studio when rules and the ML model are unsure")


class CategorizeResponse(BaseModel):
    category_id: int | None
    category_name: str | None  # None when nothing matched and the table has no "Other" row
    confidence: float
    source: Literal["history", "rule", "ml", "llm", "default"]
    reason: str


# -- anomalies and alerts -------------------------------------------------------------
class AnomalyFlagResponse(BaseModel):
    type: str
    severity: Literal["low", "medium", "high"]
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


class AnomalyScanResponse(BaseModel):
    flags: list[AnomalyFlagResponse]
    transactions_analysed: int
    history_status: Literal["ok", "limited", "insufficient"]
    notes: list[str]
    alerts_created: int


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: int
    user_id: int | None
    alert_type: str
    message: str
    is_read: bool | None
    related_transaction_id: int | None
    related_budget_id: int | None
    created_at: datetime | None


# -- insights -------------------------------------------------------------------------
class CategorySpendResponse(BaseModel):
    category_id: int | None
    category_name: str
    spend_type: str | None
    total: float
    share_pct: float
    transaction_count: int
    monthly_average: float
    recurring_share_pct: float


class MonthSpendResponse(BaseModel):
    month: str
    label: str
    total: float
    transaction_count: int
    complete: bool


class MonthlyPatternResponse(BaseModel):
    months: list[MonthSpendResponse]
    average_complete_month: float | None
    highest_month: str | None
    lowest_month: str | None
    trend: Literal["increasing", "decreasing", "stable", "not_enough_data"]
    trend_change_pct: float | None
    current_month_spent: float
    current_month_projected: float | None


class BudgetStatusResponse(BaseModel):
    budget_id: int
    category_id: int | None
    category_name: str
    start_date: date
    end_date: date
    amount_limit: float
    spent: float
    remaining: float
    used_pct: float
    projected: float | None
    is_active: bool
    status: Literal["over", "at_risk", "on_track"]


class SavingsOpportunityResponse(BaseModel):
    type: str
    title: str
    explanation: str
    monthly_amount: float
    potential_monthly_saving: float
    category_name: str | None = None
    merchant_name: str | None = None


class RecommendationResponse(BaseModel):
    priority: Literal["high", "medium", "low"]
    title: str
    detail: str


class AITextResponse(BaseModel):
    text: str
    source: Literal["llm", "fallback"]
    reason: str | None = None


class InsightsResponse(BaseModel):
    user_id: int
    currency: str
    period_start: date | None
    period_end: date
    months_covered: float
    history_status: Literal["empty", "limited", "ok"]
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
    categories: list[CategorySpendResponse]
    top_categories: list[str]
    monthly: MonthlyPatternResponse
    budgets: list[BudgetStatusResponse]
    savings_opportunities: list[SavingsOpportunityResponse]
    recommendations: list[RecommendationResponse]
    notes: list[str]
    explanation: AITextResponse | None = None


# -- advisor chat ---------------------------------------------------------------------
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(max_length=2000)]


class ChatRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    months: int = Field(default=6, ge=1, le=24)


class ChatResponse(BaseModel):
    answer: str
    source: Literal["llm", "fallback"]
    reason: str | None = None
