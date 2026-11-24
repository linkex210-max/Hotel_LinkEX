from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from apps.properties.models import Property, RoomType, Unit, RoomTypeInventory, SeasonalPricing
from apps.bookings.models import Booking
from apps.bookings.services import BookingService

class BookingLifecycleTestCase(TestCase):
    def setUp(self):
        self.property = Property.objects.create(
            name="Test Grand Hotel",
            property_type=Property.PropertyType.HOTEL,
            city="Riyadh",
            address="King Fahd Road"
        )
        self.room_type = RoomType.objects.create(
            property=self.property,
            name="Deluxe King",
            base_price=Decimal("500.00"),
            capacity_adults=2
        )
        self.unit1 = Unit.objects.create(
            property=self.property,
            room_type=self.room_type,
            unit_number="101",
            status=Unit.Status.AVAILABLE
        )
        self.unit2 = Unit.objects.create(
            property=self.property,
            room_type=self.room_type,
            unit_number="102",
            status=Unit.Status.AVAILABLE
        )
        self.check_in = date.today() + timedelta(days=1)
        self.check_out = date.today() + timedelta(days=3)

    def test_no_show_releases_inventory_and_unit(self):
        """ISS-01: NO_SHOW must release booked rooms inventory and reset assigned unit to AVAILABLE"""
        booking_data = {
            "room_type_id": self.room_type.id,
            "unit_id": self.unit1.id,
            "guest_name": "Ahmed Ali",
            "guest_phone": "+966500000000",
            "check_in_date": self.check_in,
            "check_out_date": self.check_out,
        }
        booking = BookingService.create_booking_atomic(booking_data)
        
        # Verify initial inventory consumption
        inv = RoomTypeInventory.objects.get(room_type=self.room_type, date=self.check_in)
        self.assertEqual(inv.booked_rooms, 1)

        # Transition to CONFIRMED
        BookingService.transition_status(booking, Booking.Status.CONFIRMED)
        
        # Transition to NO_SHOW
        BookingService.transition_status(booking, Booking.Status.NO_SHOW, notes="Guest did not arrive")
        
        # Check inventory is released
        inv.refresh_from_db()
        self.assertEqual(inv.booked_rooms, 0, "NO_SHOW should release inventory booked_rooms")
        
        # Check unit status is released to AVAILABLE
        self.unit1.refresh_from_db()
        self.assertEqual(self.unit1.status, Unit.Status.AVAILABLE, "NO_SHOW should release unit status to AVAILABLE")

    def test_calculate_nightly_breakdown_rejects_invalid_dates(self):
        """ISS-13: calculate_nightly_breakdown must raise ValidationError if check_in >= check_out"""
        with self.assertRaises(ValidationError):
            BookingService.calculate_nightly_breakdown(self.room_type, self.check_out, self.check_in)
        
        with self.assertRaises(ValidationError):
            BookingService.calculate_nightly_breakdown(self.room_type, self.check_in, self.check_in)

    def test_assign_room_unit_revalidates_and_locks(self):
        """ISS-02: assign_room_unit must revalidate unit status inside lock and prevent assigning unavailable units"""
        booking_data = {
            "room_type_id": self.room_type.id,
            "guest_name": "Omar",
            "guest_phone": "+966511111111",
            "check_in_date": self.check_in,
            "check_out_date": self.check_out,
        }
        booking = BookingService.create_booking_atomic(booking_data)
        
        # Put unit in MAINTENANCE
        self.unit2.status = Unit.Status.MAINTENANCE
        self.unit2.save()
        
        with self.assertRaises(ValidationError):
            BookingService.assign_room_unit(booking, self.unit2)

    def test_seasonal_pricing_room_type_specificity_precedence(self):
        """ISS-04: RoomType-specific pricing rule must always take precedence over Property-wide rule"""
        # Create general property rule
        SeasonalPricing.objects.create(
            property=self.property,
            name="General Property Rule",
            start_date=self.check_in,
            end_date=self.check_out,
            fixed_price=Decimal("300.00"),
            is_active=True
        )
        # Create specific room type rule
        SeasonalPricing.objects.create(
            property=self.property,
            room_type=self.room_type,
            name="Specific Room Type Rule",
            start_date=self.check_in,
            end_date=self.check_out,
            fixed_price=Decimal("450.00"),
            is_active=True
        )
        calc = BookingService.calculate_nightly_breakdown(self.room_type, self.check_in, self.check_out)
        self.assertEqual(calc["nights_breakdown"][0]["rate"], 450.00, "Room type specific rule must take precedence")

