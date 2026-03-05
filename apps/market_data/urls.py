"""
Market Data URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'quotes', views.QuoteViewSet, basename='quote')
router.register(r'indicators', views.IndicatorViewSet, basename='indicator')
router.register(r'screener', views.StockScreenerViewSet, basename='screener')
router.register(r'watchlist', views.WatchlistViewSet, basename='watchlist')

urlpatterns = [
    path('', include(router.urls)),
    path('overview/', views.MarketOverviewView.as_view(), name='market-overview'),
]
