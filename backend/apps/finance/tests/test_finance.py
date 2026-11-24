import os
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from apps.properties.models import Property, RoomType, Unit
from apps.bookings.models import Booking
from apps.bookings.services import BookingService
from apps.finance.models import Payment, Invoice
from apps.finance.services import FinanceService

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

    def test_invoice_immutability(self):
        """ISS-07: Modifications to issued invoices must be blocked"""
        self.booking.is_paid = True
        self.booking.save()

        inv = FinanceService.generate_invoice_for_booking(self.booking)
        
        # Attempt to tamper with total_amount
        inv.total_amount = Decimal("50.00")
        with self.assertRaises(ValidationError):
            inv.save()

    def test_invoice_cannot_be_generated_for_unpaid_booking(self):
        self.booking.is_paid = False
        self.booking.save()
        with self.assertRaises(ValidationError):
            FinanceService.generate_invoice_for_booking(self.booking)
