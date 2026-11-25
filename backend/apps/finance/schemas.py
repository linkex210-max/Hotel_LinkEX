from enum import Enum
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import date, datetime
import uuid
from apps.finance.models import Payment, Invoice, Expense


class PaymentMethodEnum(str, Enum):
    CARD = Payment.PaymentMethod.CREDIT_CARD.value
    TRANSFER = Payment.PaymentMethod.BANK_TRANSFER.value
    CASH = Payment.PaymentMethod.CASH.value
    APPLE_PAY = Payment.PaymentMethod.APPLE_PAY.value


class InvoiceTypeEnum(str, Enum):
    SIMPLIFIED = Invoice.InvoiceType.SIMPLIFIED.value
    STANDARD = Invoice.InvoiceType.STANDARD.value


class ExpenseCategoryEnum(str, Enum):
    UTILITIES = Expense.Category.UTILITIES.value
    MAINTENANCE = Expense.Category.MAINTENANCE.value
    CLEANING = Expense.Category.CLEANING.value
    COMMISSION = Expense.Category.COMMISSION.value
    STAFF = Expense.Category.STAFF.value
    OTHER = Expense.Category.OTHER.value


class PaymentIn(BaseModel):
    booking_id: int
    amount: Decimal = Field(gt=0)
    method: PaymentMethodEnum = PaymentMethodEnum.CARD
    transaction_reference: str = ""
    notes: str = ""

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
    invoice_type: InvoiceTypeEnum = InvoiceTypeEnum.SIMPLIFIED
    buyer_vat_number: str = ""

    @model_validator(mode="after")
    def validate_zatca_vat_requirements(self):
        vat = self.buyer_vat_number.strip()
        self.buyer_vat_number = vat
        if vat and (len(vat) != 15 or not vat.isdigit() or not vat.startswith("3") or not vat.endswith("3")):
            raise ValueError("buyer_vat_number must be a 15-digit ZATCA VAT number starting and ending with 3")
        if self.invoice_type == InvoiceTypeEnum.STANDARD and not vat:
            raise ValueError("buyer_vat_number is required for STANDARD (B2B) invoices")
        return self

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
    category: ExpenseCategoryEnum = ExpenseCategoryEnum.MAINTENANCE
    amount: Decimal = Field(gt=0)
    date_incurred: date
    notes: str = ""

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
