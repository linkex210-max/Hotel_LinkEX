import base64
import os
from datetime import date, datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError
from apps.bookings.models import Booking
from apps.finance.models import Payment, Expense, OwnerStatement, Invoice
from apps.properties.models import Property, OwnerContract

def generate_zatca_tlv_qr(seller_name: str, vat_number: str, timestamp_str: str, total_str: str, vat_str: str) -> str:
    """
    توليد بيانات الباركود مشفرة بنظام TLV (Tag-Length-Value) Base64
    المعتمد من هيئة الزكاة والضريبة والجمارك (ZATCA - المرحلة الثانية)
    """
    def to_tlv(tag: int, value: str) -> bytes:
        v_bytes = value.encode('utf-8')
        length = len(v_bytes)
        return bytes([tag, length]) + v_bytes

    tlv_data = (
        to_tlv(1, seller_name) +
        to_tlv(2, vat_number) +
        to_tlv(3, timestamp_str) +
        to_tlv(4, total_str) +
        to_tlv(5, vat_str)
    )
    return base64.b64encode(tlv_data).decode('utf-8')


class InvoiceService:
    """
    خدمة إدارة دورة حياة الفواتير الضريبية (Create / Issue / Void / Verify / Report).
    """

    @staticmethod
    def create_and_issue_for_booking(
        booking: Booking,
        invoice_type: str = Invoice.InvoiceType.SIMPLIFIED,
        buyer_vat: str = "",
    ) -> Invoice:
        """
        إصدار فاتورة ضريبية رسمية محصنة من التعديل (ZATCA Compliant) مع ضمان الذرية Idempotency.
        """
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking.pk)
            existing_invoice = Invoice.objects.filter(booking_id=booking.id).first()
            if existing_invoice:
                return existing_invoice

            if not booking.is_paid:
                raise ValidationError("An invoice can only be issued after the booking is fully paid")

            if invoice_type == Invoice.InvoiceType.STANDARD and not buyer_vat:
                raise ValidationError("Buyer VAT number is required for STANDARD (B2B) invoices")

            seller_name = booking.property.name
            seller_vat = os.getenv("ZATCA_SELLER_VAT_NUMBER", "")
            if len(seller_vat) != 15 or not seller_vat.isdigit() or seller_vat[0] != "3" or seller_vat[-1] != "3":
                raise ValidationError("Configure a valid ZATCA_SELLER_VAT_NUMBER before issuing invoices")
            from django.utils import timezone
            timestamp_now = timezone.now()

            invoice_seq = f"INV-{timestamp_now.year}-{booking.id:06d}"

            line_items = [
                {
                    "description": f"إقامة في {booking.room_type.name if booking.room_type else 'وحدة سكنية'} - ليلة {night['date']}",
                    "rate": str(night["rate"]),
                    "quantity": 1,
                    "amount": str(night["rate"]),
                }
                for night in booking.nights_breakdown
            ]

            qr_code = generate_zatca_tlv_qr(
                seller_name=seller_name,
                vat_number=seller_vat,
                timestamp_str=timestamp_now.isoformat(),
                total_str=f"{Decimal(str(booking.total_amount)):.2f}",
                vat_str=f"{Decimal(str(booking.tax_amount)):.2f}",
            )

            invoice = Invoice.objects.create(
                booking=booking,
                invoice_number=invoice_seq,
                invoice_type=invoice_type,
                status=Invoice.Status.ISSUED,
                buyer_name=booking.guest_name,
                buyer_vat_number=buyer_vat or "",
                subtotal=booking.subtotal,
                tax_rate=getattr(booking, "tax_rate", Decimal("15.00")),
                tax_amount=booking.tax_amount,
                discount_amount=booking.discount_amount,
                total_amount=booking.total_amount,
                line_items=line_items,
                qr_code_data=qr_code,
                issued_at=timestamp_now,
            )
            return invoice

    @staticmethod
    def void_invoice(invoice: Invoice, reason: str) -> Invoice:
        """
        إبطال فاتورة مصدرة وفق سياسة واضحة مع تسجيل السبب وتاريخ الإبطال.
        """
        if not reason or not reason.strip():
            raise ValidationError("A clear void reason is required to void an issued invoice")
        with transaction.atomic():
            inv = Invoice.objects.select_for_update().get(pk=invoice.pk)
            if inv.status == Invoice.Status.VOIDED:
                raise ValidationError("Invoice is already voided")
            if inv.is_reported:
                raise ValidationError("Reported ZATCA invoices cannot be voided directly; issue a credit note instead")
            from django.utils import timezone
            inv.status = Invoice.Status.VOIDED
            inv.voided_at = timezone.now()
            inv.void_reason = reason.strip()
            inv._allow_void_transition = True
            inv.save(update_fields=["status", "voided_at", "void_reason"])
            return inv

    @staticmethod
    def mark_reported(invoice: Invoice) -> Invoice:
        """
        تحديث حالة الإبلاغ لهيئة الزكاة والضريبة مرة واحدة فقط.
        """
        with transaction.atomic():
            inv = Invoice.objects.select_for_update().get(pk=invoice.pk)
            if inv.is_reported:
                return inv
            inv.is_reported = True
            inv._allow_report_transition = True
            inv.save(update_fields=["is_reported"])
            return inv

    @staticmethod
    def verify_hash(invoice: Invoice) -> bool:
        """التحقق من مطابقة البصمة الرقمية المحفوظة مع محتوى الفاتورة."""
        return bool(invoice.invoice_hash) and invoice.generate_hash() == invoice.invoice_hash


