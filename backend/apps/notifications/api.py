from ninja import Router
from typing import List
from apps.notifications.models import NotificationLog
from apps.users.permissions import JWTAuth

router = Router()
auth_security = JWTAuth()

@router.get("/logs", auth=auth_security)
def list_notification_logs(request):
    """عرض سجل الإشعارات المرسلة (للإدارة)"""
    if request.user.role not in ['SUPER_ADMIN', 'PROPERTY_MANAGER']:
        return []
    logs = NotificationLog.objects.all()[:50]
    return [
        {
            "id": log.id,
            "recipient": log.recipient,
            "channel": log.channel,
            "title": log.title,
            "status": log.status,
            "created_at": log.created_at
        }
        for log in logs
    ]
