"""
Audit logging system for all trade and order activities.

Provides immutable audit trail for compliance and debugging.
"""
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
import uuid
import logging
import json

logger = logging.getLogger(__name__)


class AuditLog(models.Model):
    """
    Immutable audit log for all trading activities.

    Never delete records from this table - required for compliance.
    """

    ACTION_CHOICES = [
        # Order actions
        ('order_created', 'Order Created'),
        ('order_submitted', 'Order Submitted'),
        ('order_filled', 'Order Filled'),
        ('order_partially_filled', 'Order Partially Filled'),
        ('order_cancelled', 'Order Cancelled'),
        ('order_rejected', 'Order Rejected'),
        ('order_approved', 'Order Approved (HITL)'),
        ('order_rejected_user', 'Order Rejected by User'),

        # Trade actions
        ('trade_executed', 'Trade Executed'),
        ('trade_settled', 'Trade Settled'),

        # Portfolio actions
        ('position_opened', 'Position Opened'),
        ('position_closed', 'Position Closed'),
        ('position_updated', 'Position Updated'),
        ('portfolio_reconciled', 'Portfolio Reconciled'),

        # Strategy actions
        ('strategy_activated', 'Strategy Activated'),
        ('strategy_paused', 'Strategy Paused'),
        ('strategy_executed', 'Strategy Executed'),
        ('signal_generated', 'Signal Generated'),

        # Broker actions
        ('broker_connected', 'Broker Connected'),
        ('broker_disconnected', 'Broker Disconnected'),
        ('broker_error', 'Broker Error'),

        # Security actions
        ('suspicious_activity', 'Suspicious Activity Detected'),
        ('rate_limit_exceeded', 'Rate Limit Exceeded'),
        ('unauthorized_access', 'Unauthorized Access Attempt'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Who
    user = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,  # Never delete
        related_name='audit_logs'
    )

    # What
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    description = models.TextField()

    # When
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # Where (IP address)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Related object (polymorphic)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=255)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Data snapshot (JSON)
    data_before = models.JSONField(null=True, blank=True)
    data_after = models.JSONField(null=True, blank=True)

    # Additional context
    metadata = models.JSONField(default=dict, blank=True)

    # Result
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'audit_logs'
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['-timestamp']),
        ]
        # Make immutable
        permissions = [
            ('view_auditlog', 'Can view audit logs'),
        ]

    def __str__(self):
        return f"{self.timestamp} - {self.user.email} - {self.action}"

    def save(self, *args, **kwargs):
        """Override save to make records immutable after creation."""
        if self.pk is not None:
            raise ValueError("Audit logs cannot be modified after creation")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of audit logs."""
        raise ValueError("Audit logs cannot be deleted")


def log_order_activity(order, action, user=None, request=None, success=True, error_message='', **extra_data):
    """
    Log order-related activity.

    Args:
        order: Order instance
        action: Action type (from ACTION_CHOICES)
        user: User who performed action (defaults to order.portfolio.user)
        request: HTTP request object (for IP/user agent)
        success: Whether action was successful
        error_message: Error message if failed
        **extra_data: Additional metadata
    """
    if user is None:
        user = order.portfolio.user

    # Build data snapshot
    data_after = {
        'order_id': str(order.id),
        'symbol': order.symbol,
        'quantity': order.quantity,
        'side': order.side,
        'type': order.type,
        'status': order.status,
        'limit_price': float(order.limit_price) if order.limit_price else None,
        'filled_qty': order.filled_qty,
        'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
    }

    # Get IP and user agent from request
    ip_address = None
    user_agent = ''
    if request:
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

    # Create audit log
    try:
        audit = AuditLog.objects.create(
            user=user,
            action=action,
            description=f"{action.replace('_', ' ').title()}: {order.symbol} ({order.quantity} shares)",
            timestamp=timezone.now(),
            ip_address=ip_address,
            user_agent=user_agent,
            content_type=ContentType.objects.get_for_model(order),
            object_id=str(order.id),
            data_after=data_after,
            metadata=extra_data,
            success=success,
            error_message=error_message
        )

        logger.info(f"Audit log created: {audit.id} - {action}")
        return audit

    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
        # Don't fail the main operation if audit logging fails
        return None


def log_trade_activity(trade, action='trade_executed', request=None):
    """Log trade execution."""
    user = trade.portfolio.user

    data_after = {
        'trade_id': str(trade.id),
        'symbol': trade.symbol,
        'quantity': trade.quantity,
        'side': trade.side,
        'price': float(trade.price),
        'executed_at': trade.executed_at.isoformat() if trade.executed_at else None,
    }

    ip_address = None
    user_agent = ''
    if request:
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

    try:
        return AuditLog.objects.create(
            user=user,
            action=action,
            description=f"Trade Executed: {trade.side.upper()} {trade.quantity} {trade.symbol} @ ${trade.price}",
            ip_address=ip_address,
            user_agent=user_agent,
            content_type=ContentType.objects.get_for_model(trade),
            object_id=str(trade.id),
            data_after=data_after,
            success=True
        )
    except Exception as e:
        logger.error(f"Failed to log trade activity: {e}")
        return None


def log_strategy_activity(strategy, action, user=None, **extra_data):
    """Log strategy-related activity."""
    if user is None:
        user = strategy.user

    data_after = {
        'strategy_id': str(strategy.id),
        'name': strategy.name,
        'type': strategy.strategy_type,
        'status': strategy.status,
    }

    try:
        return AuditLog.objects.create(
            user=user,
            action=action,
            description=f"{action.replace('_', ' ').title()}: {strategy.name}",
            content_type=ContentType.objects.get_for_model(strategy),
            object_id=str(strategy.id),
            data_after=data_after,
            metadata=extra_data,
            success=True
        )
    except Exception as e:
        logger.error(f"Failed to log strategy activity: {e}")
        return None


def log_security_event(user, action, description, request=None, **extra_data):
    """Log security-related events."""
    ip_address = None
    user_agent = ''
    if request:
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

    try:
        return AuditLog.objects.create(
            user=user,
            action=action,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            content_type=ContentType.objects.get_for_model(user),
            object_id=str(user.id),
            metadata=extra_data,
            success=False  # Security events are typically failures
        )
    except Exception as e:
        logger.error(f"Failed to log security event: {e}")
        return None


def get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_user_audit_trail(user, days=30):
    """
    Get audit trail for a user.

    Args:
        user: User instance
        days: Number of days to retrieve

    Returns:
        QuerySet of audit logs
    """
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(days=days)
    return AuditLog.objects.filter(user=user, timestamp__gte=cutoff)


def get_order_audit_trail(order):
    """Get complete audit trail for an order."""
    content_type = ContentType.objects.get_for_model(order)
    return AuditLog.objects.filter(
        content_type=content_type,
        object_id=str(order.id)
    )


# Middleware to automatically log requests
class AuditMiddleware:
    """
    Middleware to automatically log certain requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Log suspicious activity
        if response.status_code == 403:
            if request.user.is_authenticated:
                log_security_event(
                    user=request.user,
                    action='unauthorized_access',
                    description=f"Unauthorized access attempt to {request.path}",
                    request=request,
                    status_code=403
                )

        return response


# Add to settings.py:
"""
MIDDLEWARE = [
    ...
    'apps.orders.audit.AuditMiddleware',
]
"""

# Usage in views/services:
"""
from apps.orders.audit import log_order_activity, log_trade_activity

# In order execution
order = create_order(...)
log_order_activity(order, 'order_created', request=request)

try:
    submit_to_broker(order)
    log_order_activity(order, 'order_submitted', request=request, success=True)
except Exception as e:
    log_order_activity(order, 'order_submitted', request=request, success=False, error_message=str(e))
"""
