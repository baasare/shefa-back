"""
Celery tasks for asynchronous order processing and monitoring.

Handles background order status updates, monitoring, and reconciliation.
"""
import asyncio
from celery import shared_task
from datetime import timedelta
from django.utils import timezone
from celery.utils.log import get_task_logger

from apps.orders.models import Order
from apps.brokers.models import BrokerConnection
from apps.orders.audit.trail import log_order_activity
from apps.brokers.services import get_broker_client
from apps.orders.execution import OrderExecutionEngine, OrderExecutionError

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3)
def update_order_status(self, order_id: int):
    """
    Update order status from broker.

    Args:
        order_id: Order ID to update

    Usage:
        Called periodically for pending orders to check execution status.
    """
    try:
        order = Order.objects.select_related('portfolio__user').get(id=order_id)

        # Skip if order is already in terminal state
        if order.status in ['filled', 'cancelled', 'rejected', 'expired']:
            logger.debug(f"Order {order_id} is in terminal state {order.status}, skipping update")
            return

        # Get user's broker connection
        broker_connection = BrokerConnection.objects.filter(
            user=order.portfolio.user,
            is_active=True
        ).first()

        if not broker_connection:
            logger.error(f"No active broker connection for user {order.portfolio.user.id}")
            return

        # Update status
        engine = OrderExecutionEngine(order.portfolio.user, broker_connection)

        # Run async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            updated_order = loop.run_until_complete(engine.update_order_status(order))
            logger.info(f"Updated order {order_id} status to {updated_order.status}")

            # Log status updates for important transitions
            if updated_order.status == 'filled':
                log_order_activity(
                    updated_order,
                    'order_filled',
                    success=True,
                    automated=True
                )
            elif updated_order.status == 'partially_filled':
                log_order_activity(
                    updated_order,
                    'order_partially_filled',
                    success=True,
                    automated=True
                )
            elif updated_order.status == 'rejected':
                log_order_activity(
                    updated_order,
                    'order_rejected',
                    success=False,
                    automated=True
                )
        finally:
            loop.close()

    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")

    except Exception as e:
        logger.error(f"Error updating order {order_id} status: {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True)
def monitor_pending_orders(self):
    """
    Monitor all pending orders and update their status.

    Runs periodically (every 30 seconds) to check status of active orders.
    """
    try:
        # Get all orders that are not in terminal state
        pending_orders = Order.objects.filter(
            status__in=['pending', 'submitted', 'partially_filled']
        ).exclude(
            broker_order_id__isnull=True
        )

        logger.info(f"Monitoring {pending_orders.count()} pending orders")

        # Queue individual update tasks
        for order in pending_orders:
            update_order_status.delay(order.id)

        return {
            'status': 'success',
            'orders_queued': pending_orders.count()
        }

    except Exception as e:
        logger.error(f"Error in monitor_pending_orders: {e}")
        raise


@shared_task(bind=True, max_retries=3)
def cancel_order_async(self, order_id: int):
    """
    Cancel order asynchronously.

    Args:
        order_id: Order ID to cancel

    Returns:
        Dictionary with cancellation result
    """
    try:
        order = Order.objects.select_related('portfolio__user').get(id=order_id)

        # Get user's broker connection
        broker_connection = BrokerConnection.objects.filter(
            user=order.portfolio.user,
            is_active=True
        ).first()

        if not broker_connection:
            logger.error(f"No active broker connection for user {order.portfolio.user.id}")
            return {'success': False, 'error': 'No active broker connection'}

        # Cancel order
        engine = OrderExecutionEngine(order.portfolio.user, broker_connection)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(engine.cancel_order(order))
            logger.info(f"Cancelled order {order_id}")

            # Log cancellation
            log_order_activity(
                order,
                'order_cancelled',
                success=success,
                automated=True,
                task_id=self.request.id
            )

            return {'success': success}
        finally:
            loop.close()

    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
        return {'success': False, 'error': 'Order not found'}

    except OrderExecutionError as e:
        logger.error(f"Error cancelling order {order_id}: {e}")
        # Log failed cancellation attempt
        try:
            order = Order.objects.get(id=order_id)
            log_order_activity(
                order,
                'order_cancelled',
                success=False,
                error_message=str(e),
                automated=True,
                task_id=self.request.id
            )
        except:
            pass
        return {'success': False, 'error': str(e)}

    except Exception as e:
        logger.error(f"Unexpected error cancelling order {order_id}: {e}")
        raise self.retry(exc=e, countdown=30)


@shared_task(bind=True)
def reconcile_orders_with_broker(self, user_id: int, broker: str = None):
    """
    Reconcile orders with broker API.

    Fetches orders from broker and updates local database to ensure consistency.

    Args:
        user_id: User ID to reconcile
        broker: Optional specific broker to reconcile

    Returns:
        Dictionary with reconciliation stats
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()

        user = User.objects.get(id=user_id)

        # Get broker connection
        query = BrokerConnection.objects.filter(user=user, is_active=True)
        if broker:
            query = query.filter(broker=broker)

        broker_connection = query.first()

        if not broker_connection:
            logger.error(f"No active broker connection for user {user_id}")
            return {'success': False, 'error': 'No active broker connection'}

        # Get broker client
        client = get_broker_client(broker_connection)

        # Fetch orders from broker
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            broker_orders = loop.run_until_complete(client.get_orders(status='all', limit=500))
        finally:
            loop.close()

        stats = {
            'fetched': len(broker_orders),
            'updated': 0,
            'created': 0,
            'errors': 0
        }

        # Update or create orders
        for broker_order in broker_orders:
            try:
                # Try to find existing order by broker_order_id
                order = Order.objects.filter(
                    broker_order_id=broker_order['broker_order_id']
                ).first()

                if order:
                    # Update existing order
                    order.status = broker_order['status']
                    order.filled_qty = broker_order.get('filled_qty', 0)
                    order.filled_avg_price = broker_order.get('filled_avg_price')
                    if broker_order.get('filled_at'):
                        order.filled_at = broker_order['filled_at']
                    order.save()
                    stats['updated'] += 1

                # Note: We don't auto-create orders from broker as we need portfolio/strategy context

            except Exception as e:
                logger.error(f"Error reconciling order {broker_order.get('broker_order_id')}: {e}")
                stats['errors'] += 1

        logger.info(f"Reconciled orders for user {user_id}: {stats}")
        return {'success': True, 'stats': stats}

    except Exception as e:
        logger.error(f"Error in reconcile_orders_with_broker: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(bind=True)
def cleanup_old_orders(self, days: int = 90):
    """
    Clean up old cancelled/rejected orders.

    Args:
        days: Remove orders older than this many days (default 90)

    Returns:
        Number of orders deleted
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days)

        deleted_count = Order.objects.filter(
            status__in=['cancelled', 'rejected'],
            created_at__lt=cutoff_date
        ).delete()[0]

        logger.info(f"Deleted {deleted_count} old orders (older than {days} days)")
        return deleted_count

    except Exception as e:
        logger.error(f"Error in cleanup_old_orders: {e}")
        raise


