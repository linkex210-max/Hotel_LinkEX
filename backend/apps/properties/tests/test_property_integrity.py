from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from apps.properties.models import Property, RoomType, Unit, RoomTypeInventory

class PropertyIntegrityTestCase(TestCase):
    def setUp(self):
        self.prop_a = Property.objects.create(name="Hotel A", city="Riyadh", address="Addr A")
        self.prop_b = Property.objects.create(name="Hotel B", city="Jeddah", address="Addr B")
        self.rt_a = RoomType.objects.create(
            property=self.prop_a,
            name="Deluxe A",
            base_price=Decimal("400.00")
        )
        self.rt_b = RoomType.objects.create(
            property=self.prop_b,
            name="Deluxe B",
            base_price=Decimal("600.00")
        )

    def test_unit_cannot_belong_to_mismatched_room_type(self):
        """ISS-03: A unit belonging to Property A cannot be assigned a room type belonging to Property B"""
        unit = Unit(
            property=self.prop_a,
            room_type=self.rt_b,  # Mismatched!
            unit_number="101"
        )
        with self.assertRaises(ValidationError):
            unit.clean()
        
        with self.assertRaises(ValidationError):
            unit.save()
