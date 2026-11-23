from ninja import Router
from typing import List, Optional
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from apps.bookings.models import Booking
from apps.bookings.schemas import BookingIn, BookingOut, AvailabilityCheck, AssignRoomIn
from apps.bookings.services import BookingService
from apps.properties.models import RoomType, Unit
from apps.users.permissions import JWTAuth, has_property_scope

router = Router()
auth_security = JWTAuth()

@router.post("/check-availability")
def check_availability(request, data: AvailabilityCheck):
    """
    فحص توفر الغرف اليومي فائق السرعة O(1)
    """
    if data.room_type_id:
        rt = get_object_or_404(RoomType, id=data.room_type_id)
        is_avail = BookingService.is_room_type_available(
            room_type=rt,
            check_in=data.check_in_date,
            check_out=data.check_out_date,
            rooms_count=data.rooms_count
        )
        return {
            "room_type_id": rt.id,
            "room_type_name": rt.name,
            "available": is_avail
        }
        
    if data.property_id:
        room_types = RoomType.objects.filter(property_id=data.property_id, is_active=True)
        results = []
        for rt in room_types:
            avail = BookingService.is_room_type_available(
                room_type=rt,
                check_in=data.check_in_date,
                check_out=data.check_out_date,
                rooms_count=data.rooms_count
            )
            results.append({
                "room_type_id": rt.id,
                "room_type_name": rt.name,
                "base_price": float(rt.base_price),
                "available": avail
            })
        return {"property_id": data.property_id, "results": results}
        
    return {"error": "يجب تحديد إما room_type_id أو property_id"}

@router.post("/", response={201: BookingOut, 400: dict}, auth=auth_security)
def create_booking(request, data: BookingIn):
    """إنشاء حجز جديد للنزيل ذرياً مع منع الـ Double-Booking"""
    user = getattr(request, 'user', None)
    try:
        booking = BookingService.create_booking_atomic(data.model_dump(), user=user)
        return 201, booking
    except (ValueError, ValidationError, RoomType.DoesNotExist, Unit.DoesNotExist) as e:
        return 400, {"error": str(e)}

@router.post("/{booking_id}/assign-room", auth=auth_security)
def assign_room(request, booking_id: int, data: AssignRoomIn):
    """
    تسكين النزيل وتعيين رقم الغرفة الفعلي (بواسطة موظف الاستقبال)
    """
    booking = get_object_or_404(Booking, id=booking_id)
    if not has_property_scope(request.user, booking.property_id, 'can_manage_bookings'):
        return 403, {"error": "غير مصرح لك بإدارة غرف هذا الحجز"}
        
    unit = get_object_or_404(Unit, id=data.unit_id)
    try:
        BookingService.assign_room_unit(booking, unit, user=request.user)
    except ValidationError as exc:
        return 400, {"error": str(exc)}
    return {
        "message": f"تم تعيين الغرفة رقم {unit.unit_number} للحجز بنجاح",
        "unit_number": unit.unit_number
    }

@router.post("/{booking_id}/confirm", auth=auth_security)
def confirm_booking(request, booking_id: int):
    """تأكيد الحجز"""
    booking = get_object_or_404(Booking, id=booking_id)
    if not has_property_scope(request.user, booking.property_id, 'can_manage_bookings'):
        return 403, {"error": "غير مصرح لك بتأكيد هذا الحجز"}
        
    try:
        BookingService.transition_status(booking, Booking.Status.CONFIRMED, user=request.user, notes="Booking confirmed")
    except ValidationError as exc:
        return 400, {"error": str(exc)}
    return {"message": "تم تأكيد الحجز بنجاح", "status": booking.status}

@router.post("/{booking_id}/check-in", auth=auth_security)
def check_in(request, booking_id: int):
    """تسجيل دخول النزيل (Check-in) وتحديث حالة الغرفة لمشغولة"""
    booking = get_object_or_404(Booking, id=booking_id)
    if not has_property_scope(request.user, booking.property_id, 'can_manage_bookings'):
        return 403, {"error": "غير مصرح لك بإجراء تسجيل الدخول"}

    if not booking.unit:
        return 400, {"error": "يجب أولاً تعيين رقم الغرفة الفعلي للنزيل قبل عمل Check-in"}

    if not booking.is_paid:
        return 400, {"error": "Payment must be completed before check-in"}
        
    try:
        BookingService.transition_status(booking, Booking.Status.CHECKED_IN, user=request.user, notes="Guest checked in")
    except ValidationError as exc:
        return 400, {"error": str(exc)}
    return {"message": "تم تسجيل الدخول بنجاح", "unit_status": booking.unit.status}

@router.post("/{booking_id}/check-out", auth=auth_security)
def check_out(request, booking_id: int):
    """تسجيل خروج النزيل (Check-out) وتحويل الغرفة إلى وضع التنظيف"""
    booking = get_object_or_404(Booking, id=booking_id)
    if not has_property_scope(request.user, booking.property_id, 'can_manage_bookings'):
        return 403, {"error": "غير مصرح لك بإجراء تسجيل الخروج"}
        
    try:
        BookingService.transition_status(booking, Booking.Status.CHECKED_OUT, user=request.user, notes="Guest checked out")
    except ValidationError as exc:
        return 400, {"error": str(exc)}
    return {"message": "تم تسجيل الخروج بنجاح وتحويل الوحدة للتنظيف"}

@router.post("/{booking_id}/cancel", auth=auth_security)
def cancel_booking(request, booking_id: int, reason: Optional[str] = ""):
    """إلغاء الحجز وتحرير المخزون اليومي والغرفة"""
    booking = get_object_or_404(Booking, id=booking_id)
    is_owner = request.user.is_authenticated and booking.guest_id == request.user.id
    has_perm = has_property_scope(request.user, booking.property_id, 'can_manage_bookings')
    
    if not (is_owner or has_perm):
        return 403, {"error": "غير مصرح لك بإلغاء هذا الحجز"}
        
    try:
        BookingService.transition_status(booking, Booking.Status.CANCELLED, user=request.user, notes="Booking cancelled")
    except ValidationError as exc:
        return 400, {"error": str(exc)}
    return {"message": "تم إلغاء الحجز وتحرير المخزون بنجاح"}
