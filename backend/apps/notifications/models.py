from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class NotificationLog(models.Model):
    class Channel(models.TextChoices):
        WHATSAPP = 'WHATSAPP', _('واتساب')
        SMS = 'SMS', _('رسالة نصية SMS')
        EMAIL = 'EMAIL', _('بريد إلكتروني')
        PUSH = 'PUSH', _('إشعار تطبيق Push')

    class Status(models.TextChoices):
        SENT = 'SENT', _('تم الإرسال')
        FAILED = 'FAILED', _('فشل الإرسال')
        PENDING = 'PENDING', _('قيد المعالجة')

    recipient = models.CharField(_('المستلم (رقم/إيميل)'), max_length=150)
    property = models.ForeignKey('properties.Property', on_delete=models.CASCADE, null=True, blank=True, related_name='notification_logs')
    booking = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='notification_logs')
    channel = models.CharField(_('القناة'), max_length=20, choices=Channel.choices, default=Channel.WHATSAPP)
    title = models.CharField(_('عنوان الإشعار'), max_length=200)
    body = models.TextField(_('نص الرسالة'))
    status = models.CharField(_('حالة التسليم'), max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(_('رسالة الخطأ إن وجدت'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('سجل إشعار')
        verbose_name_plural = _('سجل الإشعارات')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.channel} -> {self.recipient} ({self.status})"
