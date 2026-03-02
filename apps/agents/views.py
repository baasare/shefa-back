"""
Views for Agents, Market Data, Brokers, and Notifications.
"""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.agents.models import AgentRun, AgentDecision, AgentLog
from apps.agents.serializers import (
    AgentRunSerializer, AgentDecisionSerializer, AgentLogSerializer
)


class AgentRunViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for AgentRun."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = AgentRunSerializer
    
    def get_queryset(self):
        return AgentRun.objects.filter(
            strategy__user=self.request.user
        ).select_related('strategy').prefetch_related('decisions')


class AgentDecisionViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for AgentDecision."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = AgentDecisionSerializer
    
    def get_queryset(self):
        return AgentDecision.objects.filter(
            strategy__user=self.request.user
        ).select_related('strategy', 'agent_run')


class AgentLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for AgentLog."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = AgentLogSerializer
    
    def get_queryset(self):
        return AgentLog.objects.filter(
            agent_run__strategy__user=self.request.user
        ).select_related('agent_run', 'agent_decision')
