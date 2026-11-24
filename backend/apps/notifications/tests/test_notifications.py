from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from apps.properties.models import Property, RoomType, Unit
from apps.bookings.models import Booking
from apps.notifications.tasks import send_whatsapp_booking_alert
from apps.notifications.models import NotificationLog
from apps.users.models import User, UserPropertyScope

class NotificationTestCase(TestCase):
    def setUp(self):
        self.prop_a = Property.objects.create(name="Notification Hotel A", city="Riyadh", address="A1")
        self.prop_b = Property.objects.create(name="Notification Hotel B", city="Jeddah", address="B1")
        self.rt_a = RoomType.objects.create(property=self.prop_a, name="Standard A", base_price=Decimal("300.00"))
        self.unit_a = Unit.objects.create(property=self.prop_a, room_type=self.rt_a, unit_number="101")
        
        # Booking without assigned unit
        self.booking_no_unit = Booking.objects.create(
            property=self.prop_a,
            room_type=self.rt_a,
            unit=None,  # No unit assigned yet
            guest_name="Fahad",
            guest_phone="+966522222222",
            check_in_date=date.today() + timedelta(days=1),
            check_out_date=date.today() + timedelta(days=2),
            base_rate=Decimal("300.00"),
            subtotal=Decimal("300.00"),
            tax_amount=Decimal("45.00"),
            total_amount=Decimal("345.00"),
            status=Booking.Status.PENDING
        )

    def test_whatsapp_alert_handles_unassigned_unit_without_crashing(self):
        """ISS-10: send_whatsapp_booking_alert must not crash with AttributeError when unit is None"""
        result = send_whatsapp_booking_alert(self.booking_no_unit.id)
        # Should complete without throwing AttributeError
        log = NotificationLog.objects.filter(recipient=self.booking_no_unit.guest_phone).first()
        self.assertIsNotNone(log)
        self.assertIn("Fahad", log.body)

    def test_notification_logs_multi_tenant_isolation(self):
        """ISS-09: PROPERTY_MANAGER must only see notification logs for their assigned properties"""
        # Create notification logs for Property A and Property B
        log_a = NotificationLog.objects.create(
            property=self.prop_a,
            recipient="+966500000001",
            channel=NotificationLog.Channel.WHATSAPP,
            title="Alert A",
            body="Booking at Property A"
        )
        log_b = NotificationLog.objects.create(
            property=self.prop_b,
            recipient="+966500000002",
            channel=NotificationLog.Channel.WHATSAPP,
            title="Alert B",
            body="Booking at Property B"
        )

        manager_a = User.objects.create_user(
            email="manager_a@hotel.com",
            password="Password123!",
            role=User.Role.PROPERTY_MANAGER
        )
        UserPropertyScope.objects.create(user=manager_a, property=self.prop_a)

        from apps.notifications.api import list_notification_logs
        class DummyRequest:
            user = manager_a

        status, logs = list_notification_logs(DummyRequest())
        self.assertEqual(status, 200)
        log_ids = [l["id"] for l in logs]
        self.assertIn(log_a.id, log_ids, "Manager A must see Property A logs")
        self.assertNotIn(log_b.id, log_ids, "Manager A must NOT see Property B logs (multi-tenant leak prevented)")

