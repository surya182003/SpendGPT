from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """Mirrors the users table in database/seed_data.sql."""

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    base_currency: Mapped[str | None] = mapped_column(String(3), server_default="EUR")
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), server_default="0.00")
    savings_goal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), server_default="0.00")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())