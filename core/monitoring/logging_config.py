"""
Comprehensive logging configuration for files and cloud.

Supports:
- Local file logging with rotation
- Cloud logging (AWS CloudWatch, Google Cloud Logging)
- Structured logging with JSON format
- Different log levels per component
"""
import logging
import logging.handlers
import os
from pathlib import Path
import json
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    """

    def format(self, record):
        """Format log record as JSON."""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id

        if hasattr(record, 'order_id'):
            log_data['order_id'] = record.order_id

        if hasattr(record, 'trade_id'):
            log_data['trade_id'] = record.trade_id

        if hasattr(record, 'strategy_id'):
            log_data['strategy_id'] = record.strategy_id

        return json.dumps(log_data)


def setup_logging(log_dir='logs', environment='development'):
    """
    Setup comprehensive logging configuration.

    Args:
        log_dir: Directory for log files
        environment: Environment name (development, staging, production)
    """
    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove existing handlers
    root_logger.handlers = []

    # Console handler (for development)
    if environment == 'development':
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # File handlers with rotation
    setup_file_handlers(log_path, root_logger)

    # Cloud logging handlers
    if environment in ['staging', 'production']:
        setup_cloud_logging(root_logger, environment)

    # Component-specific loggers
    setup_component_loggers()

    logging.info(f"Logging configured for environment: {environment}")


def setup_file_handlers(log_path, root_logger):
    """Setup file handlers with rotation."""

    # General application log
    general_handler = logging.handlers.RotatingFileHandler(
        log_path / 'app.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10
    )
    general_handler.setLevel(logging.INFO)
    general_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(general_handler)

    # Error log
    error_handler = logging.handlers.RotatingFileHandler(
        log_path / 'errors.log',
        maxBytes=10 * 1024 * 1024,
        backupCount=10
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(error_handler)

    # Trading activity log (critical for audit)
    trading_handler = logging.handlers.RotatingFileHandler(
        log_path / 'trading.log',
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=20
    )
    trading_handler.setLevel(logging.INFO)
    trading_handler.setFormatter(JSONFormatter())

    # Add filter to only log trading-related events
    trading_filter = lambda record: any(
        keyword in record.name for keyword in ['orders', 'trades', 'portfolios', 'strategies']
    )
    trading_handler.addFilter(trading_filter)
    root_logger.addHandler(trading_handler)

    # Security log
    security_handler = logging.handlers.RotatingFileHandler(
        log_path / 'security.log',
        maxBytes=10 * 1024 * 1024,
        backupCount=20
    )
    security_handler.setLevel(logging.WARNING)
    security_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(security_handler)


def setup_cloud_logging(root_logger, environment):
    """
    Setup cloud logging handlers.

    Supports AWS CloudWatch and Google Cloud Logging.
    """
    cloud_provider = os.environ.get('CLOUD_PROVIDER', '').lower()

    if cloud_provider == 'aws':
        setup_cloudwatch_logging(root_logger, environment)
    elif cloud_provider == 'gcp':
        setup_gcp_logging(root_logger, environment)


def setup_cloudwatch_logging(root_logger, environment):
    """Setup AWS CloudWatch logging."""
    try:
        import watchtower

        cloudwatch_handler = watchtower.CloudWatchLogHandler(
            log_group=f'/shefaai/{environment}',
            stream_name='{instance_id}',
            use_queues=True,
            send_interval=60,
            create_log_group=True
        )
        cloudwatch_handler.setLevel(logging.INFO)
        cloudwatch_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(cloudwatch_handler)

        logging.info("CloudWatch logging enabled")

    except ImportError:
        logging.warning("watchtower not installed. CloudWatch logging disabled.")
    except Exception as e:
        logging.error(f"Failed to setup CloudWatch logging: {e}")


def setup_gcp_logging(root_logger, environment):
    """Setup Google Cloud Logging."""
    try:
        from google.cloud import logging as gcp_logging

        client = gcp_logging.Client()
        client.setup_logging()

        logging.info("Google Cloud Logging enabled")

    except ImportError:
        logging.warning("google-cloud-logging not installed. GCP logging disabled.")
    except Exception as e:
        logging.error(f"Failed to setup GCP logging: {e}")


def setup_component_loggers():
    """Setup component-specific loggers with custom levels."""

    # Orders logger (CRITICAL)
    orders_logger = logging.getLogger('apps.orders')
    orders_logger.setLevel(logging.DEBUG)

    # Strategies logger
    strategies_logger = logging.getLogger('apps.strategies')
    strategies_logger.setLevel(logging.INFO)

    # Market data logger
    market_data_logger = logging.getLogger('apps.market_data')
    market_data_logger.setLevel(logging.INFO)

    # Brokers logger (CRITICAL)
    brokers_logger = logging.getLogger('apps.brokers')
    brokers_logger.setLevel(logging.DEBUG)

    # Django logger
    django_logger = logging.getLogger('django')
    django_logger.setLevel(logging.INFO)

    # Celery logger
    celery_logger = logging.getLogger('celery')
    celery_logger.setLevel(logging.INFO)


# Logging configuration for settings.py
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
        'json': {
            '()': 'core.monitoring.logging_config.JSONFormatter',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/app.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
            'formatter': 'json',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/errors.log',
            'maxBytes': 10485760,
            'backupCount': 10,
            'formatter': 'json',
        },
        'trading_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/trading.log',
            'maxBytes': 52428800,  # 50MB
            'backupCount': 20,
            'formatter': 'json',
        },
        'security_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/security.log',
            'maxBytes': 10485760,
            'backupCount': 20,
            'formatter': 'json',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.orders': {
            'handlers': ['console', 'file', 'trading_file', 'error_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'apps.strategies': {
            'handlers': ['console', 'file', 'trading_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.brokers': {
            'handlers': ['console', 'file', 'security_file', 'error_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'apps.portfolios': {
            'handlers': ['console', 'file', 'trading_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console', 'file', 'error_file'],
        'level': 'INFO',
    },
}


# Usage in settings.py:
"""
from core.monitoring.logging_config import LOGGING_CONFIG, setup_logging

# Use Django's LOGGING configuration
LOGGING = LOGGING_CONFIG

# Or use custom setup
setup_logging(
    log_dir='logs',
    environment=os.environ.get('ENVIRONMENT', 'development')
)
"""
