from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Transaction(Base):
    """Represents a user's financial transaction (one row per receipt)."""

    __tablename__ = "transactions"
    # same rule as SpendGPT.sql - a user can't save the same receipt twice
    __table_args__ = (UniqueConstraint("user_id", "receipt_hash", name="uq_user_receipt"),)

    transaction_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.category_id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(100), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    receipt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    items = relationship("ReceiptItem", back_populates="transaction", cascade="all, delete-orphan")
    category = relationship("Category")
