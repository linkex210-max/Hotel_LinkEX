from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('بانتظار التأكيد / الدفع')
        CONFIRMED = 'CONFIRMED', _('مؤكد')
        CHECKED_IN = 'CHECKED_IN', _('تم تسجيل الدخول (في الفندق)')
        CHECKED_OUT = 'CHECKED_OUT', _('تم تسجيل الخروج (مغادر)')
        CANCELLED = 'CANCELLED', _('ملغي')
        NO_SHOW = 'NO_SHOW', _('لم يحضر (No Show)')

    class BookingSource(models.TextChoices):
        ONLINE = 'ONLINE', _('تطبيق / موقع إلكتروني')
        MANUAL = 'MANUAL', _('حجز يدوي من الاستقبال')
        OTA = 'OTA', _('منصات وسيطة (Booking / Airbnb)')

    property = models.ForeignKey('properties.Property', on_delete=models.CASCADE, related_name='bookings')
    room_type = models.ForeignKey('properties.RoomType', on_delete=models.PROTECT, related_name='bookings', null=True, blank=True)
    # في الفنادق: الغرفة الفعلية (Unit) قد تترك فارغة وقت الحجز ويتم تسكينها وتعيينها عند الدخول
    unit = models.ForeignKey('properties.Unit', on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    guest = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    
    # Guest Info for manual or walk-in bookings
    guest_name = models.CharField(_('اسم النزيل'), max_length=150)
    guest_phone = models.CharField(_('رقم جوال النزيل'), max_length=20)
    guest_national_id = models.CharField(_('رقم الهوية / الإقامة / الجواز'), max_length=50, blank=True)

    check_in_date = models.DateField(_('تاريخ الوصول'))
    check_out_date = models.DateField(_('تاريخ المغادرة'))
    
    status = models.CharField(_('حالة الحجز'), max_length=20, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(_('مصدر الحجز'), max_length=20, choices=BookingSource.choices, default=BookingSource.ONLINE)

    total_nights = models.PositiveIntegerField(_('عدد الليالي'), default=1)
    
    # تفصيل أسعار كل ليلة بدقة (Audit Trail & Nightly Breakdown)
    # [{"date": "2026-11-24", "rate": 350.00}, {"date": "2026-11-25", "rate": 450.00}]
    nights_breakdown = models.JSONField(_('تفصيل أسعار الليالي اليومية'), default=list, blank=True)

    base_rate = models.DecimalField(_('متوسط سعر الليلة'), max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(_('المجموع قبل الضريبة'), max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(_('نسبة الضريبة %'), max_digits=5, decimal_places=2, default=15.00)
    tax_amount = models.DecimalField(_('مبلغ الضريبة'), max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(_('مبلغ الخصم'), max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(_('الإجمالي النهائي'), max_digits=10, decimal_places=2)
    
    is_paid = models.BooleanField(_('تم السداد بالكامل'), default=False)
    special_requests = models.TextField(_('طلبات خاصة'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('حجز')
        verbose_name_plural = _('الحجوزات')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['property', 'room_type', 'check_in_date', 'check_out_date']),
            models.Index(fields=['unit', 'check_in_date', 'check_out_date']),
            models.Index(fields=['status']),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(check_in_date__lt=models.F('check_out_date')), name='booking_check_in_lt_check_out'),
            models.CheckConstraint(check=models.Q(total_amount__gte=0), name='booking_total_amount_gte_zero'),
            models.CheckConstraint(check=models.Q(total_nights__gt=0), name='booking_total_nights_gt_zero'),
            models.CheckConstraint(check=models.Q(subtotal__gte=0), name='booking_subtotal_gte_zero'),
            models.CheckConstraint(check=models.Q(tax_amount__gte=0), name='booking_tax_amount_gte_zero'),
            models.CheckConstraint(check=models.Q(discount_amount__gte=0), name='booking_discount_amount_gte_zero'),
        ]

    def __str__(self):
        target = self.unit.unit_number if self.unit else (self.room_type.name if self.room_type else "حجز عام")
        return f"حجز #{self.id} - {self.guest_name} ({target})"


class BookingStatusHistory(models.Model):
    """سجل تتبع التحولات بين حالات الحجز"""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(_('من حالة'), max_length=20)
    to_status = models.CharField(_('إلى حالة'), max_length=20)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(_('ملاحظات'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('سجل حالة الحجز')
        verbose_name_plural = _('سجلات حالات الحجز')
        ordering = ['-created_at']
