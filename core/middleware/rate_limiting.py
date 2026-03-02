"""
Rate limiting middleware for API protection.

Implements token bucket algorithm with Redis backend.
"""
from django.core.cache import cache
from django.http import JsonResponse
from django.conf import settings
import time
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """
    Rate limiting middleware using token bucket algorithm.

    Limits requests per IP address and per user.
    """

    # Rate limit configurations
    RATE_LIMITS = {
        'anonymous': {
            'requests': 100,  # requests
            'window': 3600,   # per hour
        },
        'authenticated': {
            'requests': 1000,  # requests
            'window': 3600,    # per hour
        },
        'api': {
            'requests': 5000,  # requests
            'window': 3600,    # per hour
        }
    }

    # Endpoints with stricter limits
    STRICT_ENDPOINTS = {
        '/api/orders/': {'requests': 100, 'window': 3600},
        '/api/brokers/': {'requests': 50, 'window': 3600},
        '/api/strategies/execute/': {'requests': 50, 'window': 3600},
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip rate limiting for certain paths
        if self._should_skip(request):
            return self.get_response(request)

        # Get rate limit key
        key = self._get_rate_limit_key(request)

        # Get rate limit config
        config = self._get_rate_limit_config(request)

        # Check rate limit
        is_allowed, retry_after = self._check_rate_limit(
            key, config['requests'], config['window']
        )

        if not is_allowed:
            logger.warning(f"Rate limit exceeded for {key}")
            return JsonResponse({
                'error': 'Rate limit exceeded',
                'retry_after': retry_after
            }, status=429, headers={
                'Retry-After': str(retry_after),
                'X-RateLimit-Limit': str(config['requests']),
                'X-RateLimit-Remaining': '0',
                'X-RateLimit-Reset': str(int(time.time() + retry_after))
            })

        # Add rate limit headers to response
        response = self.get_response(request)

        remaining = self._get_remaining_requests(key, config['requests'])
        response['X-RateLimit-Limit'] = str(config['requests'])
        response['X-RateLimit-Remaining'] = str(remaining)
        response['X-RateLimit-Reset'] = str(int(time.time() + config['window']))

        return response

    def _should_skip(self, request):
        """Check if rate limiting should be skipped."""
        # Skip for admin
        if request.path.startswith('/admin/'):
            return True

        # Skip for health checks
        if request.path in ['/health/', '/ping/']:
            return True

        # Skip for static/media
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return True

        return False

    def _get_rate_limit_key(self, request):
        """Get unique key for rate limiting."""
        # Use user ID if authenticated
        if request.user and request.user.is_authenticated:
            return f"ratelimit:user:{request.user.id}"

        # Use IP address for anonymous
        ip = self._get_client_ip(request)
        return f"ratelimit:ip:{ip}"

    def _get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def _get_rate_limit_config(self, request):
        """Get rate limit configuration for request."""
        # Check for strict endpoint limits
        for endpoint, config in self.STRICT_ENDPOINTS.items():
            if request.path.startswith(endpoint):
                return config

        # Check if user is authenticated
        if request.user and request.user.is_authenticated:
            # Check if API key is used (higher limits)
            if 'HTTP_AUTHORIZATION' in request.META:
                return self.RATE_LIMITS['api']
            return self.RATE_LIMITS['authenticated']

        return self.RATE_LIMITS['anonymous']

    def _check_rate_limit(self, key, max_requests, window):
        """
        Check if request is within rate limit using token bucket.

        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        current_time = time.time()

        # Get current bucket state
        bucket = cache.get(key, {
            'tokens': max_requests,
            'last_update': current_time
        })

        # Calculate tokens to add based on time passed
        time_passed = current_time - bucket['last_update']
        tokens_to_add = (time_passed / window) * max_requests

        # Update tokens (capped at max_requests)
        bucket['tokens'] = min(max_requests, bucket['tokens'] + tokens_to_add)
        bucket['last_update'] = current_time

        # Check if request is allowed
        if bucket['tokens'] >= 1:
            bucket['tokens'] -= 1
            cache.set(key, bucket, window)
            return True, 0
        else:
            # Calculate retry after
            tokens_needed = 1 - bucket['tokens']
            retry_after = int((tokens_needed / max_requests) * window)
            cache.set(key, bucket, window)
            return False, retry_after

    def _get_remaining_requests(self, key, max_requests):
        """Get remaining requests in current window."""
        bucket = cache.get(key)
        if bucket:
            return int(bucket['tokens'])
        return max_requests


class IPWhitelistMiddleware:
    """
    Middleware to whitelist certain IP addresses from rate limiting.

    Useful for internal services, monitoring tools, etc.
    """

    WHITELISTED_IPS = getattr(settings, 'WHITELISTED_IPS', [
        '127.0.0.1',
        'localhost',
    ])

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = self._get_client_ip(request)

        if ip in self.WHITELISTED_IPS:
            request.rate_limit_exempt = True

        return self.get_response(request)

    def _get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


# Decorator for function-based views
def rate_limit(requests=100, window=3600):
    """
    Decorator to add rate limiting to individual views.

    Args:
        requests: Number of requests allowed
        window: Time window in seconds

    Example:
        @rate_limit(requests=10, window=60)
        def my_view(request):
            ...
    """
    def decorator(func):
        def wrapper(request, *args, **kwargs):
            from django.core.cache import cache
            import time

            # Get rate limit key
            if request.user and request.user.is_authenticated:
                key = f"ratelimit:user:{request.user.id}:{func.__name__}"
            else:
                ip = request.META.get('REMOTE_ADDR')
                key = f"ratelimit:ip:{ip}:{func.__name__}"

            current_time = time.time()

            # Get current bucket state
            bucket = cache.get(key, {
                'tokens': requests,
                'last_update': current_time
            })

            # Calculate tokens to add
            time_passed = current_time - bucket['last_update']
            tokens_to_add = (time_passed / window) * requests

            # Update tokens
            bucket['tokens'] = min(requests, bucket['tokens'] + tokens_to_add)
            bucket['last_update'] = current_time

            # Check if allowed
            if bucket['tokens'] >= 1:
                bucket['tokens'] -= 1
                cache.set(key, bucket, window)
                return func(request, *args, **kwargs)
            else:
                return JsonResponse({
                    'error': 'Rate limit exceeded'
                }, status=429)

        return wrapper
    return decorator
