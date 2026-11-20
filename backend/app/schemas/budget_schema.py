from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BudgetCreate(BaseModel):
    category_id: int | None = Field(default=None, gt=0)
    amount_limit: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be earlier than start date")
        return self


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    budget_id: int
    user_id: int
    category_id: int | None
    amount_limit: Decimal
    start_date: date
    end_date: date
    created_at: datetime