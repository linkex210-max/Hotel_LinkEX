from enum import Enum
from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime
from apps.properties.models import Property


class PropertyTypeEnum(str, Enum):
    HOTEL = Property.PropertyType.HOTEL.value
    APARTMENT_BUILDING = Property.PropertyType.APARTMENT_BUILDING.value
    CHALET = Property.PropertyType.CHALET.value
    VILLA = Property.PropertyType.VILLA.value


class OwnershipTypeEnum(str, Enum):
    OWNED = Property.OwnershipType.OWNED.value
    MANAGED = Property.OwnershipType.MANAGED.value


class PropertyIn(BaseModel):
    name: str
    property_type: PropertyTypeEnum = PropertyTypeEnum.HOTEL
    ownership_type: OwnershipTypeEnum = OwnershipTypeEnum.OWNED
    city: str
    address: str
    description: Optional[str] = ""

class PropertyOut(BaseModel):
    id: int
    name: str
    property_type: str
    ownership_type: str
    city: str
    address: str
    description: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class RoomTypeIn(BaseModel):
    property_id: int
    name: str
    code: Optional[str] = ""
    description: Optional[str] = ""
    base_price: Decimal
    capacity_adults: int = 2
    capacity_children: int = 1
    amenities: Optional[List[str]] = []

class RoomTypeOut(BaseModel):
    id: int
    property_id: int
    name: str
    code: str
    description: str
    base_price: Decimal
    capacity_adults: int
    capacity_children: int
    amenities: List[str]
    is_active: bool

    class Config:
        from_attributes = True

class UnitIn(BaseModel):
    property_id: int
    room_type_id: Optional[int] = None
    unit_number: str
    floor: int = 1
    base_price_override: Optional[Decimal] = None
    notes: Optional[str] = ""

class UnitOut(BaseModel):
    id: int
    property_id: int
    room_type_id: Optional[int]
    unit_number: str
    floor: int
    status: str
    base_price_override: Optional[Decimal]
    is_active: bool

    class Config:
        from_attributes = True

class InventoryDayOut(BaseModel):
    room_type_id: int
    date: date
    total_rooms: int
    booked_rooms: int
    available_rooms: int
    price: Decimal
    is_closed: bool

    class Config:
        from_attributes = True

class PricingRuleSchema(BaseModel):
    property_id: Optional[int] = None
    room_type_id: Optional[int] = None
    name: str
    start_date: date
    end_date: date
    price_multiplier: Optional[Decimal] = Decimal("1.00")
    fixed_price: Optional[Decimal] = None
