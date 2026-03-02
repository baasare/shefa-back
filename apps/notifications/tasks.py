"""
Notification tasks for email, SMS, and push notifications.
"""
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from celery.utils.log import get_task_logger

from apps.notifications.models import Notification

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3)
def send_email_notification(self, notification_id: int):
    """
    Send email notification.

    Args:
        notification_id: Notification ID
    """
    try:
        notification = Notification.objects.get(id=notification_id)

        subject = notification.title
        message = notification.message
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [notification.user.email]

        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False
        )

        logger.info(f"Sent email notification {notification_id} to {notification.user.email}")

        return {'success': True, 'notification_id': notification_id}

    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
        return {'success': False, 'error': 'Notification not found'}

    except Exception as e:
        logger.error(f"Error sending email notification {notification_id}: {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True)
def send_trade_execution_alert(self, order_id: str):
    """
    Send alert when trade is executed.

    Args:
        order_id: Order ID
    """
    try:
        from apps.orders.models import Order

        order = Order.objects.select_related('portfolio__user').get(id=order_id)

        if order.status != 'filled':
            return {'success': False, 'reason': 'Order not filled'}

        user = order.portfolio.user

        # Create notification
        notification = Notification.objects.create(
            user=user,
            type='trade_execution',
            title=f"Trade Executed: {order.side.upper()} {order.symbol}",
            message=f"Your order to {order.side} {order.quantity} shares of {order.symbol} was filled at ${order.filled_avg_price}",
            data={
                'order_id': str(order.id),
                'symbol': order.symbol,
                'side': order.side,
                'quantity': order.quantity,
                'price': float(order.filled_avg_price) if order.filled_avg_price else None
            }
        )

        # Send email if enabled
        if user.userprofile.email_notifications:
            send_email_notification.delay(notification.id)

        logger.info(f"Sent trade execution alert for order {order_id}")

        return {'success': True, 'notification_id': notification.id}

    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
        return {'success': False, 'error': 'Order not found'}

    except Exception as e:
        logger.error(f"Error sending trade execution alert: {e}")
        raise


@shared_task(bind=True)
def send_approval_request(self, order_id: str):
    """
    Send notification requesting order approval (HITL).

    Args:
        order_id: Order ID
    """
    try:
        from apps.orders.models import Order

        order = Order.objects.select_related('portfolio__user').get(id=order_id)
        user = order.portfolio.user

        notification = Notification.objects.create(
            user=user,
            type='approval_request',
            title=f"Approval Required: {order.side.upper()} {order.symbol}",
            message=f"Strategy wants to {order.side} {order.quantity} shares of {order.symbol}. Please approve or reject.",
            data={
                'order_id': str(order.id),
                'symbol': order.symbol,
                'side': order.side,
                'quantity': order.quantity,
                'estimated_cost': float(order.quantity * (order.limit_price or 0))
            }
        )

        # Send email
        if user.userprofile.email_notifications:
            send_email_notification.delay(notification.id)

        logger.info(f"Sent approval request for order {order_id}")

        return {'success': True, 'notification_id': notification.id}

    except Exception as e:
        logger.error(f"Error sending approval request: {e}")
        raise


@shared_task(bind=True)
def send_daily_summary(self, user_id: int):
    """
    Send daily portfolio summary.

    Args:
        user_id: User ID
    """
    try:
        from django.contrib.auth import get_user_model
        from apps.portfolios.models import Portfolio

        User = get_user_model()
        user = User.objects.get(id=user_id)

        portfolios = Portfolio.objects.filter(user=user, is_active=True)

        if not portfolios.exists():
            return {'success': False, 'reason': 'No active portfolios'}

        # Gather summary data
        summary_data = {
            'portfolios': [],
            'total_value': 0,
            'total_pnl': 0
        }

        for portfolio in portfolios:
            summary_data['portfolios'].append({
                'name': portfolio.name,
                'value': float(portfolio.total_value),
                'pnl': float(portfolio.total_value - portfolio.cash)  # Simplified
            })
            summary_data['total_value'] += float(portfolio.total_value)

        # Create notification
        notification = Notification.objects.create(
            user=user,
            type='daily_summary',
            title="Daily Portfolio Summary",
            message=f"Your total portfolio value: ${summary_data['total_value']:,.2f}",
            data=summary_data
        )

        # Send email
        if user.userprofile.email_notifications:
            send_email_notification.delay(notification.id)

        logger.info(f"Sent daily summary to user {user_id}")

        return {'success': True, 'notification_id': notification.id}

    except Exception as e:
        logger.error(f"Error sending daily summary: {e}")
        raise


@shared_task(bind=True)
def send_price_alert(self, alert_id: int, current_price: float):
    """
    Send price alert notification.

    Args:
        alert_id: Alert ID
        current_price: Current price that triggered alert
    """
    try:
        # This will be implemented when Alert model is added
        logger.info(f"Price alert {alert_id} triggered at ${current_price}")

        return {'success': True, 'alert_id': alert_id}

    except Exception as e:
        logger.error(f"Error sending price alert: {e}")
        raise


@shared_task(bind=True)
def send_strategy_signal_alert(self, strategy_id: str, symbol: str, signal: str):
    """
    Send alert when strategy generates a signal.

    Args:
        strategy_id: Strategy ID
        symbol: Symbol
        signal: Signal type ('buy', 'sell')
    """
    try:
        from apps.strategies.models import Strategy

        strategy = Strategy.objects.select_related('user').get(id=strategy_id)

        notification = Notification.objects.create(
            user=strategy.user,
            type='strategy_signal',
            title=f"Signal: {signal.upper()} {symbol}",
            message=f"Strategy '{strategy.name}' generated a {signal} signal for {symbol}",
            data={
                'strategy_id': strategy_id,
                'symbol': symbol,
                'signal': signal
            }
        )

        # Send email if enabled
        if strategy.user.userprofile.email_notifications:
            send_email_notification.delay(notification.id)

        logger.info(f"Sent strategy signal alert: {strategy_id} {symbol} {signal}")

        return {'success': True, 'notification_id': notification.id}

    except Exception as e:
        logger.error(f"Error sending strategy signal alert: {e}")
        raise


@shared_task(bind=True)
def send_daily_summaries_to_all(self):
    """Send daily summaries to all users with email notifications enabled."""
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        users = User.objects.filter(
            userprofile__email_notifications=True,
            is_active=True
        )

        count = 0
        for user in users:
            send_daily_summary.delay(user.id)
            count += 1

        logger.info(f"Queued daily summaries for {count} users")

        return {'queued': count}

    except Exception as e:
        logger.error(f"Error queueing daily summaries: {e}")
        raise
