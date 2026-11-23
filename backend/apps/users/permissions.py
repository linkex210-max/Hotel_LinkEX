import jwt
from datetime import datetime, timedelta, timezone
from django.conf import settings
from ninja.security import HttpBearer
from apps.users.models import User, UserPropertyScope

class JWTAuth(HttpBearer):
    def authenticate(self, request, token):
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            if payload.get("type") != "access":
                return None
            user_id = payload.get("user_id")
            if not user_id:
                return None
            user = User.objects.filter(id=user_id, is_active=True).first()
            if user:
                request.user = user
                return user
        except (jwt.PyJWTError, Exception):
            return None
        return None

def create_tokens(user: User):
    now = datetime.now(timezone.utc)
    access_exp = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_LIFETIME_MINUTES)
    refresh_exp = now + timedelta(days=settings.JWT_REFRESH_TOKEN_LIFETIME_DAYS)

    access_payload = {
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
        "exp": int(access_exp.timestamp()),
        "type": "access",
    }
    refresh_payload = {
        "user_id": user.id,
        "exp": int(refresh_exp.timestamp()),
        "type": "refresh",
    }

    access_token = jwt.encode(access_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    refresh_token = jwt.encode(refresh_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return access_token, refresh_token

def has_property_scope(user: User, property_id: int, required_capability: str = 'can_manage_bookings') -> bool:
    """التحقق مما إذا كان المستخدم يملك صلاحية على مبنى محدد"""
    if user.role == User.Role.SUPER_ADMIN or user.is_superuser:
        return True
    
    scope = UserPropertyScope.objects.filter(user=user, property_id=property_id).first()
    if not scope:
        return False
        
    return getattr(scope, required_capability, False)
