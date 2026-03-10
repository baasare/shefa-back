"""
URL configuration for ShefaFx Trading Platform.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from core.admin_2fa import secure_admin_site

urlpatterns = [
    # Admin
    path('admin/', secure_admin_site.urls),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(urlconf='config.urls'), name='root-schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='root-schema'), name='root-swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='root-schema'), name='root-redoc'),

    # App URLs (includes authentication)
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/agents/', include('apps.agents.urls')),
    path('api/v1/portfolios/', include('apps.portfolios.urls')),
    path('api/v1/strategies/', include('apps.strategies.urls')),
    path('api/v1/orders/', include('apps.orders.urls')),
    path('api/v1/market-data/', include('apps.market_data.urls')),
    path('api/v1/brokers/', include('apps.brokers.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
