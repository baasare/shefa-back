"""
Agent URLs
"""
from django.urls import path
from apps.agents.views import TradingAgentStreamView, AgentListView

app_name = 'agents'

urlpatterns = [
    path('', AgentListView.as_view(), name='agent-list'),
    path('stream/', TradingAgentStreamView.as_view(), name='agent-stream'),
]
