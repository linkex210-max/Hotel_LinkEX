from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import date, datetime
from apps.bookings.models import Booking


class BookingSourceEnum(str, Enum):
    ONLINE = Booking.BookingSource.ONLINE.value
    MANUAL = Booking.BookingSource.MANUAL.value
    OTA = Booking.BookingSource.OTA.value


class AvailabilityCheck(BaseModel):
    property_id: Optional[int] = None
    room_type_id: Optional[int] = None
    check_in_date: date
    check_out_date: date
    rooms_count: int = Field(default=1, ge=1, le=20)

class BookingIn(BaseModel):
    room_type_id: int
    unit_id: Optional[int] = None  # اختياري في الفنادق، محدد في الشاليهات
    guest_name: str
    guest_phone: str
    guest_national_id: Optional[str] = ""
    check_in_date: date
    check_out_date: date
    source: BookingSourceEnum = BookingSourceEnum.ONLINE
    special_requests: Optional[str] = ""

class NightRateItem(BaseModel):
    date: str
    rate: Decimal

class BookingOut(BaseModel):
    id: int
    property_id: int
    room_type_id: Optional[int]
    unit_id: Optional[int]
    guest_name: str
    guest_phone: str
    check_in_date: date
    check_out_date: date
    total_nights: int
    nights_breakdown: List[Dict[str, Any]]
    base_rate: Decimal
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    status: str
    is_paid: bool
    created_at: datetime

    class Config:
        from_attributes = True

class AssignRoomIn(BaseModel):
    unit_id: int
    notes: Optional[str] = ""
