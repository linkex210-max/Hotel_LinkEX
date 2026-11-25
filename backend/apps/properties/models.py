import builtins
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from config.validators import validate_image_upload

class Property(models.Model):
    class PropertyType(models.TextChoices):
        HOTEL = 'HOTEL', _('فندق')
        APARTMENT_BUILDING = 'APARTMENT_BUILDING', _('عمارة شقق مفروشة')
        CHALET = 'CHALET', _('شاليه / منتجع')
        VILLA = 'VILLA', _('فيلا')

    class OwnershipType(models.TextChoices):
        OWNED = 'OWNED', _('مملوك للشركة')
        MANAGED = 'MANAGED', _('مُدار بعقد مع المالك')

    name = models.CharField(_('اسم المبنى / الفندق'), max_length=200)
    property_type = models.CharField(_('نوع العقار'), max_length=30, choices=PropertyType.choices, default=PropertyType.HOTEL)
    ownership_type = models.CharField(_('نوع الملكية'), max_length=20, choices=OwnershipType.choices, default=OwnershipType.OWNED)
    city = models.CharField(_('المدينة'), max_length=100)
    address = models.TextField(_('العنوان التفصيلي'))
    description = models.TextField(_('الوصف'), blank=True)
    is_active = models.BooleanField(_('نشط في النظام'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('مبنى / عقار')
        verbose_name_plural = _('المباني والعقارات')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_property_type_display()})"


class OwnerContract(models.Model):
    """عقد إدارة العقارات غير المملوكة"""
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='owner_contracts')
    owner_name = models.CharField(_('اسم المالك'), max_length=150)
    owner_phone = models.CharField(_('رقم هاتف المالك'), max_length=20)
    owner_email = models.EmailField(_('البريد الإلكتروني للمالك'), blank=True, null=True)
    commission_percentage = models.DecimalField(_('نسبة عمولة الإدارة %'), max_digits=5, decimal_places=2, default=15.00)
    start_date = models.DateField(_('تاريخ بداية العقد'))
    end_date = models.DateField(_('تاريخ نهاية العقد'))
    contract_terms = models.TextField(_('شروط العقد'), blank=True)
    is_active = models.BooleanField(_('ساري المفعول'), default=True)

    class Meta:
        verbose_name = _('عقد المالك')
        verbose_name_plural = _('عقود الملاك')
        constraints = [
            models.CheckConstraint(check=models.Q(start_date__lte=models.F('end_date')), name='contract_start_lte_end'),
        ]

    def __str__(self):
        return f"عقد {self.owner_name} - {self.property.name}"


