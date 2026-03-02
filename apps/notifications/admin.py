"""
Notifications admin configuration.
"""
from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'user_email', 'notification_type', 'status', 'is_read', 'created_at']
    list_filter = ['notification_type', 'status', 'is_read', 'created_at']
    search_fields = ['title', 'user__email']
    readonly_fields = ['created_at', 'sent_at', 'read_at']
    date_hierarchy = 'created_at'

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
