from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, TIMESTAMP, UniqueConstraint, func

from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Budget(Base):

    __tablename__ = "budgets"

    __table_args__ = (
        UniqueConstraint("user_id", "category_id", "start_date", name="uq_user_category_start"),
        Index("fk_budget_category_id", "category_id"),
    )

    budget_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"),nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.category_id", ondelete="SET NULL"),nullable=True)
    amount_limit: Mapped[Decimal] = mapped_column(Numeric(10, 2),nullable=False)
    start_date: Mapped[date] = mapped_column(Date,nullable=False)
    end_date: Mapped[date] = mapped_column(Date,nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP,server_default=func.current_timestamp(),nullable=False)