from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReferencePrice(Base):
    """A shop's online price for a product on one day. Mirrors reference_prices in database/SpendGPT.sql.

    Rows from BasketWatch have source='basketwatch' and normalized_name is the cleaned
    receipt item name we searched for, so the same lookup can be reused that day.
    """

    __tablename__ = "reference_prices"

    ref_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_name: Mapped[str] = mapped_column(String(150), nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    retailer: Mapped[str | None] = mapped_column(String(80), nullable=True)
    unit_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    source: Mapped[str | None] = mapped_column(String(50), default="open_basket")
    observed_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
