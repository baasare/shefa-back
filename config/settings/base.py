"""
Base settings for ShefaFx Trading Platform.
"""
from pathlib import Path
from decouple import config
from datetime import timedelta

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-this-in-production')

# Application definition
INSTALLED_APPS = [
    'daphne',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    'django_json_widget',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'dj_rest_auth',
    'dj_rest_auth.registration',

    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',

    'django_celery_beat',
    'django_celery_results',

    'apps.users',
    'apps.portfolios',
    'apps.strategies',
    'apps.orders',
    'apps.agents',
    'apps.market_data',
    'apps.brokers',
    'apps.notifications',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'core.middleware.rate_limiting.RateLimitMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'core.admin_2fa.Admin2FAMiddleware',
    'apps.orders.audit.middleware.AuditMiddleware',
    'apps.users.middleware.SessionMetadataMiddleware'
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('POSTGRES_DB_NAME', default='shefa_db'),
        'USER': config('POSTGRES_USER', default='postgres'),
        'PASSWORD': config('POSTGRES_PASSWORD', default='postgres'),
        'HOST': config('POSTGRES_HOST', default='localhost'),
        'PORT': config('POSTGRES_PORT', default='5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTHENTICATION_BACKENDS = [
    'allauth.account.auth_backends.AuthenticationBackend',
    'django.contrib.auth.backends.ModelBackend',
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'users.User'

SITE_ID = 1

FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000')

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ('rest_framework.renderers.JSONRenderer',),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

REST_AUTH = {
    'USE_JWT': True,
    'JWT_AUTH_COOKIE': 'jwt-auth',
    'JWT_AUTH_REFRESH_COOKIE': 'jwt-refresh-token',
    'JWT_AUTH_HTTPONLY': False,
    'REGISTER_SERIALIZER': 'apps.users.serializers.CustomRegisterSerializer',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'TOKEN_REFRESH_SERIALIZER': 'apps.users.serializers.CustomTokenRefreshSerializer',
}

# Django Allauth Configuration
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 1
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_ADAPTER = 'core.allauth_adapter.CustomAccountAdapter'

# Social Account Configuration
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APPS': [
            {
                'client_id': config('GOOGLE_OAUTH_CLIENT_ID', default=''),
                'secret': config('GOOGLE_OAUTH_CLIENT_SECRET', default=''),
                'key': '',
            },
        ],
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
    }
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Resend Email Configuration
RESEND_API_KEY = config('RESEND_API_KEY', default='')
RESEND_FROM_EMAIL = config('RESEND_FROM_EMAIL', default='noreply@shefafx.com')
RESEND_FROM_NAME = config('RESEND_FROM_NAME', default='ShefaFx Trading')

# Spectacular API Documentation
SPECTACULAR_SETTINGS = {
    'TITLE': 'ShefaFx Trading Platform API',
    'DESCRIPTION': 'AI-powered autonomous trading agent platform',
    'VERSION': '1.0.0',
    'COMPONENT_SPLIT_REQUEST': True,
    'SERVE_INCLUDE_SCHEMA': True,
    'SECURITY': [{'bearerAuth': []}],
    'COMPONENTS': {
        'securitySchemes': {
            'bearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
                'description': 'JWT Authorization header using the Bearer scheme.'
            }
        }
    },
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
    }
}

CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = 'django-db'

ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')
ALPACA_API_KEY = config('ALPACA_API_KEY', default='')
ALPACA_API_SECRET = config('ALPACA_API_SECRET', default='')

# Encryption key rotation configuration
ENCRYPTION_KEY = config('ENCRYPTION_KEY', default=None)
ENCRYPTION_KEY_OLD_1 = config('ENCRYPTION_KEY_OLD_1', default=None)
ENCRYPTION_KEY_OLD_2 = config('ENCRYPTION_KEY_OLD_2', default=None)
ENCRYPTION_KEY_OLD_3 = config('ENCRYPTION_KEY_OLD_3', default=None)
ENCRYPTION_KEY_OLD_4 = config('ENCRYPTION_KEY_OLD_4', default=None)
ENCRYPTION_KEY_OLD_5 = config('ENCRYPTION_KEY_OLD_5', default=None)

# Logging configuration
from core.monitoring.logging_config import LOGGING_CONFIG as LOGGING
