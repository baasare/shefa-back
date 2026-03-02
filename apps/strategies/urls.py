"""
Strategy URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'strategies', views.StrategyViewSet, basename='strategy')
router.register(r'backtests', views.BacktestViewSet, basename='backtest')

urlpatterns = [
    path('', include(router.urls)),
]
