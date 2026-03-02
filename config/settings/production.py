"""
Production settings
"""
from .base import *
from core.monitoring.sentry_config import init_sentry

DEBUG = False

init_sentry()

allowed_hosts = config('ALLOWED_HOSTS', default='')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts.split(',') if host.strip()]

# Security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# CORS settings
cors_origins = config('CORS_ALLOWED_ORIGINS', default='')
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_origins.split(',') if origin.strip()]
CORS_ALLOW_CREDENTIALS = True

# Email settings (configure with production email service)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

# Sentry integration
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN and SENTRY_DSN.startswith(('http://', 'https://')):
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
    )
