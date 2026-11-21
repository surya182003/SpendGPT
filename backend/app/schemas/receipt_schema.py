from datetime import date

from pydantic import BaseModel


class ReceiptItemOut(BaseModel):
    item_name: str
    normalized_name: str | None
    quantity: float
    unit_price: float


class ReceiptOut(BaseModel):
    transaction_id: int
    user_id: int
    merchant_name: str
    transaction_date: date
    total_amount: float
    category_id: int | None
    category_name: str | None
    items: list[ReceiptItemOut]


class ReceiptUploadResponse(ReceiptOut):
    # these come from the OCR validation step, so the user knows if they should double check it
    requires_review: bool
    validation_issues: list[str]
