import hashlib
import logging
import uuid
import jwt
from datetime import datetime, timedelta, timezone
from django.conf import settings
from django.db import transaction
from django.utils import timezone as dj_timezone
from ninja.security import HttpBearer
from apps.users.models import User, UserPropertyScope, RefreshToken

logger = logging.getLogger(__name__)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


class JWTAuth(HttpBearer):
    def authenticate(self, request, token):
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            if payload.get("type") != "access":
                return None
            user_id = payload.get("user_id")
            if not user_id:
                return None
        except (jwt.PyJWTError, ValueError, TypeError):
            return None

        user = User.objects.filter(id=user_id, is_active=True).first()
        if user:
            request.user = user
            return user
        return None


def create_tokens(user: User):
    now = datetime.now(timezone.utc)
    access_exp = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_LIFETIME_MINUTES)
    refresh_exp = now + timedelta(days=settings.JWT_REFRESH_TOKEN_LIFETIME_DAYS)
    jti = str(uuid.uuid4())

    access_payload = {
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
        "exp": int(access_exp.timestamp()),
        "type": "access",
    }
    refresh_payload = {
        "user_id": user.id,
        "jti": jti,
        "exp": int(refresh_exp.timestamp()),
        "type": "refresh",
    }

    access_token = jwt.encode(access_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    refresh_token = jwt.encode(refresh_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    RefreshToken.objects.create(
        user=user,
        jti=jti,
        token_hash=_hash_token(refresh_token),
        expires_at=refresh_exp,
    )
    return access_token, refresh_token


def rotate_refresh_token(raw_refresh_token: str):
    """
    تدوير رمز التحديث مع كشف إعادة الاستخدام (Token Reuse Detection) وإلغاء الرمز السابق.
    يرفع jwt.PyJWTError أو ValueError في حال عدم الصلاحية.
    """
    payload = jwt.decode(
        raw_refresh_token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Invalid token type")
    jti = payload.get("jti")
    user_id = payload.get("user_id")
    if not jti or not user_id:
        raise jwt.InvalidTokenError("Missing jti or user_id")

    token_hash = _hash_token(raw_refresh_token)
    now = dj_timezone.now()
    reuse_user_id = None

    with transaction.atomic():
        stored = RefreshToken.objects.select_for_update().filter(
            jti=jti,
            token_hash=token_hash,
        ).first()
        if not stored:
            raise jwt.InvalidTokenError("Refresh token not recognized")

        # Reuse detection: capture user_id so revocation commits outside atomic block
        if stored.revoked_at is not None:
            reuse_user_id = stored.user_id
        else:
            if stored.expires_at <= now:
                raise jwt.ExpiredSignatureError("Refresh token expired")

            user = User.objects.filter(id=user_id, is_active=True).first()
            if not user:
                raise jwt.InvalidTokenError("User inactive or missing")

            new_access, new_refresh = create_tokens(user)
            new_payload = jwt.decode(
                new_refresh,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            stored.revoked_at = now
            stored.replaced_by_jti = new_payload["jti"]
            stored.save(update_fields=["revoked_at", "replaced_by_jti"])
            return new_access, new_refresh

    if reuse_user_id is not None:
        RefreshToken.objects.filter(user_id=reuse_user_id, revoked_at__isnull=True).update(
            revoked_at=now
        )
        logger.warning("Refresh token reuse detected for user_id=%s; all tokens revoked", reuse_user_id)
        raise jwt.InvalidTokenError("Refresh token reuse detected")


def revoke_refresh_token(raw_refresh_token: str) -> bool:
    """إبطال رمز التحديث عند تسجيل الخروج."""
    try:
        payload = jwt.decode(
            raw_refresh_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        jti = payload.get("jti")
    except (jwt.PyJWTError, ValueError, TypeError):
        return False

    if not jti:
        return False
    token_hash = _hash_token(raw_refresh_token)
    updated = RefreshToken.objects.filter(
        jti=jti,
        token_hash=token_hash,
        revoked_at__isnull=True,
    ).update(revoked_at=dj_timezone.now())
    return updated > 0


def has_property_scope(user: User, property_id: int, required_capability: str = 'can_manage_bookings') -> bool:
    """التحقق مما إذا كان المستخدم يملك صلاحية على مبنى محدد"""
    if user.role == User.Role.SUPER_ADMIN or user.is_superuser:
        return True

    scope = UserPropertyScope.objects.filter(user=user, property_id=property_id).first()
    if not scope:
        return False

    return getattr(scope, required_capability, False)
