from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from decimal import Decimal
from datetime import date, datetime
import uuid

class PaymentIn(BaseModel):
    booking_id: int
    amount: Decimal = Field(gt=0)
    method: Literal["CARD", "TRANSFER", "CASH", "APPLE_PAY"] = "CARD"
    transaction_reference: Optional[str] = ""
    notes: Optional[str] = ""

class PaymentOut(BaseModel):
    id: int
    booking_id: int
    amount: Decimal
    method: str
    status: str
    transaction_reference: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class InvoiceGenerateIn(BaseModel):
    booking_id: int
    invoice_type: Optional[str] = "SIMPLIFIED"
    buyer_vat_number: Optional[str] = ""

class InvoiceOut(BaseModel):
    id: int
    invoice_number: str
    uuid: uuid.UUID
    invoice_type: str
    buyer_name: str
    buyer_vat_number: Optional[str]
    issue_date: datetime
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    line_items: List[Dict[str, Any]]
    qr_code_data: str
    invoice_hash: str

    class Config:
        from_attributes = True

class ExpenseIn(BaseModel):
    property_id: int
    title: str
    category: str = "MAINTENANCE"
    amount: Decimal = Field(gt=0)
    date_incurred: date
    notes: Optional[str] = ""

class StatementOut(BaseModel):
    id: int
    property_id: int
    period_start: date
    period_end: date
    total_revenue: Decimal
    total_expenses: Decimal
    management_commission: Decimal
    net_owner_payout: Decimal
    is_settled: bool
    settlement_date: Optional[date]

    class Config:
        from_attributes = True