class RoomType(models.Model):
    """
    فئة الغرفة / نوع الوحدة:
    في الفنادق، النزيل يحجز 'نوع الغرفة' وليس رقم الغرفة مباشرة.
    أما في الشاليهات فيمكن أن يمثل 'الشاليه بالكامل'.
    """
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='room_types')
    name = models.CharField(_('اسم الفئة (مثلاً: ديلوكس كينج)'), max_length=100)
    code = models.CharField(_('رمز الفئة (مثلاً: DLX-K)'), max_length=20, blank=True)
    description = models.TextField(_('الوصف والمميزات'), blank=True)
    base_price = models.DecimalField(_('السعر الأساسي لليلة'), max_digits=10, decimal_places=2)
    capacity_adults = models.PositiveIntegerField(_('سعة البالغين'), default=2)
    capacity_children = models.PositiveIntegerField(_('سعة الأطفال'), default=1)
    amenities = models.JSONField(_('المرافق والخدمات المشمولة'), default=list, blank=True)
    is_active = models.BooleanField(_('نشط'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('فئة الغرفة')
        verbose_name_plural = _('فئات الغرف')
        unique_together = ('property', 'name')
        constraints = [
            models.CheckConstraint(check=models.Q(base_price__gte=0), name='room_type_base_price_gte_zero'),
        ]

    def __str__(self):
        return f"{self.property.name} - {self.name}"

    @builtins.property
    def total_inventory_units(self):
        return self.units.filter(is_active=True).count()


class Unit(models.Model):
    """
    الغرفة / الشقة الفعلية (رقم 101، 102، إلخ)
    """
    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', _('جاهزة ومتاحة')
        OCCUPIED = 'OCCUPIED', _('مشغولة بنزيل')
        MAINTENANCE = 'MAINTENANCE', _('تحت الصيانة')
        CLEANING = 'CLEANING', _('قيد التنظيف والتجهيز')
        OUT_OF_SERVICE = 'OUT_OF_SERVICE', _('خارج الخدمة')

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='units')
    room_type = models.ForeignKey(RoomType, on_delete=models.SET_NULL, null=True, blank=True, related_name='units')
    unit_number = models.CharField(_('رقم الغرفة / الوحدة'), max_length=50)
    floor = models.IntegerField(_('الطابق'), default=1)
    base_price_override = models.DecimalField(_('سعر خاص للوحدة إن وجد'), max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(_('حالة التشغيل الحالية'), max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    notes = models.TextField(_('ملاحظات التشغيل'), blank=True)
    is_active = models.BooleanField(_('نشطة'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('غرفة / وحدة فعلية')
        verbose_name_plural = _('الغرف والوحدات الفعلية')
        unique_together = ('property', 'unit_number')
        ordering = ['property', 'unit_number']

    def clean(self):
        """
        التحقق من أن RoomType والوحدة ينتميان للعقار نفسه.

        تحذير: هذا الفحص يعمل فقط عبر instance.save(). مسارات الكتابة التالية
        تتجاوز clean() وبالتالي لا تخضع لهذا التحقق:
          - Unit.objects.bulk_create([...])
          - Unit.objects.filter(...).update(room_type=...)
        يجب ضمان صحة البيانات في هذه الحالات على مستوى تطبيقي قبل الاستدعاء.
        """
        super().clean()
        if self.room_type_id and self.property_id:
            if self.room_type.property_id != self.property_id:
                raise ValidationError(_("فئة الغرفة المحددة لا تنتمي لنفس العقار / المبنى"))

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        type_str = f" ({self.room_type.name})" if self.room_type else ""
        return f"{self.property.name} - {self.unit_number}{type_str}"

    @builtins.property
    def effective_price(self):
        if self.base_price_override:
            return self.base_price_override
        if self.room_type:
            return self.room_type.base_price
        return 0


class RoomTypeInventory(models.Model):
    """
    جدول مخزون الغرف اليومي (Daily Availability & Inventory):
    يقدم أداء فائق السرعة O(1) لفحص توفر الغرف وتسعيرها اليومي
    بدون الحاجة لعمل Full Table Scan على جدول الحجوزات.
    """
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='daily_inventory')
    date = models.DateField(_('التاريخ'))
    total_rooms = models.PositiveIntegerField(_('إجمالي الغرف المتوفرة'))
    booked_rooms = models.PositiveIntegerField(_('عدد الغرف المحجوزة'), default=0)
    price = models.DecimalField(_('السعر الفعلي لهذا اليوم'), max_digits=10, decimal_places=2)
    is_closed = models.BooleanField(_('إيقاف البيع لهذا اليوم (Stop Sell)'), default=False)

    class Meta:
        verbose_name = _('المخزون اليومي للغرفة')
        verbose_name_plural = _('المخزون والتوفر اليومي')
        unique_together = ('room_type', 'date')
        indexes = [
            models.Index(fields=['room_type', 'date']),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(booked_rooms__lte=models.F('total_rooms')), name='inventory_booked_lte_total'),
            models.CheckConstraint(check=models.Q(price__gte=0), name='inventory_price_gte_zero'),
        ]

    def __str__(self):
        return f"{self.room_type.name} [{self.date}]: {self.available_rooms}/{self.total_rooms}"

    @builtins.property
    def available_rooms(self):
        if self.is_closed:
            return 0
        return max(0, self.total_rooms - self.booked_rooms)


class SeasonalPricing(models.Model):
    """محرك الأسعار الموسمية وقواعد التسعير الديناميكي"""
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='seasonal_prices', null=True, blank=True)
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='seasonal_prices', null=True, blank=True)
    name = models.CharField(_('اسم الموسم / العرض'), max_length=100)
    start_date = models.DateField(_('من تاريخ'))
    end_date = models.DateField(_('إلى تاريخ'))
    price_multiplier = models.DecimalField(_('معامل الضرب بالسعر (مثلاً 1.25 لزيادة 25%)'), max_digits=4, decimal_places=2, default=1.00)
    fixed_price = models.DecimalField(_('سعر ثابت محدد لليلة (اختياري)'), max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(_('مفعل'), default=True)

    class Meta:
        verbose_name = _('تسعير موسمي')
        verbose_name_plural = _('الأسعار الموسمية')
        constraints = [
            models.CheckConstraint(check=models.Q(start_date__lte=models.F('end_date')), name='seasonal_start_lte_end'),
            models.CheckConstraint(check=models.Q(price_multiplier__gt=0), name='seasonal_multiplier_gt_zero'),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_date} -> {self.end_date})"


class UnitImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='images', null=True, blank=True)
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='images', null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='images', null=True, blank=True)
    image = models.ImageField(_('الصورة'), upload_to='properties/', validators=[validate_image_upload])
    caption = models.CharField(_('وصف الصورة'), max_length=150, blank=True)
    is_primary = models.BooleanField(_('الصورة الرئيسية'), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('صورة')
        verbose_name_plural = _('الصور')
