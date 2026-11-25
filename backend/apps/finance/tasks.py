import logging
from celery import shared_task
from django.core.exceptions import ValidationError
from apps.bookings.models import Booking
from apps.finance.models import InvoiceIssuanceAttempt
from apps.finance.services import InvoiceService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5)
def issue_invoice_for_booking(self, booking_id: int) -> int:
    """
    مهمة Celery غير متزامنة وموثوقة لإصدار الفاتورة الضريبية بعد اعتماد الدفع.
    تضمن Idempotency وتسجيل الأخطاء وإعادة المحاولة بـ Exponential Backoff.
    """
    attempt, _ = InvoiceIssuanceAttempt.objects.get_or_create(
        booking_id=booking_id,
        defaults={"status": InvoiceIssuanceAttempt.Status.PENDING},
    )
    attempt.attempts += 1
    attempt.save(update_fields=["attempts", "updated_at"])

    try:
        booking = Booking.objects.get(pk=booking_id)
        invoice = InvoiceService.create_and_issue_for_booking(booking)
        attempt.status = InvoiceIssuanceAttempt.Status.SUCCEEDED
        attempt.last_error = ""
        attempt.save(update_fields=["status", "last_error", "updated_at"])
        logger.info("Invoice %s issued successfully for booking %s", invoice.invoice_number, booking_id)
        return invoice.id
    except (Booking.DoesNotExist, ValidationError) as exc:
        # أخطاء منطقية غير قابلة للإصلاح بإعادة المحاولة
        attempt.status = InvoiceIssuanceAttempt.Status.FAILED
        attempt.last_error = str(exc)
        attempt.save(update_fields=["status", "last_error", "updated_at"])
        logger.error("Permanent failure issuing invoice for booking %s: %s", booking_id, exc)
        raise
    except Exception as exc:
        attempt.last_error = str(exc)
        if self.request.retries >= self.max_retries:
            attempt.status = InvoiceIssuanceAttempt.Status.FAILED
            attempt.save(update_fields=["status", "last_error", "updated_at"])
            logger.exception("Max retries exceeded issuing invoice for booking %s", booking_id)
            raise
        attempt.status = InvoiceIssuanceAttempt.Status.RETRYING
        attempt.save(update_fields=["status", "last_error", "updated_at"])
        countdown = min(60 * (2 ** self.request.retries), 3600)
        logger.warning(
            "Transient failure issuing invoice for booking %s (attempt %s); retrying in %ss: %s",
            booking_id, attempt.attempts, countdown, exc,
        )
        raise self.retry(exc=exc, countdown=countdown)


def enqueue_invoice_issuance(booking_id: int) -> None:
    """إطلاق مهمة إصدار الفاتورة بعد نجاح transaction.on_commit مع تسجيل أي فشل في الإرسال."""
    try:
        issue_invoice_for_booking.delay(booking_id)
    except Exception as exc:
        logger.exception("Failed to enqueue issue_invoice_for_booking for booking %s", booking_id)
        InvoiceIssuanceAttempt.objects.update_or_create(
            booking_id=booking_id,
            defaults={
                "status": InvoiceIssuanceAttempt.Status.FAILED,
                "last_error": f"Broker enqueue failure: {exc}",
            },
        )
