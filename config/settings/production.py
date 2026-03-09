"""
Production settings
"""
from .base import *
from core.monitoring.sentry_config import init_sentry
import os

DEBUG = False

# Load SENTRY_DSN into os.environ so init_sentry() can access it
sentry_dsn = config('SENTRY_DSN', default='')
if sentry_dsn:
    os.environ['SENTRY_DSN'] = sentry_dsn

init_sentry()

ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())

CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', cast=Csv())

# Security settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# CORS settings
cors_origins = config('CORS_ALLOWED_ORIGINS', cast=Csv())
CORS_ALLOW_CREDENTIALS = True

# Email settings - Using Resend for ALL emails (including django-allauth)
EMAIL_BACKEND = 'core.email_backends.ResendEmailBackend'
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@shefaai.com')

# SMTP settings (kept as fallback, not used when Resend backend is active)
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Sentry integration
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN and SENTRY_DSN.startswith(('http://', 'https://')):
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
    )
