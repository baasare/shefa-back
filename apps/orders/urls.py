"""
Order URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.orders import views

router = DefaultRouter()
router.register(r'', views.OrderViewSet, basename='order')
router.register(r'trades', views.TradeViewSet, basename='trade')

urlpatterns = [
    path('', include(router.urls)),
]
