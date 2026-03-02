"""
Views for Agents, Market Data, Brokers, and Notifications.
"""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.market_data.models import Quote, Indicator
from apps.market_data.serializers import QuoteSerializer, IndicatorSerializer


class QuoteViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for market quotes."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = QuoteSerializer
    queryset = Quote.objects.all()
    
    @action(detail=False, methods=['get'])
    def by_symbol(self, request):
        """Get quotes for a specific symbol."""
        symbol = request.query_params.get('symbol', '').upper()
        limit = int(request.query_params.get('limit', 100))
        
        if not symbol:
            return Response(
                {'error': 'symbol parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        quotes = self.queryset.filter(symbol=symbol).order_by('-timestamp')[:limit]
        serializer = self.get_serializer(quotes, many=True)
        
        return Response({
            'symbol': symbol,
            'count': quotes.count(),
            'quotes': serializer.data
        })


class IndicatorViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for technical indicators."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = IndicatorSerializer
    queryset = Indicator.objects.all()
    
    @action(detail=False, methods=['get'])
    def by_symbol(self, request):
        """Get indicators for a specific symbol."""
        symbol = request.query_params.get('symbol', '').upper()
        indicator_type = request.query_params.get('type')
        
        if not symbol:
            return Response(
                {'error': 'symbol parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        indicators = self.queryset.filter(symbol=symbol)
        
        if indicator_type:
            indicators = indicators.filter(indicator_type=indicator_type)
        
        indicators = indicators.order_by('-timestamp')[:100]
        serializer = self.get_serializer(indicators, many=True)
        
        return Response({
            'symbol': symbol,
            'indicator_type': indicator_type,
            'count': indicators.count(),
            'indicators': serializer.data
        })
