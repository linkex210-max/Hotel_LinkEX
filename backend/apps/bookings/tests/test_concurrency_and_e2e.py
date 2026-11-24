import os
import threading
from decimal import Decimal
from datetime import date, timedelta
from django.test import TransactionTestCase
from django.db import connection
from apps.properties.models import Property, RoomType, Unit, RoomTypeInventory
from apps.bookings.models import Booking
from apps.bookings.services import BookingService
from apps.finance.models import Payment, Invoice
from apps.finance.services import FinanceService
from apps.users.models import User, UserPropertyScope
from apps.users.permissions import create_tokens

class ConcurrencyAndE2ETestCase(TransactionTestCase):
    """
    اختبارات التزامن الشديد ودورة الحياة الكاملة (Concurrency & E2E Verification)
    تستخدم TransactionTestCase لاختبار العمليات الحقيقية للـ DB Locks و Transactions
    """
    def setUp(self):
        os.environ["ZATCA_SELLER_VAT_NUMBER"] = "300000000000003"
        self.property = Property.objects.create(
            name="Concurrent Hotel",
            city="Riyadh",
            address="King Fahd Rd"
        )
        self.room_type = RoomType.objects.create(
            property=self.property,
            name="Single Only Room",
            base_price=Decimal("500.00"),
            capacity_adults=1
        )
        # Create only 1 unit - exactly 1 room capacity!
        self.unit = Unit.objects.create(
            property=self.property,
            room_type=self.room_type,
            unit_number="101",
            status=Unit.Status.AVAILABLE
        )
        self.check_in = date.today() + timedelta(days=5)
        self.check_out = date.today() + timedelta(days=6)

        # Manager user
        self.manager = User.objects.create_user(
            email="manager@concurrenthotel.com",
            password="ManagerPassword123!",
            role=User.Role.PROPERTY_MANAGER
        )
        UserPropertyScope.objects.create(
            user=self.manager,
            property=self.property,
            can_manage_bookings=True,
            can_manage_pricing=True,
            can_view_finance=True
        )

    def test_concurrent_booking_prevents_double_booking(self):
        """
        اختبار التزامن الشديد:
        محاولة حجزين متزامنين في نفس اللحظة للغرفة الوحيدة المتاحة.
        يجب أن ينجح حجز واحد فقط ويفشل الحجز الآخر بشكل نظيف لمنع الـ Overbooking.
        """
        results = []
        errors = []

        def attempt_booking(guest_name, guest_phone):
            # Close existing connection to force thread-specific connection
            connection.close()
            try:
                b = BookingService.create_booking_atomic({
                    "room_type_id": self.room_type.id,
                    "guest_name": guest_name,
                    "guest_phone": guest_phone,
                    "check_in_date": self.check_in,
                    "check_out_date": self.check_out,
                })
                results.append(b.id)
            except Exception as e:
                errors.append(str(e))
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt_booking, args=("Guest A", "+966500000001"))
        t2 = threading.Thread(target=attempt_booking, args=("Guest B", "+966500000002"))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly 1 booking succeeded
        self.assertEqual(len(results), 1, "Exactly one booking must succeed when 1 room is available")
        self.assertEqual(len(errors), 1, "The second concurrent booking must be rejected")
        
        # Check inventory is exactly 1 booked room
        inv = RoomTypeInventory.objects.get(room_type=self.room_type, date=self.check_in)
        self.assertEqual(inv.booked_rooms, 1)

    def test_full_lifecycle_e2e(self):
        """
        اختبار دورة الحياة الكاملة للحجز من البداية للنهاية:
        إنشاء حجز -> سداد دفعة -> اعتماد السند وتوليد الفاتورة -> تسكين الغرفة -> Check-in -> Check-out
        """
        # 1. إنشاء الحجز
        booking = BookingService.create_booking_atomic({
            "room_type_id": self.room_type.id,
            "guest_name": "Sultan",
            "guest_phone": "+966599999999",
            "check_in_date": self.check_in,
            "check_out_date": self.check_out,
        })
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertFalse(booking.is_paid)

        # 2. تسجيل دفعة مالية
        payment = Payment.objects.create(
            booking=booking,
            amount=booking.total_amount,
            method=Payment.PaymentMethod.BANK_TRANSFER,
            status=Payment.Status.PENDING
        )

        # 3. اعتماد الدفعة
        payment.status = Payment.Status.COMPLETED
        payment.verified_by = self.manager
        payment.save()
        booking.is_paid = True
        booking.save()
        BookingService.transition_status(booking, Booking.Status.CONFIRMED)

        # 4. إصدار فاتورة ضريبية ZATCA
        invoice = FinanceService.generate_invoice_for_booking(booking)
        self.assertIsNotNone(invoice.invoice_hash)
        self.assertEqual(invoice.total_amount, booking.total_amount)

        # 5. تعيين الغرفة الفعلية للنزيل
        BookingService.assign_room_unit(booking, self.unit, user=self.manager)
        booking.refresh_from_db()
        self.assertEqual(booking.unit_id, self.unit.id)

        # 6. Check-in
        BookingService.transition_status(booking, Booking.Status.CHECKED_IN, user=self.manager)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)

        # 7. Check-out
        BookingService.transition_status(booking, Booking.Status.CHECKED_OUT, user=self.manager)
        booking.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CHECKED_OUT)
        self.assertEqual(self.unit.status, Unit.Status.CLEANING)
