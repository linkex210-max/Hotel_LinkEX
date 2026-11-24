import jwt
from ninja import Router
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from typing import List

from apps.users.models import User, UserPropertyScope, ActivityLog
from apps.users.schemas import LoginSchema, TokenOutSchema, RefreshTokenSchema, UserCreateSchema, UserOutSchema, PermissionUpdateSchema
from apps.users.permissions import JWTAuth, create_tokens

router = Router()
auth_security = JWTAuth()

@router.post("/login", response={200: TokenOutSchema, 401: dict}, auth=None)
def login(request, data: LoginSchema):
    """تسجيل الدخول وإصدار رموز JWT"""
    user = User.objects.filter(email=data.email).first()
    if not user or not user.check_password(data.password):
        return 401, {"message": "بيانات الدخول غير صحيحة"}
    
    if not user.is_active:
        return 401, {"message": "الحساب غير نشط"}
        
    access_token, refresh_token = create_tokens(user)
    
    # تسجيل الحركة
    ActivityLog.objects.create(
        user=user,
        action="LOGIN",
        details={"email": user.email}
    )
    
    return 200, {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/refresh", response={200: TokenOutSchema, 401: dict}, auth=None)
def refresh_token(request, data: RefreshTokenSchema):
    """تجديد رمز الدخول access_token باستخدام refresh_token"""
    try:
        payload = jwt.decode(
            data.refresh_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "refresh":
            return 401, {"message": "رمز التحديث غير صالح"}
        user_id = payload.get("user_id")
        user = User.objects.filter(id=user_id, is_active=True).first()
        if not user:
            return 401, {"message": "المستخدم غير موجود أو حسابه غير نشط"}
        access_token, new_refresh = create_tokens(user)
        return 200, {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "token_type": "bearer"
        }
    except (jwt.PyJWTError, Exception):
        return 401, {"message": "رمز التحديث منتهي الصلاحية أو غير صالح"}

@router.post("/register", response={201: UserOutSchema, 400: dict}, auth=None)
def register(request, data: UserCreateSchema):
    """إنشاء مستخدم جديد"""
    if User.objects.filter(email=data.email).exists():
        return 400, {"message": "البريد الإلكتروني مسجل مسبقاً"}
        
    try:
        validate_password(data.password)
    except ValidationError as exc:
        return 400, {"message": list(exc.messages)}

    user = User.objects.create_user(
        email=data.email,
        password=data.password,
        first_name=data.first_name,
        last_name=data.last_name,
        phone_number=data.phone_number,
        role=User.Role.GUEST
    )
    return 201, user

@router.get("/me", response=UserOutSchema, auth=auth_security)
def get_current_user(request):
    """الحصول على بيانات المستخدم الحالي"""
    return request.user

@router.get("/team", response=List[UserOutSchema], auth=auth_security)
def list_team_members(request):
    """عرض قائمة أعضاء الفريق"""
    if request.user.role == User.Role.SUPER_ADMIN or request.user.is_superuser:
        return User.objects.filter(role__in=[
            User.Role.PROPERTY_MANAGER, User.Role.RECEPTIONIST, User.Role.ACCOUNTANT
        ])
    if request.user.role != User.Role.PROPERTY_MANAGER:
        return []
    property_ids = request.user.property_scopes.values_list("property_id", flat=True)
    return User.objects.filter(property_scopes__property_id__in=property_ids, role__in=[
        User.Role.PROPERTY_MANAGER,
        User.Role.RECEPTIONIST,
        User.Role.ACCOUNTANT
    ]).distinct()

@router.post("/property-scope", response={200: dict, 403: dict}, auth=auth_security)
def assign_property_scope(request, data: PermissionUpdateSchema):
    """تحديد نطاق وصلاحيات مستخدم على مبنى معين"""
    if request.user.role != User.Role.SUPER_ADMIN and not request.user.is_superuser:
        return 403, {"error": "غير مصرح لك بتعديل النطاقات"}
        
    user = get_object_or_404(User, id=data.user_id)
    scope, created = UserPropertyScope.objects.update_or_create(
        user=user,
        property_id=data.property_id,
        defaults={
            "can_manage_bookings": data.can_manage_bookings,
            "can_manage_pricing": data.can_manage_pricing,
            "can_view_finance": data.can_view_finance
        }
    )
    return 200, {"message": "تم تحديث نطاق الصلاحيات بنجاح", "scope_id": scope.id}
