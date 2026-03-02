"""
Views for Agents, Market Data, Brokers, and Notifications.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.brokers.models import BrokerConnection
from apps.brokers.serializers import BrokerConnectionSerializer
from apps.brokers.services import verify_broker_connection


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
        """
        Test broker connection by verifying credentials.

        Attempts to fetch account info from the broker to verify
        that the stored credentials are valid and working.
        """
        connection = self.get_object()

        # Verify connection with actual broker API
        result = verify_broker_connection(connection)

        if result['success']:
            # Update connection status to active on successful test
            connection.status = 'active'
            connection.last_error = ''
            connection.save()

            return Response({
                'success': True,
                'message': result['message'],
                'broker': connection.broker,
                'account_number': connection.account_number,
                'account_info': {
                    'portfolio_value': result['account_info'].get('portfolio_value'),
                    'cash': result['account_info'].get('cash'),
                    'buying_power': result['account_info'].get('buying_power'),
                }
            }, status=status.HTTP_200_OK)
        else:
            # Update connection status to error on failed test
            connection.status = 'error'
            connection.last_error = result['message']
            connection.save()

            return Response({
                'success': False,
                'message': result['message'],
                'broker': connection.broker,
            }, status=status.HTTP_400_BAD_REQUEST)
