import hashlib
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

class Payment(models.Model):
    class PaymentMethod(models.TextChoices):
        CREDIT_CARD = 'CARD', _('بطاقة مدى / ائتمان')
        BANK_TRANSFER = 'TRANSFER', _('تحويل بنكي مباشر')
        CASH = 'CASH', _('نقداً (في الاستقبال)')
        APPLE_PAY = 'APPLE_PAY', _('Apple Pay')

    class Status(models.TextChoices):
        PENDING = 'PENDING', _('بانتظار التحقق / الاعتماد')
        COMPLETED = 'COMPLETED', _('مكتمل ومقبول')
        FAILED = 'FAILED', _('فاشل')
        REFUNDED = 'REFUNDED', _('مسترجع')

    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(_('مبلغ الدفعة'), max_digits=10, decimal_places=2)
    method = models.CharField(_('طريقة الدفع'), max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CREDIT_CARD)
    status = models.CharField(_('حالة الدفعة'), max_length=20, choices=Status.choices, default=Status.PENDING)
    transaction_reference = models.CharField(_('الرقم المرجعي / كود العملية'), max_length=100, blank=True)
    transfer_receipt = models.ImageField(_('إيصال التحويل'), upload_to='receipts/', blank=True, null=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(_('ملاحظات المحاسب'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('دفعة مالية')
        verbose_name_plural = _('المدفوعات')
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name='payment_amount_gt_zero'),
        ]

    def __str__(self):
        return f"دفعة #{self.id} - {self.amount} ريال - {self.get_status_display()}"


class Invoice(models.Model):
    """
    الفاتورة الضريبية الرسمية (مطابقة لمتطلبات ZATCA):
    فاتورة غير قابلة للتعديل بعد الإصدار مع Hash وبصمة رقمية و QR Code.
    """
    class InvoiceType(models.TextChoices):
        SIMPLIFIED = 'SIMPLIFIED', _('فاتورة ضريبية مبسطة (أفراد / B2C)')
        STANDARD = 'STANDARD', _('فاتورة ضريبية قياسية (شركات / B2B)')

    booking = models.OneToOneField('bookings.Booking', on_delete=models.PROTECT, related_name='invoice')
    invoice_number = models.CharField(_('رقم الفاتورة المتسلسل'), max_length=50, unique=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    invoice_type = models.CharField(_('نوع الفاتورة'), max_length=20, choices=InvoiceType.choices, default=InvoiceType.SIMPLIFIED)
    
    # تفاصيل العميل والضريبة
    buyer_name = models.CharField(_('اسم العميل / الشركة'), max_length=150)
    buyer_vat_number = models.CharField(_('الرقم الضريبي للمشتري'), max_length=50, blank=True)
    
    issue_date = models.DateTimeField(_('تاريخ ووقت الإصدار'), auto_now_add=True)
    
    # المبالغ المالية
    subtotal = models.DecimalField(_('المبلغ الخاضع للضريبة'), max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(_('نسبة الضريبة %'), max_digits=5, decimal_places=2, default=15.00)
    tax_amount = models.DecimalField(_('مبلغ ضريبة القيمة المضافة'), max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(_('الخصم الإجمالي'), max_digits=12, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(_('المبلغ الإجمالي شامل الضريبة'), max_digits=12, decimal_places=2)

    # تفاصيل بنود الفاتورة اليومية
    line_items = models.JSONField(_('بنود الفاتورة'), default=list)

    # التشفير والتحقق الإلكتروني (ZATCA Hash & QR)
    qr_code_data = models.TextField(_('بيانات الـ QR Code (بصيغة TLV Base64)'), blank=True)
    invoice_hash = models.CharField(_('البصمة الرقمية للفاتورة (SHA256 Hash)'), max_length=64, blank=True)
    is_reported = models.BooleanField(_('تم التبليغ للهيئة الضريبية'), default=False)

    class Meta:
        verbose_name = _('فاتورة ضريبية')
        verbose_name_plural = _('الفواتير الضريبية')
        ordering = ['-issue_date']
        constraints = [
            models.CheckConstraint(check=models.Q(total_amount__gte=0), name='invoice_total_amount_gte_zero'),
            models.CheckConstraint(check=models.Q(tax_amount__gte=0), name='invoice_tax_amount_gte_zero'),
        ]

    def __str__(self):
        return f"{self.invoice_number} ({self.total_amount} ريال)"

    def generate_hash(self):
        payload = f"{self.invoice_number}|{self.issue_date}|{self.total_amount}|{self.tax_amount}"
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        if self.pk:
            orig = Invoice.objects.filter(pk=self.pk).values(
                'invoice_number', 'total_amount', 'subtotal', 'tax_amount', 'invoice_hash'
            ).first()
            if orig:
                if (
                    orig['invoice_number'] != self.invoice_number or
                    Decimal(str(orig['total_amount'])) != Decimal(str(self.total_amount)) or
                    Decimal(str(orig['subtotal'])) != Decimal(str(self.subtotal)) or
                    Decimal(str(orig['tax_amount'])) != Decimal(str(self.tax_amount)) or
                    (orig['invoice_hash'] and orig['invoice_hash'] != self.invoice_hash)
                ):
                    raise ValidationError(_("الفواتير الضريبية المصدرة غير قابلة للتعديل بتاتاً وفقاً لمتطلبات هيئة الزكاة والضريبة والجمارك (ZATCA)"))
        if not self.invoice_hash:
            super().save(*args, **kwargs)
            self.invoice_hash = self.generate_hash()
            super().save(update_fields=["invoice_hash"])
            return
        super().save(*args, **kwargs)


class Expense(models.Model):
    class Category(models.TextChoices):
        UTILITIES = 'UTILITIES', _('كهرباء ومياه وإنترنت')
        MAINTENANCE = 'MAINTENANCE', _('صيانة وإصلاحات')
        CLEANING = 'CLEANING', _('مستلزمات نظافة وضيافة')
        COMMISSION = 'COMMISSION', _('عمولات منصات وسيطة')
        STAFF = 'STAFF', _('رواتب ونثريات موظفين')
        OTHER = 'OTHER', _('مصروفات أخرى')

    property = models.ForeignKey('properties.Property', on_delete=models.CASCADE, related_name='expenses')
    title = models.CharField(_('عنوان المصروف'), max_length=150)
    category = models.CharField(_('تصنيف المصروف'), max_length=30, choices=Category.choices, default=Category.MAINTENANCE)
    amount = models.DecimalField(_('المبلغ'), max_digits=10, decimal_places=2)
    date_incurred = models.DateField(_('تاريخ الصرف'))
    invoice_file = models.FileField(_('ملف الفاتورة / السند'), upload_to='expenses/', blank=True, null=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(_('ملاحظات'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('مصروف')
        verbose_name_plural = _('المصروفات')
        ordering = ['-date_incurred']


class OwnerStatement(models.Model):
    """كشف حساب دوري لمالك العقار غير المملوك"""
    property = models.ForeignKey('properties.Property', on_delete=models.CASCADE, related_name='owner_statements')
    contract = models.ForeignKey('properties.OwnerContract', on_delete=models.SET_NULL, null=True, blank=True)
    period_start = models.DateField(_('بداية الفترة'))
    period_end = models.DateField(_('نهاية الفترة'))
    total_revenue = models.DecimalField(_('إجمالي دخل الحجوزات'), max_digits=12, decimal_places=2, default=0.00)
    total_expenses = models.DecimalField(_('إجمالي المصروفات التشغيلية'), max_digits=12, decimal_places=2, default=0.00)
    management_commission = models.DecimalField(_('نسبة عمولة الإدارة'), max_digits=12, decimal_places=2, default=0.00)
    net_owner_payout = models.DecimalField(_('صافي المستحق للمالك'), max_digits=12, decimal_places=2, default=0.00)
    is_settled = models.BooleanField(_('تمت التسوية والتحويل للمالك'), default=False)
    settlement_date = models.DateField(_('تاريخ تسوية الحساب'), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('كشف حساب المالك')
        verbose_name_plural = _('كشوفات حسابات الملاك')
        ordering = ['-period_end']
