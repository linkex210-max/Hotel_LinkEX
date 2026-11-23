from ninja import Router
from typing import List
from datetime import date
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError
from apps.finance.models import Payment, Expense, OwnerStatement, Invoice
from apps.finance.schemas import (
    PaymentIn, PaymentOut, ExpenseIn, StatementOut,
    InvoiceGenerateIn, InvoiceOut
)
from apps.finance.services import FinanceService
from apps.bookings.models import Booking
from apps.users.permissions import JWTAuth, has_property_scope

router = Router()
auth_security = JWTAuth()

@router.post("/payments", response={201: PaymentOut, 400: dict, 403: dict}, auth=auth_security)
def record_payment(request, data: PaymentIn):
    with transaction.atomic():
        booking = get_object_or_404(Booking.objects.select_for_update(), id=data.booking_id)
        if booking.guest_id != request.user.id and not has_property_scope(request.user, booking.property_id, 'can_view_finance'):
            return 403, {"error": "Not allowed to pay this booking"}
        paid = booking.payments.filter(status=Payment.Status.COMPLETED).aggregate(total=Sum("amount"))["total"] or 0
        pending = booking.payments.filter(status=Payment.Status.PENDING).aggregate(total=Sum("amount"))["total"] or 0
        if data.amount <= 0 or data.amount + paid + pending > booking.total_amount:
            return 400, {"error": "Payment amount is invalid or exceeds the outstanding balance"}
        payment = Payment.objects.create(
            booking=booking, amount=data.amount, method=data.method,
            transaction_reference=data.transaction_reference, notes=data.notes,
            status=Payment.Status.PENDING,
        )
    return 201, payment

@router.post("/invoices/generate", response={201: InvoiceOut, 400: dict, 403: dict}, auth=auth_security)
def generate_invoice(request, data: InvoiceGenerateIn):
    """إصدار فاتورة ضريبية رسمية للحجز (ZATCA Compliant)"""
    booking = get_object_or_404(Booking, id=data.booking_id)
    if not (has_property_scope(request.user, booking.property_id, 'can_view_finance') or booking.guest_id == request.user.id):
        return 403, {"error": "غير مصرح لك بإصدار هذه الفاتورة"}

    try:
        invoice = FinanceService.generate_invoice_for_booking(
            booking=booking,
            invoice_type=data.invoice_type,
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

@router.post("/payments/{payment_id}/verify", auth=auth_security)
def verify_transfer_receipt(request, payment_id: int):
    """اعتماد سند أو إيصال تحويل بنكي بواسطة المحاسب"""
    payment = get_object_or_404(Payment, id=payment_id)
    if not has_property_scope(request.user, payment.booking.property_id, 'can_view_finance'):
        return 403, {"error": "غير مصرح لك باعتماد السندات المالية"}

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=payment.booking_id)
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status != Payment.Status.PENDING:
            return 400, {"error": "Only pending payments can be verified"}
        if booking.status not in [Booking.Status.PENDING, Booking.Status.CONFIRMED]:
            return 400, {"error": "Payments cannot be verified for a closed booking"}
        payment.status = Payment.Status.COMPLETED
        payment.verified_by = request.user
        payment.save(update_fields=["status", "verified_by"])
        total_paid = booking.payments.filter(status=Payment.Status.COMPLETED).aggregate(total=Sum("amount"))["total"] or 0
        if total_paid >= booking.total_amount and not booking.is_paid:
            booking.is_paid = True
            booking.save(update_fields=["is_paid", "updated_at"])
            if booking.status == Booking.Status.PENDING:
                from apps.bookings.services import BookingService
                BookingService.transition_status(booking, Booking.Status.CONFIRMED, user=request.user, notes="Payment verified")
            transaction.on_commit(
                lambda: FinanceService.generate_invoice_for_booking(booking),
                robust=True,
            )
    return {"message": "تم اعتماد السند المالي بنجاح"}

@router.post("/expenses", auth=auth_security)
def record_expense(request, data: ExpenseIn):
    """تسجيل مصروف تشغيلي على مبنى"""
    if not has_property_scope(request.user, data.property_id, 'can_view_finance'):
        return 403, {"error": "غير مصرح لك بتسجيل مصروفات"}

    expense = Expense.objects.create(
        property_id=data.property_id,
        title=data.title,
        category=data.category,
        amount=data.amount,
        date_incurred=data.date_incurred,
        notes=data.notes,
        recorded_by=request.user
    )
    return {"message": "تم تسجيل المصروف بنجاح", "expense_id": expense.id}

@router.post("/statements/generate", response=StatementOut, auth=auth_security)
def generate_owner_statement(request, property_id: int, start_date: date, end_date: date):
    """توليد كشف حساب وإيرادات مالك العقار"""
    if not has_property_scope(request.user, property_id, 'can_view_finance'):
        return 403, {"error": "غير مصرح لك باستخراج كشوفات الحساب"}

    statement = FinanceService.calculate_owner_statement(property_id, start_date, end_date)
    return statement
