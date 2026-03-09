from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from core.admin_2fa import secure_admin_site

urlpatterns = [
    # Admin
    path('admin/', secure_admin_site.urls, name="admin"),
    # API Documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # App URLs
    path('v1/', include('apps.users.urls')),
    path('v1/agents/', include('apps.agents.urls')),
    path('v1/', include('apps.portfolios.urls')),
    path('v1/', include('apps.strategies.urls')),
    path('v1/', include('apps.orders.urls')),
    path('v1/market-data/', include('apps.market_data.urls')),
    path('v1/brokers/', include('apps.brokers.urls')),
    path('v1/notifications/', include('apps.notifications.urls')),
]