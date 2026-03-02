"""
Notification models for ShefaAI Trading Platform.
"""
from django.db import models
import uuid


class Notification(models.Model):
    """User notifications."""

    NOTIFICATION_TYPE_CHOICES = [
        ('trade_executed', 'Trade Executed'),
        ('approval_required', 'Approval Required'),
        ('strategy_alert', 'Strategy Alert'),
        ('risk_alert', 'Risk Alert'),
        ('system', 'System'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='notifications')

    notification_type = models.CharField('Type', max_length=50, choices=NOTIFICATION_TYPE_CHOICES)
    title = models.CharField('Title', max_length=255)
    message = models.TextField('Message')
    data = models.JSONField('Data', null=True, blank=True)

    # Delivery
    send_email = models.BooleanField('Send Email', default=False)
    send_push = models.BooleanField('Send Push', default=True)
    send_sms = models.BooleanField('Send SMS', default=False)

    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='pending')
    is_read = models.BooleanField('Read', default=False)

    created_at = models.DateTimeField('Created At', auto_now_add=True)
    sent_at = models.DateTimeField('Sent At', null=True, blank=True)
    read_at = models.DateTimeField('Read At', null=True, blank=True)

    class Meta:
        db_table = 'notifications'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['is_read']),
        ]

    def __str__(self):
        return f'{self.user.email} - {self.title}'
