from django.contrib import admin
from apps.properties.models import Property, OwnerContract, RoomType, Unit, RoomTypeInventory, SeasonalPricing, UnitImage

class UnitInline(admin.TabularInline):
    model = Unit
    extra = 1

class UnitImageInline(admin.TabularInline):
    model = UnitImage
    extra = 1

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('name', 'property_type', 'ownership_type', 'city', 'is_active')
    list_filter = ('property_type', 'ownership_type', 'city', 'is_active')
    search_fields = ('name', 'city', 'address')

@admin.register(OwnerContract)
class OwnerContractAdmin(admin.ModelAdmin):
    list_display = ('owner_name', 'property', 'commission_percentage', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'property')

@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'property', 'base_price', 'capacity_adults', 'capacity_children', 'is_active')
    list_filter = ('property', 'is_active')
    search_fields = ('name', 'code', 'property__name')
    inlines = [UnitInline]

@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('unit_number', 'property', 'room_type', 'status', 'is_active')
    list_filter = ('property', 'room_type', 'status', 'is_active')
    search_fields = ('unit_number', 'property__name')
    inlines = [UnitImageInline]

@admin.register(RoomTypeInventory)
class RoomTypeInventoryAdmin(admin.ModelAdmin):
    list_display = ('room_type', 'date', 'total_rooms', 'booked_rooms', 'price', 'is_closed')
    list_filter = ('room_type__property', 'is_closed', 'date')
    search_fields = ('room_type__name',)

@admin.register(SeasonalPricing)
class SeasonalPricingAdmin(admin.ModelAdmin):
    list_display = ('name', 'property', 'room_type', 'start_date', 'end_date', 'price_multiplier', 'fixed_price', 'is_active')
    list_filter = ('is_active', 'property')
