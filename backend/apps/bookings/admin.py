from django.contrib import admin
from apps.bookings.models import Booking, BookingStatusHistory

class BookingStatusHistoryInline(admin.TabularInline):
    model = BookingStatusHistory
    extra = 0
    readonly_fields = ('from_status', 'to_status', 'changed_by', 'notes', 'created_at')

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'guest_name', 'guest_phone', 'property', 'room_type', 'unit', 'check_in_date', 'check_out_date', 'total_amount', 'status', 'is_paid')
    list_filter = ('status', 'is_paid', 'property', 'room_type', 'source')
    search_fields = ('id', 'guest_name', 'guest_phone', 'guest_national_id')
    readonly_fields = ('nights_breakdown', 'created_at', 'updated_at')
    inlines = [BookingStatusHistoryInline]

@admin.register(BookingStatusHistory)
class BookingStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('booking', 'from_status', 'to_status', 'changed_by', 'created_at')
    list_filter = ('to_status',)
