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
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # App URLs (includes authentication)
    path('api/', include('apps.users.urls')),  # Includes /api/auth/ endpoints
    path('api/agents/', include('apps.agents.urls')),
    path('api/portfolios/', include('apps.portfolios.urls')),
    path('api/strategies/', include('apps.strategies.urls')),
    path('api/orders/', include('apps.orders.urls')),
    path('api/market-data/', include('apps.market_data.urls')),
    path('api/brokers/', include('apps.brokers.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
