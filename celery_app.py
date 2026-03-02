"""
Celery configuration for ShefaAI Trading Platform.
"""
import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

# Load config from Django settings with CELERY namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Reconnect on startup
app.conf.broker_connection_retry_on_startup = True

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Celery Beat schedule for autonomous trading
app.conf.beat_schedule = {
    # Run periodic agent scan every 15 minutes during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
    'run-periodic-agent-scan': {
        'task': 'apps.agents.tasks.run_periodic_agent_scan',
        'schedule': crontab(minute='*/15', hour='9-16', day_of_week='1-5'),  # Every 15 min during market hours
    },
    # Sync market data every 30 seconds
    'sync-market-data': {
        'task': 'apps.market_data.tasks.sync_latest_quotes',
        'schedule': 30.0,
    },
    # Daily end-of-day portfolio reconciliation
    'daily-portfolio-reconciliation': {
        'task': 'apps.portfolios.tasks.reconcile_end_of_day',
        'schedule': crontab(hour=16, minute=30),  # 4:30 PM EST (market close)
    },
    # Weekly backtest validation
    'weekly-backtest-validation': {
        'task': 'apps.strategies.tasks.validate_all_strategies',
        'schedule': crontab(day_of_week=6, hour=10, minute=0),  # Saturday 10 AM
    },
    'send-daily-summaries': {
        'task': 'apps.notifications.tasks.send_daily_summaries_to_all',
        'schedule': crontab(hour=17, minute=0),  # 5 PM daily
    },
    # Order monitoring
    'monitor-pending-orders': {
        'task': 'apps.orders.tasks.monitor_pending_orders',
        'schedule': 30.0,  # Every 30 seconds
    },
    'check-stale-orders': {
        'task': 'apps.orders.tasks.check_stale_orders',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
    'cleanup-old-orders': {
        'task': 'apps.orders.tasks.cleanup_old_orders',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
        'kwargs': {'days': 90}
    },
    # Portfolio snapshots - daily at market close (4:30 PM ET)
    'create-daily-snapshots': {
        'task': 'apps.portfolios.tasks.create_daily_snapshots',
        'schedule': crontab(hour=16, minute=30),
    },
    # Update portfolio values - every 5 minutes during market hours
    'update-all-portfolio-values': {
        'task': 'apps.portfolios.tasks.update_all_portfolio_values',
        'schedule': 300.0,  # 5 minutes
    },
    # Reconcile with broker - daily at 5 PM ET
    'reconcile-all-portfolios': {
        'task': 'apps.portfolios.tasks.reconcile_all_portfolios',
        'schedule': crontab(hour=17, minute=0),
    },

    # Cleanup old snapshots - weekly on Sunday at 3 AM
    'cleanup-old-snapshots': {
        'task': 'apps.portfolios.tasks.cleanup_old_snapshots',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),
        'kwargs': {'days': 365}
    },
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

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
