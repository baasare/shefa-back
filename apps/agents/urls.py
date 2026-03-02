"""
Agent URL configuration.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.agents import views

router = DefaultRouter()
router.register(r'runs', views.AgentRunViewSet, basename='agentrun')
router.register(r'decisions', views.AgentDecisionViewSet, basename='agentdecision')
router.register(r'logs', views.AgentLogViewSet, basename='agentlog')

urlpatterns = [
    path('', include(router.urls)),
]
