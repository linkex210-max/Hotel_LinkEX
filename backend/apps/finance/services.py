import base64
import os
from datetime import date, datetime
from decimal import Decimal
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


class FinanceService:
    @staticmethod
    def generate_invoice_for_booking(booking: Booking, invoice_type: str = Invoice.InvoiceType.SIMPLIFIED, buyer_vat: str = "") -> Invoice:
        """
        إصدار فاتورة ضريبية رسمية محصنة من التعديل (ZATCA Compliant)
        """
        # التحقق إذا كانت الفاتورة مصدرة مسبقاً
        if hasattr(booking, 'invoice'):
            return booking.invoice
        if not booking.is_paid:
            raise ValidationError("An invoice can only be issued after the booking is fully paid")

        seller_name = booking.property.name
        seller_vat = os.getenv("ZATCA_SELLER_VAT_NUMBER", "")
        if len(seller_vat) != 15 or not seller_vat.isdigit() or seller_vat[0] != "3" or seller_vat[-1] != "3":
            raise ValidationError("Configure a valid ZATCA_SELLER_VAT_NUMBER before issuing invoices")
        from django.utils import timezone
        timestamp_now = timezone.now()

        # توليد رقم تسلسلي فريد
        invoice_seq = f"INV-{timestamp_now.year}-{booking.id:06d}"

        # بنود الفاتورة اليومية
        line_items = [
            {
                "description": f"إقامة في {booking.room_type.name if booking.room_type else 'وحدة سكنية'} - ليلة {night['date']}",
                "rate": night["rate"],
                "quantity": 1,
                "amount": night["rate"]
            }
            for night in booking.nights_breakdown
        ]

        qr_code = generate_zatca_tlv_qr(
            seller_name=seller_name,
            vat_number=seller_vat,
            timestamp_str=timestamp_now.isoformat(),
            total_str=str(booking.total_amount),
            vat_str=str(booking.tax_amount)
        )

        invoice = Invoice.objects.create(
            booking=booking,
            invoice_number=invoice_seq,
            invoice_type=invoice_type,
            buyer_name=booking.guest_name,
            buyer_vat_number=buyer_vat,
            subtotal=booking.subtotal,
            tax_rate=Decimal("15.00"),
            tax_amount=booking.tax_amount,
            discount_amount=booking.discount_amount,
            total_amount=booking.total_amount,
            line_items=line_items,
            qr_code_data=qr_code
        )
        return invoice

    @staticmethod
    def calculate_owner_statement(property_id: int, period_start: date, period_end: date) -> OwnerStatement:
        """
        احتساب إيرادات ومصروفات وصافي مستحقات مالك العقار عن فترة محددة
        """
        prop = Property.objects.get(id=property_id)
        contract = OwnerContract.objects.filter(property=prop, is_active=True).first()

        commission_pct = contract.commission_percentage if contract else Decimal("15.00")

        revenue_agg = Payment.objects.filter(
            booking__property_id=property_id,
            status=Payment.Status.COMPLETED,
            created_at__date__gte=period_start,
            created_at__date__lte=period_end
        ).aggregate(total=Sum('amount'))

        total_revenue = revenue_agg['total'] or Decimal("0.00")

        expense_agg = Expense.objects.filter(
            property_id=property_id,
            date_incurred__gte=period_start,
            date_incurred__lte=period_end
        ).aggregate(total=Sum('amount'))

        total_expenses = expense_agg['total'] or Decimal("0.00")

        management_commission = (total_revenue * (commission_pct / Decimal("100.00"))).quantize(Decimal("0.01"))
        net_owner_payout = (total_revenue - total_expenses - management_commission).quantize(Decimal("0.01"))

        statement = OwnerStatement.objects.create(
            property=prop,
            contract=contract,
            period_start=period_start,
            period_end=period_end,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            management_commission=management_commission,
            net_owner_payout=net_owner_payout
        )

        return statement
