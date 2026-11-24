from celery import shared_task
from datetime import timedelta
from django.utils import timezone
from apps.bookings.models import Booking
from apps.bookings.services import BookingService
from apps.notifications.models import NotificationLog

@shared_task
def cancel_expired_pending_bookings():
    """
    مهمة دورية (Celery Beat):
    إلغاء الحجوزات المعلقة التي لم يتم سدادها خلال 30 دقيقة من إنشائها
    وتحرير الغرف تلقائياً لإتاحتها للنزلاء الآخرين
    """
    expiry_time = timezone.now() - timedelta(minutes=30)
    expired_bookings = Booking.objects.filter(
        status=Booking.Status.PENDING,
        is_paid=False,
        created_at__lte=expiry_time
    )

    cancelled_count = 0
    for booking in expired_bookings:
        BookingService.transition_status(
            booking=booking,
            new_status=Booking.Status.CANCELLED,
            notes="إلغاء تلقائي بواسطة النظام لعدم إتمام السداد خلال المهلة المحددة"
        )
        cancelled_count += 1

    return f"تم فحص الحجوزات وإلغاء {cancelled_count} حجز منتهي الصلاحية"

@shared_task
def send_whatsapp_booking_alert(booking_id: int):
    """إرسال تنبيه واتساب للنزيل بتفاصيل الحجز"""
    try:
        booking = Booking.objects.get(id=booking_id)
        unit_str = booking.unit.unit_number if booking.unit else (booking.room_type.name if booking.room_type else "لم تعين بعد")
        msg_body = (
            f"مرحباً {booking.guest_name}، تم استلام حجزك في {booking.property.name} بنجاح!\n"
            f"رقم الحجز: #{booking.id}\n"
            f"تاريخ الوصول: {booking.check_in_date}\n"
            f"الوحدة: {unit_str}\n"
            f"الإجمالي: {booking.total_amount} ريال"
        )

        NotificationLog.objects.create(
            property=booking.property,
            booking=booking,
            recipient=booking.guest_phone,
            channel=NotificationLog.Channel.WHATSAPP,
            title="تأكيد حجز جديد",
            body=msg_body,
            status=NotificationLog.Status.FAILED,
            error_message="WhatsApp provider is not configured; no message was sent."
        )
        return f"WhatsApp message for booking #{booking_id} was not sent: provider not configured"
    except Exception as e:
        return f"فشل إرسال إشعار الحجز #{booking_id}: {str(e)}"
