from django.contrib import admin
from apps.notifications.models import NotificationLog

@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'channel', 'title', 'status', 'created_at')
    list_filter = ('channel', 'status')
    search_fields = ('recipient', 'title', 'body')
