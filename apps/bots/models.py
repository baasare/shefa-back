import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Bot(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('stopped', 'Stopped'),
        ('error', 'Needs attention'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='paper_bots')
    portfolio = models.ForeignKey('portfolios.Portfolio', on_delete=models.CASCADE, related_name='paper_bots')
    name = models.CharField(max_length=100)
    idea = models.TextField(max_length=2000)
    symbols = models.JSONField(default=list)
    max_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    max_open_positions = models.PositiveSmallIntegerField(default=5)
    daily_loss_limit_pct = models.DecimalField(max_digits=4, decimal_places=2, default=2)
    run_frequency_minutes = models.PositiveSmallIntegerField(default=15)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='draft', db_index=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    config_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['status', 'next_run_at'])]

    def __str__(self):
        return f'{self.name} ({self.status})'


class BotRun(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name='runs')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='queued', db_index=True)
    result = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-queued_at']
        indexes = [models.Index(fields=['bot', '-queued_at'])]
        constraints = [
            models.UniqueConstraint(
                fields=['bot'],
                condition=Q(status__in=['queued', 'running']),
                name='one_open_run_per_paper_bot',
            )
        ]


class BotEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name='events')
    run = models.ForeignKey(BotRun, on_delete=models.CASCADE, related_name='events', null=True, blank=True)
    event_type = models.CharField(max_length=32, db_index=True)
    message = models.CharField(max_length=500)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['id']
        indexes = [models.Index(fields=['bot', 'id'])]
