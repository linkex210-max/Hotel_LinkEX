from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('يجب تحديد البريد الإلكتروني'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'SUPER_ADMIN')
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = 'SUPER_ADMIN', _('مدير النظام الأعلى')
        PROPERTY_MANAGER = 'PROPERTY_MANAGER', _('مدير مبنى / فندق')
        RECEPTIONIST = 'RECEPTIONIST', _('موظف استقبال')
        ACCOUNTANT = 'ACCOUNTANT', _('محاسب')
        GUEST = 'GUEST', _('نزيل / عميل')

    username = None
    email = models.EmailField(_('البريد الإلكتروني'), unique=True)
    phone_number = models.CharField(_('رقم الجوال'), max_length=20, blank=True, null=True)
    role = models.CharField(_('الدور'), max_length=30, choices=Role.choices, default=Role.GUEST)
    is_active = models.BooleanField(_('نشط'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _('مستخدم')
        verbose_name_plural = _('المستخدمون')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"


class Permission(models.Model):
    """صلاحيات مخصصة للنظام"""
    name = models.CharField(_('اسم الصلاحية'), max_length=100)
    codename = models.CharField(_('رمز الصلاحية'), max_length=100, unique=True)
    description = models.TextField(_('الوصف'), blank=True)

    class Meta:
        verbose_name = _('صلاحية')
        verbose_name_plural = _('الصلاحيات')

    def __str__(self):
        return self.name


class UserPropertyScope(models.Model):
    """تحديد نطاق المباني المسموح للمستخدم إدارتها"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='property_scopes')
    property = models.ForeignKey('properties.Property', on_delete=models.CASCADE, related_name='user_scopes')
    can_manage_bookings = models.BooleanField(_('إدارة الحجوزات'), default=True)
    can_manage_pricing = models.BooleanField(_('إدارة الأسعار'), default=False)
    can_view_finance = models.BooleanField(_('الاطلاع على المالية'), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('نطاق مبنى المستخدم')
        verbose_name_plural = _('نطاقات مباني المستخدمين')
        unique_together = ('user', 'property')

    def __str__(self):
        return f"{self.user.email} -> {self.property.name}"


class ActivityLog(models.Model):
    """سجل الحركات والعمليات للمستخدمين"""
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    action = models.CharField(_('الإجراء'), max_length=100)
    details = models.JSONField(_('التفاصيل'), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_('عنوان IP'), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('سجل النشاط')
        verbose_name_plural = _('سجلات الأنشطة')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.created_at} - {self.action} by {self.user}"
