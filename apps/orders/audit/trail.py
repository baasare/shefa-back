"""
Audit logging system for all trade and order activities.

Provides immutable audit trail for compliance and debugging.
"""
import logging
from apps.orders.audit.model import AuditLog

from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger(__name__)


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
