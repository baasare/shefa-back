"""
Sentry error tracking and performance monitoring configuration.
"""
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import logging
import os


def init_sentry():
    """
    Initialize Sentry error tracking and APM.

    Call this in settings.py or wsgi.py
    """
    sentry_dsn = os.environ.get('SENTRY_DSN')
    environment = os.environ.get('ENVIRONMENT', 'development')

    if not sentry_dsn:
        logging.warning("SENTRY_DSN not set. Sentry will not be initialized.")
        return

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=environment,

        # Integrations
        integrations=[
            DjangoIntegration(
                transaction_style='url',
                middleware_spans=True,
                signals_spans=True,
                cache_spans=True,
            ),
            CeleryIntegration(
                monitor_beat_tasks=True,
                propagate_traces=True,
            ),
            RedisIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR
            ),
        ],

        # Performance monitoring
        traces_sample_rate=1.0 if environment == 'development' else 0.1,

        # Profiles sample rate
        profiles_sample_rate=1.0 if environment == 'development' else 0.1,

        # Send PII (personally identifiable information)
        send_default_pii=False,  # IMPORTANT: Set to False for compliance

        # Release tracking
        release=os.environ.get('GIT_COMMIT_SHA', 'unknown'),

        # Before send hook for filtering
        before_send=before_send_filter,

        # Before breadcrumb hook
        before_breadcrumb=before_breadcrumb_filter,

        # Max request body size
        max_request_body_size='medium',  # 'small', 'medium', 'always'

        # Max value length
        max_value_length=1024,
    )

    logging.info(f"Sentry initialized for environment: {environment}")


def before_send_filter(event, hint):
    """
    Filter events before sending to Sentry.

    Use this to:
    - Remove sensitive data
    - Filter out certain errors
    - Add custom context
    """
    # Don't send certain exception types
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']

        # Filter out expected errors
        if isinstance(exc_value, (KeyboardInterrupt, SystemExit)):
            return None

    # Remove sensitive data from request
    if 'request' in event:
        request = event['request']

        # Remove sensitive headers
        if 'headers' in request:
            sensitive_headers = ['Authorization', 'Cookie', 'X-Api-Key']
            for header in sensitive_headers:
                if header in request['headers']:
                    request['headers'][header] = '[Filtered]'

        # Remove sensitive query params
        if 'query_string' in request:
            sensitive_params = ['password', 'token', 'api_key', 'secret']
            # This is simplified - implement proper filtering
            for param in sensitive_params:
                if param in str(request.get('query_string', '')):
                    request['query_string'] = '[Filtered]'

    # Remove sensitive data from extra context
    if 'extra' in event:
        sensitive_keys = ['api_key', 'api_secret', 'password', 'token']
        for key in list(event['extra'].keys()):
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                event['extra'][key] = '[Filtered]'

    return event


def before_breadcrumb_filter(crumb, hint):
    """
    Filter breadcrumbs before sending to Sentry.

    Breadcrumbs are trail of events leading to an error.
    """
    # Filter sensitive breadcrumb data
    if crumb.get('category') == 'http':
        # Remove sensitive headers from HTTP breadcrumbs
        if 'data' in crumb and 'headers' in crumb['data']:
            sensitive_headers = ['Authorization', 'Cookie']
            for header in sensitive_headers:
                if header in crumb['data']['headers']:
                    crumb['data']['headers'][header] = '[Filtered]'

    return crumb


def capture_trade_execution_context(trade):
    """
    Add trade execution context to Sentry.

    Call this when capturing trade-related errors.
    """
    sentry_sdk.set_context("trade", {
        "trade_id": str(trade.id),
        "symbol": trade.symbol,
        "side": trade.side,
        "quantity": trade.quantity,
        "price": float(trade.price),
    })


def capture_order_context(order):
    """Add order context to Sentry."""
    sentry_sdk.set_context("order", {
        "order_id": str(order.id),
        "symbol": order.symbol,
        "side": order.side,
        "type": order.type,
        "status": order.status,
        "quantity": order.quantity,
    })


def capture_strategy_context(strategy):
    """Add strategy context to Sentry."""
    sentry_sdk.set_context("strategy", {
        "strategy_id": str(strategy.id),
        "name": strategy.name,
        "type": strategy.strategy_type,
        "status": strategy.status,
    })


# Custom Sentry error classes
class TradingSystemError(Exception):
    """Base class for trading system errors."""
    pass


class OrderExecutionError(TradingSystemError):
    """Raised when order execution fails."""
    pass


class BrokerConnectionError(TradingSystemError):
    """Raised when broker connection fails."""
    pass


class StrategyEvaluationError(TradingSystemError):
    """Raised when strategy evaluation fails."""
    pass
