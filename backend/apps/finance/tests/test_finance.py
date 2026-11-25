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
        inv.refresh_from_db()

        # 10. Tampering with invoice_number
        inv.invoice_number = "INV-FAKE-999"
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 11. Tampering with uuid
        import uuid as uuid_lib
        inv.uuid = uuid_lib.uuid4()
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 12. Tampering with issue_date
        from django.utils import timezone
        inv.issue_date = timezone.now() - timedelta(days=30)
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 13. Tampering with booking
        b2 = BookingService.create_booking_atomic({
            "room_type_id": self.room_type.id,
            "guest_name": "Other Guest",
            "guest_phone": "+966555555556",
            "check_in_date": self.check_in + timedelta(days=5),
            "check_out_date": self.check_out + timedelta(days=5),
        })
        inv.booking = b2
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 14. Tampering with tax_rate
        inv.tax_rate = Decimal("5.00")
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 15. Tampering with invoice_hash
        inv.invoice_hash = "0" * 64
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 16. Tampering with is_reported directly via save()
        inv.is_reported = True
        with self.assertRaises(ValidationError):
            inv.save()
        inv.refresh_from_db()

        # 17. Blocking QuerySet.update() and bulk_update() on Invoice
        with self.assertRaises(ValidationError):
            Invoice.objects.filter(pk=inv.pk).update(total_amount=Decimal("1.00"))
        with self.assertRaises(ValidationError):
            Invoice.objects.bulk_update([inv], ["total_amount"])

        # 18. Verify hash integrity and controlled InvoiceService transitions
        from apps.finance.services import InvoiceService
        self.assertTrue(InvoiceService.verify_hash(inv))
        InvoiceService.void_invoice(inv, reason="Duplicate test void")
        inv.refresh_from_db()
        self.assertEqual(inv.status, Invoice.Status.VOIDED)
        with self.assertRaises(ValidationError):
            InvoiceService.void_invoice(inv, reason="Void again")

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
            can_view_finance=True,
            can_record_payments=True,
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

    def test_issue_invoice_task_records_failure_and_retries(self):
        """Issue 3: Invoice issuance failures must be logged in InvoiceIssuanceAttempt and retried with backoff."""
        from unittest.mock import patch
        from celery.exceptions import Retry
        from apps.finance.models import InvoiceIssuanceAttempt
        from apps.finance.tasks import issue_invoice_for_booking, enqueue_invoice_issuance

        self.booking.is_paid = True
        self.booking.save(update_fields=["is_paid"])

        # 1. Transient failure -> marks RETRYING, records attempt & error, and invokes Celery retry
        with patch("apps.finance.tasks.InvoiceService.create_and_issue_for_booking", side_effect=RuntimeError("DB timeout")):
            with patch.object(issue_invoice_for_booking, "retry", side_effect=Retry("retrying")) as mock_retry:
                with self.assertRaises(Retry):
                    issue_invoice_for_booking(self.booking.id)
                mock_retry.assert_called_once()
                self.assertEqual(mock_retry.call_args.kwargs["countdown"], 60)

        attempt = InvoiceIssuanceAttempt.objects.get(booking=self.booking)
        self.assertEqual(attempt.status, InvoiceIssuanceAttempt.Status.RETRYING)
        self.assertEqual(attempt.attempts, 1)
        self.assertIn("DB timeout", attempt.last_error)

        # 2. Retry succeeds and is idempotent
        inv_id = issue_invoice_for_booking(self.booking.id)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, InvoiceIssuanceAttempt.Status.SUCCEEDED)
        self.assertEqual(attempt.last_error, "")
        self.assertEqual(attempt.attempts, 2)
        self.assertEqual(issue_invoice_for_booking(self.booking.id), inv_id)

        # 3. Broker enqueue failure must also be recorded instead of failing silently
        with patch("apps.finance.tasks.issue_invoice_for_booking.delay", side_effect=ConnectionError("Redis down")):
            enqueue_invoice_issuance(self.booking.id)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, InvoiceIssuanceAttempt.Status.FAILED)
        self.assertIn("Redis down", attempt.last_error)

    def test_schema_validation_enums_and_invoice_inputs(self):
        """Issues 4 & 5: Pydantic schemas must reject null/invalid enums and validate ZATCA buyer VAT."""
        from pydantic import ValidationError as PydanticValidationError
        from apps.finance.schemas import InvoiceGenerateIn, PaymentIn, ExpenseIn
        from apps.bookings.schemas import BookingIn
        from apps.properties.schemas import PropertyIn

        # Issue 4: InvoiceGenerateIn
        with self.assertRaises(PydanticValidationError):
            InvoiceGenerateIn(booking_id=1, invoice_type=None)
        with self.assertRaises(PydanticValidationError):
            InvoiceGenerateIn(booking_id=1, buyer_vat_number=None)
        with self.assertRaises(PydanticValidationError):
            InvoiceGenerateIn(booking_id=1, invoice_type="INVALID_TYPE")
        with self.assertRaises(PydanticValidationError):
            InvoiceGenerateIn(booking_id=1, invoice_type="SIMPLIFIED", buyer_vat_number="12345")
        with self.assertRaises(PydanticValidationError):
            InvoiceGenerateIn(booking_id=1, invoice_type="STANDARD", buyer_vat_number="")

        valid_simplified = InvoiceGenerateIn(booking_id=1, invoice_type="SIMPLIFIED", buyer_vat_number="")
        self.assertEqual(valid_simplified.invoice_type.value, "SIMPLIFIED")

        valid_standard = InvoiceGenerateIn(
            booking_id=1, invoice_type="STANDARD", buyer_vat_number="310000000000003"
        )
        self.assertEqual(valid_standard.invoice_type.value, "STANDARD")

        # Issue 5: Other unconstrained enums
        with self.assertRaises(PydanticValidationError):
            PaymentIn(booking_id=1, amount=Decimal("100.00"), method="CRYPTO")
        with self.assertRaises(PydanticValidationError):
            ExpenseIn(property_id=1, title="Test", category="UNKNOWN_CAT", amount=Decimal("10.00"), date_incurred=date.today())
        with self.assertRaises(PydanticValidationError):
            BookingIn(
                room_type_id=1, guest_name="A", guest_phone="050",
                check_in_date=self.check_in, check_out_date=self.check_out,
                source="WALKIN_INVALID",
            )
        with self.assertRaises(PydanticValidationError):
            PropertyIn(name="P", property_type="SPACESHIP", ownership_type="OWNED", city="Riyadh", address="A")
        with self.assertRaises(PydanticValidationError):
            PropertyIn(name="P", property_type="HOTEL", ownership_type="RENTED_INVALID", city="Riyadh", address="A")

    def test_decimal_precision_and_versioned_tax_rate(self):
        """Issues 6 & 7: No float imprecision in pricing/invoices and TaxRate changes must not mutate past invoices."""
        from apps.finance.models import TaxRate
        from apps.finance.services import InvoiceService

        # 1. Versioned TaxRate: 15% today, 20% starting in 30 days
        TaxRate.objects.create(
            name="Standard VAT 15%",
            rate_percentage=Decimal("15.00"),
            effective_from=date.today() - timedelta(days=30),
            effective_to=date.today() + timedelta(days=29),
        )
        TaxRate.objects.create(
            name="Future VAT 20%",
            rate_percentage=Decimal("20.00"),
            effective_from=date.today() + timedelta(days=30),
        )

        # Decimal-sensitive base price (0.10 + 0.20 type case: 100.10)
        rt_dec = RoomType.objects.create(
            property=self.property,
            name="Precision Suite",
            base_price=Decimal("100.10"),
        )
        Unit.objects.create(property=self.property, room_type=rt_dec, unit_number="599")

        b_current = BookingService.create_booking_atomic({
            "room_type_id": rt_dec.id,
            "guest_name": "Current Tax Guest",
            "guest_phone": "+966550000001",
            "check_in_date": date.today() + timedelta(days=1),
            "check_out_date": date.today() + timedelta(days=3),  # 2 nights = 200.20
        })
        self.assertEqual(b_current.subtotal, Decimal("200.20"))
        self.assertEqual(b_current.tax_rate, Decimal("15.00"))
        self.assertEqual(b_current.tax_amount, Decimal("30.03"))
        self.assertEqual(b_current.total_amount, Decimal("230.23"))
        # Canonical string in nights_breakdown (not float)
        self.assertIsInstance(b_current.nights_breakdown[0]["rate"], str)
        self.assertEqual(b_current.nights_breakdown[0]["rate"], "100.10")

        b_current.is_paid = True
        b_current.save(update_fields=["is_paid"])
        inv_current = InvoiceService.create_and_issue_for_booking(b_current)
        self.assertEqual(inv_current.tax_rate, Decimal("15.00"))
        self.assertEqual(inv_current.tax_amount, Decimal("30.03"))
        self.assertIsInstance(inv_current.line_items[0]["rate"], str)

        # Future booking uses 20% VAT without altering existing invoice!
        b_future = BookingService.create_booking_atomic({
            "room_type_id": rt_dec.id,
            "guest_name": "Future Tax Guest",
            "guest_phone": "+966550000002",
            "check_in_date": date.today() + timedelta(days=35),
            "check_out_date": date.today() + timedelta(days=36),  # 1 night = 100.10
        })
        self.assertEqual(b_future.tax_rate, Decimal("20.00"))
        self.assertEqual(b_future.tax_amount, Decimal("20.02"))
        self.assertEqual(b_future.total_amount, Decimal("120.12"))

        inv_current.refresh_from_db()
        self.assertEqual(inv_current.tax_rate, Decimal("15.00"))
        self.assertEqual(inv_current.total_amount, Decimal("230.23"))

    def test_owner_statement_idempotency_cash_basis_and_settlement_lock(self):
        """Issues 8 & 9: OwnerStatement must be idempotent, reject reversed periods/settled edits, and use Payment.completed_at (Cash Basis)."""
        from datetime import datetime
        from django.utils import timezone

        p_start = date.today() - timedelta(days=5)
        p_end = date.today()

        # 1. Reversed period must raise ValidationError
        with self.assertRaises(ValidationError):
            FinanceService.calculate_owner_statement(self.property.id, p_end, p_start)

        # 2. Cash Basis: PENDING, FAILED, REFUNDED, and out-of-range completed_at must be excluded
        Payment.objects.create(
            booking=self.booking, amount=Decimal("100.00"), status=Payment.Status.PENDING
        )
        Payment.objects.create(
            booking=self.booking, amount=Decimal("200.00"), status=Payment.Status.FAILED
        )
        Payment.objects.create(
            booking=self.booking, amount=Decimal("300.00"), status=Payment.Status.REFUNDED
        )
        # Completed BEFORE period_start (created_at is today, but completed_at is 20 days ago)
        out_of_range = Payment.objects.create(
            booking=self.booking,
            amount=Decimal("400.00"),
            status=Payment.Status.COMPLETED,
            completed_at=timezone.make_aware(datetime.combine(p_start - timedelta(days=10), datetime.min.time())),
        )
        # Completed INSIDE period
        in_range = Payment.objects.create(
            booking=self.booking,
            amount=Decimal("500.00"),
            status=Payment.Status.COMPLETED,
            completed_at=timezone.make_aware(datetime.combine(p_start + timedelta(days=1), datetime.min.time())),
        )

        stmt1 = FinanceService.calculate_owner_statement(self.property.id, p_start, p_end)
        self.assertEqual(stmt1.total_revenue, Decimal("500.00"))
        self.assertEqual(stmt1.management_commission, Decimal("75.00"))
        self.assertEqual(stmt1.net_owner_payout, Decimal("425.00"))

        # 3. Calling generate twice updates idempotently (no duplicate row)
        stmt2 = FinanceService.calculate_owner_statement(self.property.id, p_start, p_end)
        self.assertEqual(stmt1.id, stmt2.id)
        self.assertEqual(
            OwnerStatement.objects.filter(property=self.property, period_start=p_start, period_end=p_end).count(),
            1,
        )

        # 4. Settling statement locks it against further recalculation
        FinanceService.settle_owner_statement(stmt1.id)
        stmt1.refresh_from_db()
        self.assertTrue(stmt1.is_settled)
        with self.assertRaises(ValidationError):
            FinanceService.calculate_owner_statement(self.property.id, p_start, p_end)

    def test_finance_service_record_and_verify_payment_without_http(self):
        """Issue 15: Payment business logic works cleanly in service layer independent of HTTP."""
        from unittest.mock import patch
        from apps.finance.models import InvoiceIssuanceAttempt

        user = User.objects.create_user(email="svc_acct@hotel.com", password="Pass123!User")
        payment = FinanceService.record_payment_for_booking(
            booking=self.booking,
            amount=self.booking.total_amount,
            method=Payment.PaymentMethod.BANK_TRANSFER,
        )
        self.assertEqual(payment.status, Payment.Status.PENDING)

        with patch("apps.finance.tasks.enqueue_invoice_issuance"):
            verified = FinanceService.verify_payment(payment.id, verified_by_user=user)
        self.assertEqual(verified.status, Payment.Status.COMPLETED)
        self.assertIsNotNone(verified.completed_at)
        self.booking.refresh_from_db()
        self.assertTrue(self.booking.is_paid)
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)
        self.assertTrue(InvoiceIssuanceAttempt.objects.filter(booking=self.booking).exists())

    def test_upload_validation_blocks_spoofed_oversized_and_unsafe_files(self):
        """Security Audit #10: Upload fields must validate extension, size, and actual file content."""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        # 1. Disallowed extension (.html / .svg)
        bad_ext = SimpleUploadedFile("payload.html", b"<script>alert(1)</script>", content_type="text/html")
        exp_bad_ext = Expense(
            property=self.property, title="Test", amount=Decimal("10.00"),
            date_incurred=date.today(), invoice_file=bad_ext,
        )
        with self.assertRaises(ValidationError):
            exp_bad_ext.full_clean()

        # 2. Spoofed PDF extension (HTML disguised as .pdf)
        spoofed_pdf = SimpleUploadedFile("fake.pdf", b"<html>not a pdf</html>", content_type="application/pdf")
        exp_spoofed = Expense(
            property=self.property, title="Test", amount=Decimal("10.00"),
            date_incurred=date.today(), invoice_file=spoofed_pdf,
        )
        with self.assertRaises(ValidationError):
            exp_spoofed.full_clean()

        # 3. Spoofed image extension (non-image bytes disguised as .png)
        spoofed_img = SimpleUploadedFile("fake.png", b"not-an-image", content_type="image/png")
        pay_spoofed = Payment(
            booking=self.booking, amount=Decimal("50.00"), transfer_receipt=spoofed_img,
        )
        with self.assertRaises(ValidationError):
            pay_spoofed.full_clean()

        # 4. Oversized file (> 5MB)
        oversized = SimpleUploadedFile("big.pdf", b"%PDF-" + (b"0" * (5 * 1024 * 1024 + 10)), content_type="application/pdf")
        exp_big = Expense(
            property=self.property, title="Test", amount=Decimal("10.00"),
            date_incurred=date.today(), invoice_file=oversized,
        )
        with self.assertRaises(ValidationError):
            exp_big.full_clean()

        # 5. Valid PDF passes
        valid_pdf = SimpleUploadedFile("invoice.pdf", b"%PDF-1.4 valid content", content_type="application/pdf")
        exp_valid = Expense(
            property=self.property, title="Valid PDF", amount=Decimal("10.00"),
            date_incurred=date.today(), invoice_file=valid_pdf,
        )
        exp_valid.full_clean()

        # 6. Valid PNG image passes
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), color="red").save(buf, format="PNG")
        valid_png = SimpleUploadedFile("receipt.png", buf.getvalue(), content_type="image/png")
        pay_valid = Payment(
            booking=self.booking, amount=Decimal("50.00"), transfer_receipt=valid_png,
        )
        pay_valid.full_clean()
