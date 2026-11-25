from ninja import Router, Query
from typing import List, Optional
from datetime import date
from django.shortcuts import get_object_or_404
from config.rate_limit import is_rate_limited
from apps.properties.models import Property, RoomType, Unit, RoomTypeInventory, SeasonalPricing
from apps.properties.schemas import (
    PropertyIn, PropertyOut, RoomTypeIn, RoomTypeOut,
    UnitIn, UnitOut, InventoryDayOut, PricingRuleSchema
)
from apps.users.permissions import JWTAuth, has_property_scope

router = Router()
auth_security = JWTAuth()

@router.get("/", response={200: List[PropertyOut], 429: dict})
def list_properties(
    request,
    city: Optional[str] = None,
    property_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """[PUBLIC ENDPOINT] عرض قائمة المباني والفنادق النشطة للنزلاء مع pagination وحماية rate limiting"""
    if is_rate_limited(request, "public_list_properties", limit=60, window_seconds=60):
        return 429, {"error": "Too many requests, please try again later"}
    qs = Property.objects.filter(is_active=True)
    if city:
        qs = qs.filter(city__icontains=city)
    if property_type:
        qs = qs.filter(property_type=property_type)
    return 200, list(qs[offset:offset + limit])

@router.post("/", response={201: PropertyOut, 403: dict}, auth=auth_security)
def create_property(request, data: PropertyIn):
    """إضافة مبنى أو فندق جديد (للمدراء فقط)"""
    if request.user.role != 'SUPER_ADMIN' and not request.user.is_superuser:
        return 403, {"error": "غير مصرح لك بإضافة مبنى"}
    payload = data.model_dump()
    payload["property_type"] = data.property_type.value
    payload["ownership_type"] = data.ownership_type.value
    prop = Property.objects.create(**payload)
    return 201, prop

# --- Room Types (فئات الغرف) ---

@router.get("/{property_id}/room-types", response={200: List[RoomTypeOut], 429: dict})
def list_room_types(
    request,
    property_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """[PUBLIC ENDPOINT] عرض فئات الغرف المتاحة في مبنى/فندق معين مع pagination وحماية rate limiting"""
    if is_rate_limited(request, "public_list_room_types", limit=60, window_seconds=60):
        return 429, {"error": "Too many requests, please try again later"}
    qs = RoomType.objects.filter(property_id=property_id, property__is_active=True, is_active=True)
    return 200, list(qs[offset:offset + limit])

@router.post("/room-types", response={201: RoomTypeOut, 403: dict}, auth=auth_security)
def create_room_type(request, data: RoomTypeIn):
    """إنشاء فئة غرفة جديدة (مثل ديلوكس، جناح عائلي)"""
    if not has_property_scope(request.user, data.property_id, 'can_manage_pricing'):
        return 403, {"error": "لا تملك صلاحية إدارة الغرف في هذا المبنى"}
    room_type = RoomType.objects.create(**data.model_dump())
    return 201, room_type

# --- Units (الغرف الفعلية) ---

@router.get("/{property_id}/units", response={200: List[UnitOut], 403: dict}, auth=auth_security)
def list_units(request, property_id: int, room_type_id: Optional[int] = None, status: Optional[str] = None):
    """عرض قائمة الوحدات والغرف الفعلية"""
    if not has_property_scope(request.user, property_id, 'can_manage_bookings'):
        return 403, {"error": "غير مصرح لك باستعراض غرف هذا المبنى"}
    qs = Unit.objects.filter(property_id=property_id, is_active=True)
    if room_type_id:
        qs = qs.filter(room_type_id=room_type_id)
    if status:
        qs = qs.filter(status=status)
    return 200, list(qs)

@router.post("/units", response={201: UnitOut, 400: dict, 403: dict}, auth=auth_security)
def create_unit(request, data: UnitIn):
    """إضافة غرفة أو وحدة سكنية برقمها الفعلي"""
    if not has_property_scope(request.user, data.property_id, 'can_manage_bookings'):
        return 403, {"error": "لا تملك صلاحية على هذا المبنى"}
    if data.room_type_id and not RoomType.objects.filter(id=data.room_type_id, property_id=data.property_id).exists():
        return 400, {"error": "Room type must belong to the selected property"}
    unit = Unit.objects.create(**data.model_dump())
    return 201, unit

# --- Inventory & Calendar (المخزون والتوفر اليومي O(1)) ---

@router.get("/room-types/{room_type_id}/inventory", response={200: List[InventoryDayOut], 403: dict}, auth=auth_security)
def get_room_type_inventory(request, room_type_id: int, start_date: date, end_date: date):
    """استعراض توفر وأسعار فئة الغرفة عبر التقويم اليومي السريع"""
    room_type = get_object_or_404(RoomType, id=room_type_id)
    if not has_property_scope(request.user, room_type.property_id, 'can_manage_bookings'):
        return 403, {"error": "غير مصرح لك باستعراض مخزون هذا المبنى"}
    inv = RoomTypeInventory.objects.filter(
        room_type_id=room_type_id,
        date__gte=start_date,
        date__lte=end_date
    ).order_by('date')
    return 200, list(inv)

@router.post("/pricing-rules", response={201: dict, 400: dict, 403: dict}, auth=auth_security)
def create_pricing_rule(request, data: PricingRuleSchema):
    """إنشاء قاعدة تسعير موسمي ديناميكي"""
    target_property_id = data.property_id
    if not target_property_id and data.room_type_id:
        rt = get_object_or_404(RoomType, id=data.room_type_id)
        target_property_id = rt.property_id

    if not target_property_id:
        return 400, {"error": "A property or room type is required for pricing rules"}
    if data.property_id and data.room_type_id and not RoomType.objects.filter(
        id=data.room_type_id, property_id=data.property_id
    ).exists():
        return 400, {"error": "Room type must belong to the selected property"}

    if target_property_id and not has_property_scope(request.user, target_property_id, 'can_manage_pricing'):
        return 403, {"error": "لا تملك صلاحية إدارة الأسعار على هذا المبنى"}
        
    rule = SeasonalPricing.objects.create(**data.model_dump())
    return 201, {"message": "تم إضافة قاعدة التسعير بنجاح", "rule_id": rule.id}
