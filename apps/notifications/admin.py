"""
Notifications admin configuration.
"""
from django.contrib import admin, messages
from django.utils.html import format_html
from django.db.models import Q
from apps.notifications.models import Notification
from apps.notifications.tasks import (
    send_email_notification,
    send_daily_summary
)
from apps.notifications.services import mark_as_read
from core.admin_2fa import secure_admin_site


@admin.register(Notification, site=secure_admin_site)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        'title',
        'user_email',
        'notification_type',
        'status_badge',
        'read_badge',
        'created_at'
    ]
    list_filter = ['notification_type', 'status', 'is_read', 'created_at']
    search_fields = ['title', 'user__email', 'message']
    readonly_fields = ['created_at', 'sent_at', 'read_at']
    date_hierarchy = 'created_at'
    actions = [
        'mark_as_read_action',
        'mark_as_unread_action',
        'send_email_action',
        'resend_failed_notifications',
        'send_daily_summary_to_users',
        'delete_read_notifications'
    ]

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def status_badge(self, obj):
        """Display status as colored badge."""
        colors = {
            'pending': '#ffc107',
            'sent': '#28a745',
            'failed': '#dc3545'
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.status.upper()
        )
    status_badge.short_description = 'Status'

    def read_badge(self, obj):
        """Display read status as badge."""
        if obj.is_read:
            return format_html(
                '<span style="color: #28a745;">✓ Read</span>'
            )
        return format_html(
            '<span style="color: #ffc107;">● Unread</span>'
        )
    read_badge.short_description = 'Read Status'

    def mark_as_read_action(self, request, queryset):
        """Mark selected notifications as read."""
        unread_notifications = queryset.filter(is_read=False)
        count = 0

        for notification in unread_notifications:
            if mark_as_read(notification.id):
                count += 1

        self.message_user(
            request,
            f"Marked {count} notification(s) as read",
            messages.SUCCESS
        )
    mark_as_read_action.short_description = "✓ Mark as read"

    def mark_as_unread_action(self, request, queryset):
        """Mark selected notifications as unread."""
        updated = queryset.filter(is_read=True).update(is_read=False, read_at=None)

        self.message_user(
            request,
            f"Marked {updated} notification(s) as unread",
            messages.SUCCESS
        )
    mark_as_unread_action.short_description = "● Mark as unread"

    def send_email_action(self, request, queryset):
        """Send email for selected notifications."""
        pending_notifications = queryset.filter(
            Q(status='pending') | Q(status='failed')
        )

        count = 0
        for notification in pending_notifications:
            # Queue email task
            send_email_notification.delay(notification.id)
            count += 1

        self.message_user(
            request,
            f"Queued {count} email notification(s) for sending",
            messages.SUCCESS
        )
    send_email_action.short_description = "📧 Send email notifications"

    def resend_failed_notifications(self, request, queryset):
        """Resend failed notifications."""
        failed_notifications = queryset.filter(status='failed')

        if not failed_notifications.exists():
            self.message_user(
                request,
                "No failed notifications selected",
                messages.WARNING
            )
            return

        count = 0
        for notification in failed_notifications:
            # Reset status and resend
            notification.status = 'pending'
            notification.save()
            send_email_notification.delay(notification.id)
            count += 1

        self.message_user(
            request,
            f"Queued {count} failed notification(s) for retry",
            messages.SUCCESS
        )
    resend_failed_notifications.short_description = "🔄 Retry failed notifications"

    def send_daily_summary_to_users(self, request, queryset):
        """Send daily summary to selected notification users."""
        # Get unique users from selected notifications
        users = queryset.values_list('user', flat=True).distinct()

        count = 0
        for user_id in users:
            send_daily_summary.delay(user_id)
            count += 1

        self.message_user(
            request,
            f"Queued daily summary for {count} user(s)",
            messages.SUCCESS
        )
    send_daily_summary_to_users.short_description = "📊 Send daily summary to users"

    def delete_read_notifications(self, request, queryset):
        """Delete read notifications older than 30 days."""
        from django.utils import timezone
        from datetime import timedelta

        cutoff_date = timezone.now() - timedelta(days=30)
        read_notifications = queryset.filter(
            is_read=True,
            created_at__lt=cutoff_date
        )

        count = read_notifications.count()

        if count == 0:
            self.message_user(
                request,
                "No read notifications older than 30 days found",
                messages.WARNING
            )
            return

        read_notifications.delete()

        self.message_user(
            request,
            f"Deleted {count} read notification(s) older than 30 days",
            messages.SUCCESS
        )
    delete_read_notifications.short_description = "🗑️ Delete old read notifications"
