from django.contrib import admin
from apps.finance.models import Payment, Invoice, Expense, OwnerStatement

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'booking', 'amount', 'method', 'status', 'transaction_reference', 'created_at')
    list_filter = ('status', 'method')
    search_fields = ('booking__id', 'transaction_reference')

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'booking', 'buyer_name', 'subtotal', 'tax_amount', 'total_amount', 'issue_date', 'is_reported')
    list_filter = ('invoice_type', 'is_reported')
    search_fields = ('invoice_number', 'buyer_name', 'booking__id')
    readonly_fields = ('invoice_hash', 'qr_code_data', 'issue_date', 'line_items')

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('title', 'property', 'category', 'amount', 'date_incurred', 'recorded_by')
    list_filter = ('category', 'property')
    search_fields = ('title', 'notes')

@admin.register(OwnerStatement)
class OwnerStatementAdmin(admin.ModelAdmin):
    list_display = ('property', 'period_start', 'period_end', 'total_revenue', 'total_expenses', 'management_commission', 'net_owner_payout', 'is_settled')
    list_filter = ('is_settled', 'property')
