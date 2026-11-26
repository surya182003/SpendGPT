from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Alert(Base):
    """A notification for the user. Mirrors the existing alerts table in database/SpendGPT.sql.

    alert_type values in use: budget_exceeded, budget_warning, large_transaction
    (seed data) and, from the AI anomaly service, possible_duplicate, spending_spike.
    """

    __tablename__ = "alerts"

    alert_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool | None] = mapped_column(Boolean, default=False)
    related_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.transaction_id", ondelete="SET NULL"), nullable=True
    )
    related_budget_id: Mapped[int | None] = mapped_column(
        ForeignKey("budgets.budget_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=func.current_timestamp())
