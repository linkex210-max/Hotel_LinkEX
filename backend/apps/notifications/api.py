from ninja import Router
from django.db import models
from typing import List
from apps.notifications.models import NotificationLog
from apps.users.permissions import JWTAuth

router = Router()
auth_security = JWTAuth()

@router.get("/logs", response={200: List[dict], 403: dict}, auth=auth_security)
def list_notification_logs(request):
    """عرض سجل الإشعارات المرسلة مع عزل بيانات الـ Multi-Tenant"""
    if request.user.role not in ['SUPER_ADMIN', 'PROPERTY_MANAGER'] and not request.user.is_superuser:
        return 403, {"error": "غير مصرح لك باستعراض سجلات الإشعارات"}

    if request.user.role == 'SUPER_ADMIN' or request.user.is_superuser:
        logs = NotificationLog.objects.all()[:50]
    else:
        # تقييد مدير المبنى بنطاق العقارات المخصصة له فقط
        # مع التحقق من صلاحية can_manage_bookings أو can_view_finance
        # (رؤية الإشعارات مرتبطة بالإشراف الفعلي على العقار)
        authorized_property_ids = request.user.property_scopes.filter(
            models.Q(can_manage_bookings=True) | models.Q(can_view_finance=True)
        ).values_list('property_id', flat=True)
        logs = NotificationLog.objects.filter(property_id__in=authorized_property_ids)[:50]

    return 200, [
        {
            "id": log.id,
            "property_id": log.property_id,
            "recipient": log.recipient,
            "channel": log.channel,
            "title": log.title,
            "status": log.status,
            "created_at": log.created_at
        }
        for log in logs
    ]
