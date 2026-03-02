"""
Views for Agents, Market Data, Brokers, and Notifications.
"""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.brokers.models import BrokerConnection
from apps.brokers.serializers import BrokerConnectionSerializer


class BrokerConnectionViewSet(viewsets.ModelViewSet):
    """ViewSet for BrokerConnection CRUD operations."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = BrokerConnectionSerializer
    
    def get_queryset(self):
        return BrokerConnection.objects.filter(
            user=self.request.user
        ).select_related('portfolio')
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test broker connection."""
        connection = self.get_object()
        
        # TODO: Implement actual connection test
        # For now, just return mock response
        
        return Response({
            'message': 'Connection test successful',
            'broker': connection.broker,
            'account_number': connection.account_number
        })
