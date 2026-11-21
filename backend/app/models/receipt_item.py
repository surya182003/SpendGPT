from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReceiptItem(Base):
    """One product line from a receipt. Mirrors receipt_items in database/SpendGPT.sql."""

    __tablename__ = "receipt_items"

    item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.transaction_id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_name: Mapped[str] = mapped_column(String(150), nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    transaction = relationship("Transaction", back_populates="items")
