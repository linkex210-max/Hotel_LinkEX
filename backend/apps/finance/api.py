from ninja import Router
from typing import List
from datetime import date
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError
from apps.finance.models import Payment, Expense, OwnerStatement, Invoice, InvoiceIssuanceAttempt
from apps.finance.schemas import (
    PaymentIn, PaymentOut, ExpenseIn, StatementOut,
    InvoiceGenerateIn, InvoiceOut
)
from apps.finance.services import FinanceService
from apps.finance.tasks import enqueue_invoice_issuance
from apps.bookings.models import Booking
from apps.users.permissions import JWTAuth, has_property_scope

router = Router()
auth_security = JWTAuth()

@router.post("/payments", response={201: PaymentOut, 400: dict, 403: dict}, auth=auth_security)
def record_payment(request, data: PaymentIn):
    booking = get_object_or_404(Booking, id=data.booking_id)
    if booking.guest_id != request.user.id and not has_property_scope(request.user, booking.property_id, 'can_record_payments'):
        return 403, {"error": "Not allowed to pay this booking"}
    try:
        payment = FinanceService.record_payment_for_booking(
            booking=booking,
            amount=data.amount,
            method=data.method.value,
            transaction_reference=data.transaction_reference,
            notes=data.notes,
        )
    except ValidationError as exc:
        return 400, {"error": str(exc)}
    return 201, payment

@router.post("/invoices/generate", response={201: InvoiceOut, 400: dict, 403: dict}, auth=auth_security)
def generate_invoice(request, data: InvoiceGenerateIn):
    """إصدار فاتورة ضريبية رسمية للحجز (ZATCA Compliant)"""
    booking = get_object_or_404(Booking, id=data.booking_id)
    if not (has_property_scope(request.user, booking.property_id, 'can_issue_invoices') or booking.guest_id == request.user.id):
        return 403, {"error": "غير مصرح لك بإصدار هذه الفاتورة"}

    try:
        invoice = FinanceService.generate_invoice_for_booking(
            booking=booking,
            invoice_type=data.invoice_type.value,
            buyer_vat=data.buyer_vat_number
        )
    except ValidationError as exc:
        return 400, {"error": str(exc)}
    return 201, invoice

@router.get("/invoices/{invoice_number}", response={200: InvoiceOut, 404: dict, 403: dict}, auth=auth_security)
def get_invoice(request, invoice_number: str):
    """عرض الفاتورة الضريبية وبيانات التحقق الرقمي والـ QR"""
    invoice = get_object_or_404(Invoice, invoice_number=invoice_number)
    if invoice.booking.guest_id != request.user.id and not has_property_scope(request.user, invoice.booking.property_id, 'can_view_finance'):
        return 403, {"error": "Not allowed to view this invoice"}
    return 200, invoice

@router.post("/payments/{payment_id}/verify", response={200: dict, 400: dict, 403: dict}, auth=auth_security)
def verify_transfer_receipt(request, payment_id: int):
    """اعتماد سند أو إيصال تحويل بنكي بواسطة المحاسب"""
    payment = get_object_or_404(Payment, id=payment_id)
    if not has_property_scope(request.user, payment.booking.property_id, 'can_verify_payments'):
        return 403, {"error": "غير مصرح لك باعتماد السندات المالية"}

    try:
        FinanceService.verify_payment(payment.id, verified_by_user=request.user)
    except ValidationError as exc:
        return 400, {"error": str(exc)}
    return 200, {"message": "تم اعتماد السند المالي بنجاح"}

@router.post("/expenses", response={201: dict, 403: dict}, auth=auth_security)
def record_expense(request, data: ExpenseIn):
    """تسجيل مصروف تشغيلي على مبنى"""
    if not has_property_scope(request.user, data.property_id, 'can_record_expenses'):
        return 403, {"error": "غير مصرح لك بتسجيل مصروفات"}

    expense = Expense.objects.create(
        property_id=data.property_id,
        title=data.title,
        category=data.category.value,
        amount=data.amount,
        date_incurred=data.date_incurred,
        notes=data.notes,
        recorded_by=request.user
    )
    return 201, {"message": "تم تسجيل المصروف بنجاح", "expense_id": expense.id}

@router.post("/statements/generate", response={200: StatementOut, 400: dict, 403: dict}, auth=auth_security)
def generate_owner_statement(request, property_id: int, start_date: date, end_date: date):
    """توليد كشف حساب وإيرادات مالك العقار"""
    if not has_property_scope(request.user, property_id, 'can_generate_statements'):
        return 403, {"error": "غير مصرح لك باستخراج كشوفات الحساب"}

    try:
        statement = FinanceService.calculate_owner_statement(property_id, start_date, end_date)
    except ValidationError as exc:
        return 400, {"error": str(exc)}
    return 200, statement

@router.post("/statements/{statement_id}/settle", response={200: StatementOut, 400: dict, 403: dict}, auth=auth_security)
def settle_owner_statement(request, statement_id: int):
    """تسوية واعتماد كشف حساب مالك العقار"""
    statement = get_object_or_404(OwnerStatement, id=statement_id)
    if not has_property_scope(request.user, statement.property_id, 'can_settle_statements'):
        return 403, {"error": "غير مصرح لك بتسوية كشوفات الحساب"}

    try:
        statement = FinanceService.settle_owner_statement(statement.id)
    except ValidationError as exc:
        return 400, {"error": str(exc)}
    return 200, statement
