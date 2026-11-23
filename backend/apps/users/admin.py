from django.contrib import admin
from apps.users.models import User, Permission, UserPropertyScope, ActivityLog

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'codename')
    search_fields = ('name', 'codename')

@admin.register(UserPropertyScope)
class UserPropertyScopeAdmin(admin.ModelAdmin):
    list_display = ('user', 'property', 'can_manage_bookings', 'can_manage_pricing', 'can_view_finance')
    list_filter = ('property',)

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'ip_address', 'created_at')
    list_filter = ('action',)
    search_fields = ('action', 'user__email')
