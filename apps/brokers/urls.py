"""
Broker URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.brokers import views

router = DefaultRouter()
router.register(r'connections', views.BrokerConnectionViewSet, basename='brokerconnection')

urlpatterns = [
    path('', include(router.urls)),
]
