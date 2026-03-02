"""
Celery tasks for portfolio management and reconciliation.

Handles daily snapshots, position reconciliation, and performance calculations.
"""
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from datetime import timedelta
import asyncio

from apps.portfolios.models import Portfolio, Position, PortfolioSnapshot
from apps.portfolios.services import (
    calculate_portfolio_value,
    update_portfolio_snapshot,
    calculate_position_value,
    calculate_realized_pnl
)
from apps.brokers.models import BrokerConnection
from apps.brokers.services import get_broker_client

logger = get_task_logger(__name__)


@shared_task(bind=True)
def create_daily_snapshots(self):
    """
    Create daily snapshots for all active portfolios.

    Runs once per day (configured in Celery Beat schedule).
    """
    try:
        portfolios = Portfolio.objects.filter(is_active=True)

        success_count = 0
        error_count = 0

        for portfolio in portfolios:
            try:
                # Create snapshot
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    snapshot = loop.run_until_complete(update_portfolio_snapshot(portfolio))
                    success_count += 1
                    logger.info(f"Created snapshot for portfolio {portfolio.id}: ${snapshot.total_value}")
                finally:
                    loop.close()

            except Exception as e:
                error_count += 1
                logger.error(f"Error creating snapshot for portfolio {portfolio.id}: {e}")

        logger.info(f"Daily snapshots completed: {success_count} success, {error_count} errors")

        return {
            'success': success_count,
            'errors': error_count,
            'total': portfolios.count()
        }

    except Exception as e:
        logger.error(f"Error in create_daily_snapshots: {e}")
        raise


@shared_task(bind=True, max_retries=3)
def update_portfolio_value(self, portfolio_id: int):
    """
    Update portfolio value and create snapshot.

    Args:
        portfolio_id: Portfolio ID to update
    """
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)

        # Calculate current value
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            values = loop.run_until_complete(calculate_portfolio_value(portfolio))

            # Update portfolio model
            portfolio.cash = values['cash']
            portfolio.total_value = values['total_value']
            portfolio.save()

            # Create snapshot
            snapshot = loop.run_until_complete(update_portfolio_snapshot(portfolio))

            logger.info(f"Updated portfolio {portfolio_id} value: ${values['total_value']}")

            return {
                'portfolio_id': portfolio_id,
                'total_value': float(values['total_value']),
                'cash': float(values['cash']),
                'positions_value': float(values['positions_value']),
                'unrealized_pnl': float(values['unrealized_pnl'])
            }

        finally:
            loop.close()

    except Portfolio.DoesNotExist:
        logger.error(f"Portfolio {portfolio_id} not found")
        return {'error': 'Portfolio not found'}

    except Exception as e:
        logger.error(f"Error updating portfolio {portfolio_id} value: {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3)
def reconcile_portfolio_positions(self, portfolio_id: int):
    """
    Reconcile portfolio positions with broker.

    Fetches current positions from broker and updates database.

    Args:
        portfolio_id: Portfolio ID to reconcile
    """
    try:
        portfolio = Portfolio.objects.select_related('user').get(id=portfolio_id)

        # Get user's broker connection
        broker_connection = BrokerConnection.objects.filter(
            user=portfolio.user,
            is_active=True
        ).first()

        if not broker_connection:
            logger.warning(f"No active broker connection for portfolio {portfolio_id}")
            return {'success': False, 'error': 'No active broker connection'}

        # Get broker client
        client = get_broker_client(broker_connection)

        # Fetch positions from broker
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            broker_positions = loop.run_until_complete(client.get_positions())

            # Fetch account info for cash balance
            account_info = loop.run_until_complete(client.get_account_info())

        finally:
            loop.close()

        stats = {
            'fetched': len(broker_positions),
            'updated': 0,
            'created': 0,
            'removed': 0
        }

        # Update cash balance
        portfolio.cash = account_info['cash']
        portfolio.save()

        # Get current positions in database
        db_positions = {
            pos.symbol: pos
            for pos in Position.objects.filter(portfolio=portfolio)
        }

        broker_symbols = set()

        # Update positions from broker
        for broker_pos in broker_positions:
            symbol = broker_pos['symbol']
            broker_symbols.add(symbol)

            if symbol in db_positions:
                # Update existing position
                position = db_positions[symbol]
                position.quantity = broker_pos['quantity']
                position.avg_price = broker_pos['avg_entry_price']
                position.cost_basis = broker_pos['cost_basis']
                position.save()
                stats['updated'] += 1
            else:
                # Create new position
                Position.objects.create(
                    portfolio=portfolio,
                    symbol=symbol,
                    quantity=broker_pos['quantity'],
                    avg_price=broker_pos['avg_entry_price'],
                    cost_basis=broker_pos['cost_basis']
                )
                stats['created'] += 1

        # Remove positions no longer held
        for symbol, position in db_positions.items():
            if symbol not in broker_symbols and position.quantity > 0:
                position.quantity = 0
                position.cost_basis = 0
                position.save()
                stats['removed'] += 1

        logger.info(f"Reconciled portfolio {portfolio_id}: {stats}")

        # Update portfolio value after reconciliation
        update_portfolio_value.delay(portfolio_id)

        return {'success': True, 'stats': stats}

    except Portfolio.DoesNotExist:
        logger.error(f"Portfolio {portfolio_id} not found")
        return {'success': False, 'error': 'Portfolio not found'}

    except Exception as e:
        logger.error(f"Error reconciling portfolio {portfolio_id}: {e}")
        raise self.retry(exc=e, countdown=120)


@shared_task(bind=True)
def update_position_values(self, portfolio_id: int):
    """
    Update current values for all positions in portfolio.

    Args:
        portfolio_id: Portfolio ID
    """
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)
        positions = Position.objects.filter(portfolio=portfolio, quantity__gt=0)

        updated_count = 0

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            for position in positions:
                try:
                    # Calculate current value
                    position_data = loop.run_until_complete(calculate_position_value(position))

                    # Store in metadata for quick access
                    position.metadata = position.metadata or {}
                    position.metadata['current_price'] = str(position_data['current_price'])
                    position.metadata['market_value'] = str(position_data['market_value'])
                    position.metadata['unrealized_pnl'] = str(position_data['unrealized_pnl'])
                    position.metadata['unrealized_pnl_pct'] = str(position_data['unrealized_pnl_pct'])
                    position.metadata['updated_at'] = str(timezone.now())
                    position.save()

                    updated_count += 1

                except Exception as e:
                    logger.error(f"Error updating position {position.id}: {e}")

        finally:
            loop.close()

        logger.info(f"Updated {updated_count} positions for portfolio {portfolio_id}")

        return {
            'portfolio_id': portfolio_id,
            'updated': updated_count
        }

    except Portfolio.DoesNotExist:
        logger.error(f"Portfolio {portfolio_id} not found")
        return {'error': 'Portfolio not found'}

    except Exception as e:
        logger.error(f"Error updating position values for portfolio {portfolio_id}: {e}")
        raise


