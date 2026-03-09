"""
Comprehensive logging configuration for files and cloud.

Supports:
- Local file logging with rotation
- S3 storage for logs (Supabase) with time-based uploads
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
import boto3
from botocore.client import Config
import threading
import time
import shutil


class S3LogUploader:
    """
    Background uploader that periodically syncs local logs to S3.
    """
    
    def __init__(self, log_path, environment='development', upload_interval=120):
        """
        Initialize S3 log uploader.
        
        Args:
            log_path: Path to local log directory
            environment: Environment name (development, production, etc.)
            upload_interval: Seconds between uploads (default: 300 = 5 minutes)
        """
        self.log_path = Path(log_path)
        self.environment = environment
        self.upload_interval = upload_interval
        self.s3_client = self._get_s3_client()
        self.running = False
        self.thread = None
        
    def _get_s3_client(self):
        """Initialize S3 client for Supabase Storage."""
        try:
            s3_client = boto3.client(
                's3',
                endpoint_url=os.environ.get('S3_ENDPOINT'),
                aws_access_key_id=os.environ.get('S3_ACCESS_KEY_ID'),
                aws_secret_access_key=os.environ.get('S3_SECRET_ACCESS_KEY'),
                region_name=os.environ.get('S3_REGION', 'us-east-1'),
                config=Config(signature_version='s3v4')
            )
            return s3_client
        except Exception as e:
            print(f"Failed to initialize S3 client: {e}")
            return None
    
    def start(self):
        """Start the background upload thread."""
        if self.s3_client and not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._upload_loop, daemon=True)
            self.thread.start()
            print(f"S3 log uploader started (uploads every {self.upload_interval}s)")
    
    def stop(self):
        """Stop the background upload thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
    
    def _upload_loop(self):
        """Background loop that uploads logs periodically."""
        while self.running:
            try:
                self._upload_logs()
            except Exception as e:
                print(f"Error uploading logs to S3: {e}")
            
            # Sleep in small intervals to allow quick shutdown
            for _ in range(self.upload_interval):
                if not self.running:
                    break
                time.sleep(1)
    
    def _upload_logs(self):
        """Upload all log files to S3."""
        if not self.s3_client or not self.log_path.exists():
            return
        
        bucket_name = os.environ.get('S3_BUCKET_NAME', 'shefa-logs')
        timestamp = datetime.utcnow().strftime('%Y/%m/%d/%H')
        
        for log_file in self.log_path.glob('*.log*'):
            if log_file.is_file() and log_file.stat().st_size > 0:
                try:
                    # Generate S3 key
                    s3_key = f"{self.environment}/logs/{timestamp}/{log_file.name}"
                    
                    # Upload to S3
                    self.s3_client.upload_file(
                        str(log_file),
                        bucket_name,
                        s3_key
                    )
                    
                    print(f"Uploaded {log_file.name} to S3: {s3_key}")
                    
                except Exception as e:
                    print(f"Failed to upload {log_file.name}: {e}")


class S3RotatingFileHandler(logging.handlers.RotatingFileHandler):
    """
    Rotating file handler with S3 upload on rotation (backup mechanism).
    """

    def __init__(self, *args, environment='development', **kwargs):
        super().__init__(*args, **kwargs)
        self.environment = environment
        self.s3_client = self._get_s3_client()

    def _get_s3_client(self):
        """Initialize S3 client for Supabase Storage."""
        try:
            s3_client = boto3.client(
                's3',
                endpoint_url=os.environ.get('S3_ENDPOINT'),
                aws_access_key_id=os.environ.get('S3_ACCESS_KEY_ID'),
                aws_secret_access_key=os.environ.get('S3_SECRET_ACCESS_KEY'),
                region_name=os.environ.get('S3_REGION', 'us-east-1'),
                config=Config(signature_version='s3v4')
            )
            return s3_client
        except Exception as e:
            logging.error(f"Failed to initialize S3 client: {e}")
            return None

    def doRollover(self):
        """
        Override doRollover to upload rotated log to S3.
        """
        super().doRollover()

        # Upload the rotated file to S3
        if self.s3_client:
            try:
                # The rotated file will have a .1 extension
                rotated_file = f"{self.baseFilename}.1"
                if os.path.exists(rotated_file):
                    # Generate S3 key with environment and timestamp
                    timestamp = datetime.utcnow().strftime('%Y/%m/%d/%H')
                    filename = Path(rotated_file).name
                    s3_key = f"{self.environment}/logs/rotated/{timestamp}/{filename}"

                    # Upload to S3
                    bucket_name = os.environ.get('S3_BUCKET_NAME', 'shefa-logs')
                    self.s3_client.upload_file(
                        rotated_file,
                        bucket_name,
                        s3_key
                    )

                    logging.info(f"Uploaded rotated log to S3: {s3_key}")

                    # Delete local rotated file to save space
                    os.remove(rotated_file)

            except Exception as e:
                logging.error(f"Failed to upload log to S3: {e}")


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


