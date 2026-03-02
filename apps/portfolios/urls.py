"""
Portfolio URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.portfolios import views

router = DefaultRouter()
router.register(r'portfolios', views.PortfolioViewSet, basename='portfolio')
router.register(r'positions', views.PositionViewSet, basename='position')
router.register(r'snapshots', views.PortfolioSnapshotViewSet, basename='snapshot')

urlpatterns = [
    path('', include(router.urls)),
]
