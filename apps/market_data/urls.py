"""
Market Data URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'quotes', views.QuoteViewSet, basename='quote')
router.register(r'indicators', views.IndicatorViewSet, basename='indicator')

urlpatterns = [
    path('', include(router.urls)),
]