def setup_logging(log_dir='logs', environment='development', upload_interval=300):
    """
    Setup comprehensive logging configuration.

    Args:
        log_dir: Directory for log files
        environment: Environment name (development, staging, production)
        upload_interval: Seconds between S3 uploads (default: 300 = 5 minutes)
    """
    # Create log directory with absolute path
    if not os.path.isabs(log_dir):
        # Convert relative path to absolute based on project root
        base_dir = Path(__file__).resolve().parent.parent.parent
        log_path = base_dir / log_dir
    else:
        log_path = Path(log_dir)
    
    log_path.mkdir(parents=True, exist_ok=True)

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
    setup_file_handlers(log_path, root_logger, environment)

    # Start S3 uploader (uploads logs periodically)
    uploader = S3LogUploader(log_path, environment, upload_interval)
    uploader.start()

    # Cloud logging handlers
    if environment in ['staging', 'production']:
        setup_cloud_logging(root_logger, environment)

    # Component-specific loggers
    setup_component_loggers()

    logging.info(f"Logging configured for environment: {environment}")


def setup_file_handlers(log_path, root_logger, environment='development'):
    """Setup file handlers with rotation and S3 upload on rotate."""

    # General application log
    general_handler = S3RotatingFileHandler(
        log_path / 'app.log',
        maxBytes=5 * 1024 * 1024,  # 10MB
        backupCount=10,
        environment=environment
    )
    general_handler.setLevel(logging.INFO)
    general_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(general_handler)

    # Error log
    error_handler = S3RotatingFileHandler(
        log_path / 'errors.log',
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
        environment=environment
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(error_handler)

    # Trading activity log (critical for audit)
    trading_handler = S3RotatingFileHandler(
        log_path / 'trading.log',
        maxBytes=5 * 1024 * 1024,  # 50MB
        backupCount=20,
        environment=environment
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
    security_handler = S3RotatingFileHandler(
        log_path / 'security.log',
        maxBytes=5 * 1024 * 1024,
        backupCount=20,
        environment=environment
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

    # Orders logger
    orders_logger = logging.getLogger('apps.orders')
    orders_logger.setLevel(logging.DEBUG)

    # Strategies logger
    strategies_logger = logging.getLogger('apps.strategies')
    strategies_logger.setLevel(logging.INFO)

    # Market data logger
    market_data_logger = logging.getLogger('apps.market_data')
    market_data_logger.setLevel(logging.INFO)

    # Brokers logger
    brokers_logger = logging.getLogger('apps.brokers')
    brokers_logger.setLevel(logging.DEBUG)

    # Django logger
    django_logger = logging.getLogger('django')
    django_logger.setLevel(logging.INFO)

    # Celery logger
    celery_logger = logging.getLogger('celery')
    celery_logger.setLevel(logging.INFO)


def get_logging_config():
    """
    Generate logging configuration with proper log directory creation.
    
    Returns:
        dict: Logging configuration dictionary
    """
    # Ensure logs directory exists (production-safe)
    base_dir = Path(__file__).resolve().parent.parent.parent
    log_dir = base_dir / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    return {
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
                'filename': str(log_dir / 'app.log'),
                'maxBytes': 10485760,  # 10MB
                'backupCount': 10,
                'formatter': 'json',
            },
            'error_file': {
                'level': 'ERROR',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': str(log_dir / 'errors.log'),
                'maxBytes': 10485760,
                'backupCount': 10,
                'formatter': 'json',
            },
            'trading_file': {
                'level': 'INFO',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': str(log_dir / 'trading.log'),
                'maxBytes': 52428800,  # 50MB
                'backupCount': 20,
                'formatter': 'json',
            },
            'security_file': {
                'level': 'WARNING',
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': str(log_dir / 'security.log'),
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


# For backward compatibility
LOGGING_CONFIG = get_logging_config()