@shared_task(bind=True)
def check_stale_orders(self):
    """
    Check for orders stuck in pending/submitted state for too long.

    Flags orders that haven't been updated recently as potentially stale.
    """
    try:
        # Check orders pending for more than 1 hour
        stale_threshold = timezone.now() - timedelta(hours=1)

        stale_orders = Order.objects.filter(
            status__in=['pending', 'submitted'],
            created_at__lt=stale_threshold
        )

        stale_count = 0
        for order in stale_orders:
            # Try to update status
            update_order_status.delay(order.id)
            stale_count += 1

            # Add stale flag to metadata
            order.metadata = order.metadata or {}
            order.metadata['flagged_as_stale'] = str(timezone.now())
            order.save()

        logger.info(f"Found {stale_count} potentially stale orders")
        return {
            'stale_orders': stale_count,
            'queued_updates': stale_count
        }

    except Exception as e:
        logger.error(f"Error in check_stale_orders: {e}")
        raise


@shared_task(bind=True)
def sync_positions_from_broker(self, user_id: int, portfolio_id: int):
    """
    Sync positions from broker to portfolio.

    Fetches current positions from broker and updates portfolio accordingly.

    Args:
        user_id: User ID
        portfolio_id: Portfolio ID to sync

    Returns:
        Sync statistics
    """
    try:
        from django.contrib.auth import get_user_model
        from apps.portfolios.models import Portfolio, Position

        User = get_user_model()

        user = User.objects.get(id=user_id)
        portfolio = Portfolio.objects.get(id=portfolio_id, user=user)

        # Get broker connection
        broker_connection = BrokerConnection.objects.filter(
            user=user,
            is_active=True
        ).first()

        if not broker_connection:
            return {'success': False, 'error': 'No active broker connection'}

        # Get broker client
        client = get_broker_client(broker_connection)

        # Fetch positions from broker
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            broker_positions = loop.run_until_complete(client.get_positions())
        finally:
            loop.close()

        stats = {
            'fetched': len(broker_positions),
            'updated': 0,
            'created': 0
        }

        # Update positions
        for broker_pos in broker_positions:
            position, created = Position.objects.update_or_create(
                portfolio=portfolio,
                symbol=broker_pos['symbol'],
                defaults={
                    'quantity': broker_pos['quantity'],
                    'avg_price': broker_pos['avg_entry_price'],
                    'cost_basis': broker_pos['cost_basis']
                }
            )

            if created:
                stats['created'] += 1
            else:
                stats['updated'] += 1

        logger.info(f"Synced positions for portfolio {portfolio_id}: {stats}")
        return {'success': True, 'stats': stats}

    except Exception as e:
        logger.error(f"Error syncing positions: {e}")
        return {'success': False, 'error': str(e)}