@shared_task(bind=True)
def cleanup_old_snapshots(self, days: int = 365):
    """
    Clean up old portfolio snapshots.

    Keeps daily snapshots for the retention period.

    Args:
        days: Retention period in days (default 365)
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days)

        deleted_count = PortfolioSnapshot.objects.filter(
            timestamp__lt=cutoff_date
        ).delete()[0]

        logger.info(f"Deleted {deleted_count} old snapshots (older than {days} days)")

        return {
            'deleted': deleted_count,
            'retention_days': days
        }

    except Exception as e:
        logger.error(f"Error cleaning up old snapshots: {e}")
        raise


@shared_task(bind=True)
def calculate_portfolio_performance(self, portfolio_id: int, days: int = 30):
    """
    Calculate and cache portfolio performance metrics.

    Args:
        portfolio_id: Portfolio ID
        days: Period for calculation (default 30)

    Returns:
        Performance metrics dictionary
    """
    try:
        from .services import get_portfolio_performance

        portfolio = Portfolio.objects.get(id=portfolio_id)

        # Calculate performance
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            performance = loop.run_until_complete(get_portfolio_performance(portfolio, days))
        finally:
            loop.close()

        # Store in portfolio metadata
        portfolio.metadata = portfolio.metadata or {}
        portfolio.metadata[f'performance_{days}d'] = {
            'current_value': str(performance['current_value']),
            'start_value': str(performance['start_value']),
            'change': str(performance['change']),
            'change_pct': str(performance['change_pct']),
            'realized_pnl': str(performance['realized_pnl']),
            'unrealized_pnl': str(performance['unrealized_pnl']),
            'total_pnl': str(performance['total_pnl']),
            'calculated_at': str(timezone.now())
        }
        portfolio.save()

        logger.info(f"Calculated performance for portfolio {portfolio_id}: {performance['change_pct']}%")

        return performance

    except Portfolio.DoesNotExist:
        logger.error(f"Portfolio {portfolio_id} not found")
        return {'error': 'Portfolio not found'}

    except Exception as e:
        logger.error(f"Error calculating performance for portfolio {portfolio_id}: {e}")
        raise


@shared_task(bind=True)
def reconcile_all_portfolios(self):
    """
    Reconcile all active portfolios with their brokers.

    Runs daily to ensure database is in sync with broker accounts.
    """
    try:
        portfolios = Portfolio.objects.filter(is_active=True)

        queued = 0
        for portfolio in portfolios:
            reconcile_portfolio_positions.delay(portfolio.id)
            queued += 1

        logger.info(f"Queued reconciliation for {queued} portfolios")

        return {
            'queued': queued,
            'total': portfolios.count()
        }

    except Exception as e:
        logger.error(f"Error in reconcile_all_portfolios: {e}")
        raise


@shared_task(bind=True)
def update_all_portfolio_values(self):
    """
    Update values for all active portfolios.

    Runs periodically to keep portfolio values current.
    """
    try:
        portfolios = Portfolio.objects.filter(is_active=True)

        queued = 0
        for portfolio in portfolios:
            update_portfolio_value.delay(portfolio.id)
            queued += 1

        logger.info(f"Queued value updates for {queued} portfolios")

        return {
            'queued': queued,
            'total': portfolios.count()
        }

    except Exception as e:
        logger.error(f"Error in update_all_portfolio_values: {e}")
        raise
