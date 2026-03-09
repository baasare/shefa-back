"""
Development settings
"""
from .base import *

DEBUG = True

ALLOWED_HOSTS = ['localhost', 'api.localhost', '127.0.0.1', '0.0.0.0']

# CORS settings for development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# CSRF settings for development
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8000',
]

# Development-specific installed apps
INSTALLED_APPS += [
    'django_extensions',
]

# Email backend for development
# Use console backend for local development (prints to console)
# To test Resend in development, comment out line below and use:
# EMAIL_BACKEND = 'core.email_backends.ResendEmailBackend'
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Logging
LOGGING['root']['level'] = 'DEBUG'