class FinanceService:
    @staticmethod
    def record_payment_for_booking(
        booking: Booking,
        amount: Decimal,
        method: str,
        transaction_reference: str = "",
        notes: str = "",
    ) -> Payment:
        """تسجيل دفعة مالية ذرياً مع التحقق من حالة الحجز والرصيد المتبقي (مستقل عن HTTP)."""
        with transaction.atomic():
            locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)
            if locked_booking.status in [Booking.Status.CANCELLED, Booking.Status.NO_SHOW, Booking.Status.CHECKED_OUT]:
                raise ValidationError("Payments cannot be recorded for a cancelled, no-show, or already checked-out booking")
            if locked_booking.is_paid:
                raise ValidationError("Booking is already fully paid")

            paid = locked_booking.payments.filter(status=Payment.Status.COMPLETED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            pending = locked_booking.payments.filter(status=Payment.Status.PENDING).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            if amount <= 0 or amount + paid + pending > locked_booking.total_amount:
                raise ValidationError("Payment amount is invalid or exceeds the outstanding balance")

            return Payment.objects.create(
                booking=locked_booking,
                amount=amount,
                method=method,
                transaction_reference=transaction_reference,
                notes=notes,
                status=Payment.Status.PENDING,
            )

    @staticmethod
    def verify_payment(payment_id: int, verified_by_user=None) -> Payment:
        """اعتماد الدفعة المالية، تحديث حالة الحجز، وجدولة إصدار الفاتورة الضريبية."""
        from django.utils import timezone
        from apps.finance.models import InvoiceIssuanceAttempt
        from apps.finance.tasks import enqueue_invoice_issuance

        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment_id)
            booking = Booking.objects.select_for_update().get(pk=payment.booking_id)

            if payment.status != Payment.Status.PENDING:
                raise ValidationError("Only pending payments can be verified")
            if booking.status not in [Booking.Status.PENDING, Booking.Status.CONFIRMED]:
                raise ValidationError("Payments cannot be verified for a closed booking")

            payment.status = Payment.Status.COMPLETED
            payment.completed_at = timezone.now()
            payment.verified_by = verified_by_user
            payment.save(update_fields=["status", "completed_at", "verified_by"])

            total_paid = booking.payments.filter(status=Payment.Status.COMPLETED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            if total_paid >= booking.total_amount and not booking.is_paid:
                booking.is_paid = True
                booking.save(update_fields=["is_paid", "updated_at"])
                if booking.status == Booking.Status.PENDING:
                    from apps.bookings.services import BookingService
                    BookingService.transition_status(booking, Booking.Status.CONFIRMED, user=verified_by_user, notes="Payment verified")
                InvoiceIssuanceAttempt.objects.get_or_create(
                    booking=booking,
                    defaults={"status": InvoiceIssuanceAttempt.Status.PENDING},
                )
                booking_id_to_issue = booking.id
                transaction.on_commit(
                    lambda b_id=booking_id_to_issue: enqueue_invoice_issuance(b_id),
                )
            return payment

    @staticmethod
    def generate_invoice_for_booking(booking: Booking, invoice_type: str = Invoice.InvoiceType.SIMPLIFIED, buyer_vat: str = "") -> Invoice:
        return InvoiceService.create_and_issue_for_booking(
            booking=booking,
            invoice_type=invoice_type,
            buyer_vat=buyer_vat,
        )

    @staticmethod
    def calculate_owner_statement(property_id: int, period_start: date, period_end: date) -> OwnerStatement:
        """
        احتساب إيرادات ومصروفات وصافي مستحقات مالك العقار عن فترة محددة (Idempotent).

        القاعدة المحاسبية (Cash Basis - الأساس النقدي):
        - تُحتسب الإيرادات بناءً على تاريخ التحصيل والاعتماد الفعلي للدفعة (`Payment.completed_at`)
          للمدفوعات بحالة `COMPLETED` فقط.
        - لا تُحتسب المدفوعات بحالة `PENDING` أو `FAILED` أو `REFUNDED`.
        - يُمنع إعادة احتساب أو تعديل أي كشف تمت تسويته (`is_settled=True`).
        """
        if period_start > period_end:
            raise ValidationError("period_start must be on or before period_end")

        with transaction.atomic():
            prop = Property.objects.select_for_update().get(id=property_id)
            existing = OwnerStatement.objects.select_for_update().filter(
                property=prop,
                period_start=period_start,
                period_end=period_end,
            ).first()
            if existing and existing.is_settled:
                raise ValidationError("Settled owner statement cannot be modified")

            contract = OwnerContract.objects.filter(property=prop, is_active=True).first()
            commission_pct = contract.commission_percentage if contract else Decimal("15.00")

            revenue_agg = Payment.objects.filter(
                booking__property_id=property_id,
                status=Payment.Status.COMPLETED,
                completed_at__date__gte=period_start,
                completed_at__date__lte=period_end,
            ).aggregate(total=Sum('amount'))

            total_revenue = revenue_agg['total'] or Decimal("0.00")

            expense_agg = Expense.objects.filter(
                property_id=property_id,
                date_incurred__gte=period_start,
                date_incurred__lte=period_end,
            ).aggregate(total=Sum('amount'))

            total_expenses = expense_agg['total'] or Decimal("0.00")

            management_commission = (total_revenue * (commission_pct / Decimal("100.00"))).quantize(Decimal("0.01"))
            net_owner_payout = (total_revenue - total_expenses - management_commission).quantize(Decimal("0.01"))

            if existing:
                existing.contract = contract
                existing.total_revenue = total_revenue
                existing.total_expenses = total_expenses
                existing.management_commission = management_commission
                existing.net_owner_payout = net_owner_payout
                existing.save(update_fields=[
                    "contract", "total_revenue", "total_expenses",
                    "management_commission", "net_owner_payout",
                ])
                return existing

            return OwnerStatement.objects.create(
                property=prop,
                contract=contract,
                period_start=period_start,
                period_end=period_end,
                total_revenue=total_revenue,
                total_expenses=total_expenses,
                management_commission=management_commission,
                net_owner_payout=net_owner_payout,
            )

    @staticmethod
    def settle_owner_statement(statement_id: int, settlement_date: date | None = None) -> OwnerStatement:
        """اعتماد تسوية كشف حساب المالك ومنع تعديله لاحقاً."""
        from django.utils import timezone
        with transaction.atomic():
            stmt = OwnerStatement.objects.select_for_update().get(pk=statement_id)
            if stmt.is_settled:
                raise ValidationError("Owner statement is already settled")
            stmt.is_settled = True
            stmt.settlement_date = settlement_date or timezone.localdate()
            stmt.save(update_fields=["is_settled", "settlement_date"])
            return stmt
