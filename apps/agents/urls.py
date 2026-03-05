"""
Agent URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.agents import views

router = DefaultRouter()
router.register(r'', views.AgentViewSet, basename='agent')
router.register(r'runs', views.AgentRunViewSet, basename='agentrun')
router.register(r'decisions', views.AgentDecisionViewSet, basename='agentdecision')
router.register(r'logs', views.AgentLogViewSet, basename='agentlog')

urlpatterns = [
    path('', include(router.urls)),
    # Agent analysis endpoints
    path('analyze-stock/', views.AgentAnalysisViewSet.as_view({'post': 'analyze_stock'}), name='analyze-stock'),
    path('monitor-watchlist/', views.AgentAnalysisViewSet.as_view({'post': 'monitor_watchlist'}), name='monitor-watchlist'),
    path('execute-autonomous-trade/', views.AgentAnalysisViewSet.as_view({'post': 'execute_trade'}), name='execute-trade'),
]
