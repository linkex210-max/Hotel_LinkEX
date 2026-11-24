import os
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from apps.properties.models import Property, RoomType, Unit, OwnerContract
from apps.bookings.models import Booking
from apps.bookings.services import BookingService
from apps.finance.models import Payment, Invoice, Expense, OwnerStatement
from apps.finance.services import FinanceService
from apps.users.models import User, UserPropertyScope

class FinanceTestCase(TestCase):
    def setUp(self):
        os.environ["ZATCA_SELLER_VAT_NUMBER"] = "300000000000003"
        self.property = Property.objects.create(name="Finance Test Hotel", city="Riyadh", address="Al Olaya")
        self.room_type = RoomType.objects.create(
            property=self.property,
            name="Executive Suite",
            base_price=Decimal("1000.00")
        )
        self.unit = Unit.objects.create(
            property=self.property,
            room_type=self.room_type,
            unit_number="501"
        )
        self.check_in = date.today() + timedelta(days=2)
        self.check_out = date.today() + timedelta(days=3)
        self.booking = BookingService.create_booking_atomic({
            "room_type_id": self.room_type.id,
            "guest_name": "Khalid",
            "guest_phone": "+966555555555",
            "check_in_date": self.check_in,
            "check_out_date": self.check_out,
        })

    def test_invoice_generation_and_idempotency(self):
        """ISS-06: generate_invoice_for_booking must be idempotent and return existing invoice"""
        # Mark booking paid
        self.booking.is_paid = True
        self.booking.save()

        inv1 = FinanceService.generate_invoice_for_booking(self.booking)
        self.assertIsNotNone(inv1.invoice_hash)
        self.assertIsNotNone(inv1.qr_code_data)

        # Calling again should safely return the exact same invoice without creating a new one or crashing
        inv2 = FinanceService.generate_invoice_for_booking(self.booking)
        self.assertEqual(inv1.id, inv2.id)
        self.assertEqual(Invoice.objects.filter(booking=self.booking).count(), 1)

    def test_invoice_immutability_all_fields(self):
        """ISS-07: Modifications to issued invoices must be blocked across all financial and identity fields"""
        self.booking.is_paid = True
        self.booking.save()

        inv = FinanceService.generate_invoice_for_booking(self.booking)

        # 1. Tampering with total_amount
        inv.total_amount = Decimal("50.00")
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 2. Tampering with subtotal
        inv.subtotal = Decimal("100.00")
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 3. Tampering with tax_amount
        inv.tax_amount = Decimal("0.00")
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 4. Tampering with discount_amount
        inv.discount_amount = Decimal("500.00")
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 5. Tampering with buyer_name
        inv.buyer_name = "Fraudulent Buyer"
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 6. Tampering with buyer_vat_number
        inv.buyer_vat_number = "399999999999993"
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 7. Tampering with line_items
        inv.line_items = [{"fake": "item"}]
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 8. Tampering with qr_code_data
        inv.qr_code_data = "corrupted_qr"
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 9. Tampering with invoice_type
        inv.invoice_type = Invoice.InvoiceType.STANDARD
        with self.assertRaises(ValidationError):
            inv.save()

    def test_invoice_cannot_be_generated_for_unpaid_booking(self):
        self.booking.is_paid = False
        self.booking.save()
        with self.assertRaises(ValidationError):
            FinanceService.generate_invoice_for_booking(self.booking)

    def test_payment_blocked_on_cancelled_noshow_and_checked_out(self):
        """ISS-08: Payments cannot be recorded for CANCELLED, NO_SHOW, or CHECKED_OUT bookings"""
        from apps.finance.api import record_payment
        from apps.finance.schemas import PaymentIn

        user = User.objects.create_user(email="cashier@hotel.com", password="Pass123!User")
        UserPropertyScope.objects.create(
            user=user,
            property=self.property,
            can_view_finance=True
        )

        class MockRequest:
            def __init__(self, user):
                self.user = user

        request = MockRequest(user)
        payment_data = PaymentIn(
            booking_id=self.booking.id,
            amount=Decimal("100.00"),
            method=Payment.PaymentMethod.CASH
        )

        # 1. CANCELLED booking
        self.booking.status = Booking.Status.CANCELLED
        self.booking.save(update_fields=["status"])
        status, resp = record_payment(request, payment_data)
        self.assertEqual(status, 400)
        self.assertIn("cancelled", resp["error"].lower())

        # 2. NO_SHOW booking
        self.booking.status = Booking.Status.NO_SHOW
        self.booking.save(update_fields=["status"])
        status, resp = record_payment(request, payment_data)
        self.assertEqual(status, 400)
        self.assertIn("no-show", resp["error"].lower())

        # 3. CHECKED_OUT booking
        self.booking.status = Booking.Status.CHECKED_OUT
        self.booking.save(update_fields=["status"])
        status, resp = record_payment(request, payment_data)
        self.assertEqual(status, 400)
        self.assertIn("checked-out", resp["error"].lower())

    def test_db_constraints_enforce_data_integrity(self):
        """ISS-05: CheckConstraints at the database level must block invalid financial and booking records"""
        # 1. Expense amount > 0
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Expense.objects.create(
                    property=self.property,
                    title="Negative Expense",
                    category=Expense.Category.MAINTENANCE,
                    amount=Decimal("-50.00"),
                    date_incurred=date.today()
                )

        # 2. Booking subtotal >= 0
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Booking.objects.create(
                    property=self.property,
                    room_type=self.room_type,
                    guest_name="Test Guest",
                    guest_phone="+966500000000",
                    check_in_date=self.check_in,
                    check_out_date=self.check_out,
                    subtotal=Decimal("-10.00"),
                    tax_amount=Decimal("0.00"),
                    discount_amount=Decimal("0.00"),
                    total_amount=Decimal("0.00")
                )

        # 3. Invoice subtotal >= 0
        self.booking.status = Booking.Status.CONFIRMED
        self.booking.is_paid = True
        self.booking.save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.objects.create(
                    booking=self.booking,
                    invoice_number="INV-INVALID-001",
                    buyer_name="Invalid Buyer",
                    subtotal=Decimal("-100.00"),
                    tax_rate=Decimal("15.00"),
                    tax_amount=Decimal("0.00"),
                    discount_amount=Decimal("0.00"),
                    total_amount=Decimal("0.00")
                )

        # 4. OwnerStatement period_start <= period_end
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OwnerStatement.objects.create(
                    property=self.property,
                    period_start=date.today() + timedelta(days=10),
                    period_end=date.today(),  # End before start!
                    total_revenue=Decimal("1000.00"),
                    total_expenses=Decimal("200.00")
                )
