"""
Celery tasks for strategy execution, backtesting, and monitoring.
"""
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import asyncio

from .models import Strategy, Backtest
from .executor import execute_strategy_sync
from .backtest import run_backtest
from .validator import validate_strategy

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3)
def execute_strategy_task(self, strategy_id: str, symbol: str = None, dry_run: bool = False):
    """
    Execute strategy in background.

    Args:
        strategy_id: Strategy UUID
        symbol: Optional specific symbol
        dry_run: Signal generation only
    """
    try:
        logger.info(f"Executing strategy {strategy_id} (dry_run={dry_run})")

        result = execute_strategy_sync(strategy_id, symbol, dry_run)

        logger.info(f"Strategy execution completed: {result.get('summary', {})}")

        return result

    except Exception as e:
        logger.error(f"Error executing strategy {strategy_id}: {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True)
def execute_all_active_strategies(self, dry_run: bool = False):
    """
    Execute all active strategies.

    Runs periodically to evaluate strategies on their watchlists.

    Args:
        dry_run: If True, only generates signals without placing orders
    """
    try:
        strategies = Strategy.objects.filter(status='active')

        logger.info(f"Executing {strategies.count()} active strategies")

        results = []
        for strategy in strategies:
            try:
                result = execute_strategy_sync(str(strategy.id), dry_run=dry_run)
                results.append({
                    'strategy_id': str(strategy.id),
                    'success': True,
                    'result': result
                })
            except Exception as e:
                logger.error(f"Error executing strategy {strategy.id}: {e}")
                results.append({
                    'strategy_id': str(strategy.id),
                    'success': False,
                    'error': str(e)
                })

        return {
            'total': strategies.count(),
            'results': results
        }

    except Exception as e:
        logger.error(f"Error in execute_all_active_strategies: {e}")
        raise


@shared_task(bind=True, max_retries=1)
def run_backtest_task(
    self,
    strategy_id: str,
    start_date_str: str,
    end_date_str: str,
    initial_capital: str
):
    """
    Run backtest in background.

    Args:
        strategy_id: Strategy UUID
        start_date_str: Start date (ISO format)
        end_date_str: End date (ISO format)
        initial_capital: Initial capital amount
    """
    try:
        from datetime import datetime

        strategy = Strategy.objects.get(id=strategy_id)
        start_date = datetime.fromisoformat(start_date_str).date()
        end_date = datetime.fromisoformat(end_date_str).date()
        capital = Decimal(initial_capital)

        logger.info(f"Starting backtest for strategy {strategy_id}")

        # Update backtest status to running
        backtest = Backtest.objects.create(
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=capital,
            status='running'
        )

        # Run backtest
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_backtest(
                strategy, start_date, end_date, capital
            ))
        finally:
            loop.close()

        logger.info(f"Backtest completed for strategy {strategy_id}: {result.total_return}% return")

        return {
            'backtest_id': str(result.id),
            'total_return': float(result.total_return),
            'win_rate': float(result.win_rate),
            'total_trades': result.total_trades
        }

    except Strategy.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {'error': 'Strategy not found'}

    except Exception as e:
        logger.error(f"Backtest failed for strategy {strategy_id}: {e}")
        raise self.retry(exc=e, countdown=120)


@shared_task(bind=True)
def validate_strategy_task(self, strategy_id: str):
    """
    Validate strategy configuration.

    Args:
        strategy_id: Strategy UUID
    """
    try:
        strategy = Strategy.objects.get(id=strategy_id)

        is_valid, errors, warnings = validate_strategy(strategy)

        logger.info(f"Validated strategy {strategy_id}: valid={is_valid}")

        return {
            'strategy_id': strategy_id,
            'is_valid': is_valid,
            'errors': errors,
            'warnings': warnings
        }

    except Strategy.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {'error': 'Strategy not found'}

    except Exception as e:
        logger.error(f"Error validating strategy {strategy_id}: {e}")
        raise


@shared_task(bind=True)
def update_strategy_performance_metrics(self, strategy_id: str):
    """
    Update strategy performance metrics from trades.

    Args:
        strategy_id: Strategy UUID
    """
    try:
        from apps.orders.models import Order

        strategy = Strategy.objects.get(id=strategy_id)

        # Get all filled orders for this strategy
        orders = Order.objects.filter(
            strategy_id=strategy_id,
            status='filled'
        )

        if not orders.exists():
            return {'strategy_id': strategy_id, 'trades': 0}

        # Calculate metrics
        # This is a simplified version - should match trades to calculate actual P&L
        total_trades = orders.count()

        # For now, use order metadata if available
        # In production, calculate from matched buy/sell pairs

        strategy.total_trades = total_trades
        strategy.save()

        logger.info(f"Updated performance for strategy {strategy_id}: {total_trades} trades")

        return {
            'strategy_id': strategy_id,
            'total_trades': total_trades
        }

    except Strategy.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return {'error': 'Strategy not found'}

    except Exception as e:
        logger.error(f"Error updating strategy performance: {e}")
        raise


@shared_task(bind=True)
def cleanup_old_backtests(self, days: int = 90):
    """
    Clean up old backtest results.

    Args:
        days: Delete backtests older than this many days
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days)

        deleted_count = Backtest.objects.filter(
            created_at__lt=cutoff_date,
            status='completed'
        ).delete()[0]

        logger.info(f"Deleted {deleted_count} old backtests (older than {days} days)")

        return {'deleted': deleted_count}

    except Exception as e:
        logger.error(f"Error cleaning up backtests: {e}")
        raise


# Celery Beat schedule configuration
# Add to celeryconfig.py or settings:
"""
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # Execute active strategies every hour during market hours
    'execute-active-strategies': {
        'task': 'apps.strategies.tasks.execute_all_active_strategies',
        'schedule': crontab(minute=0),  # Every hour
        'kwargs': {'dry_run': False}
    },

    # Cleanup old backtests weekly
    'cleanup-old-backtests': {
        'task': 'apps.strategies.tasks.cleanup_old_backtests',
        'schedule': crontab(hour=2, minute=0, day_of_week=0),  # Sunday 2 AM
        'kwargs': {'days': 90}
    },
}
"""
