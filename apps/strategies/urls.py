"""
Strategy URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.strategies import views

router = DefaultRouter()
router.register(r'', views.StrategyViewSet, basename='strategy')
router.register(r'backtests', views.BacktestViewSet, basename='backtest')
router.register(r'templates', views.StrategyTemplateViewSet, basename='template')
router.register(r'watchlists', views.WatchlistViewSet, basename='watchlist')

urlpatterns = [
    path('', include(router.urls)),
]
