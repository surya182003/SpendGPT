from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

class TransactionCreate(BaseModel):
    merchant_name: str = Field(min_length=1, max_length=100, strip_whitespace=True)
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    transaction_date: date
    category_id: int | None = None
    is_recurring: bool = False

class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    user_id: int
    category_id: int | None
    amount: Decimal
    merchant_name: str
    transaction_date: date
    is_recurring: bool
    created_at: datetime | None
