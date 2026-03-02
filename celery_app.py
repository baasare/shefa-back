"""
Celery configuration for ShefaAI Trading Platform.
"""
import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('shefa')

# Load config from Django settings with CELERY namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Celery Beat schedule for autonomous trading
app.conf.beat_schedule = {
    # Run active agents every minute during market hours
    'run-active-agents': {
        'task': 'apps.agents.tasks.run_all_active_agents',
        'schedule': 60.0,  # Every 60 seconds
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
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
