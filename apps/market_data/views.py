"""
Views for Agents, Market Data, Brokers, and Notifications.
"""
from decimal import Decimal
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Q, F

from apps.market_data.models import Quote, Indicator, StockScreener
from apps.market_data.serializers import (
    QuoteSerializer, IndicatorSerializer,
    StockScreenerSerializer, StockScreenerListSerializer
)


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


class StockScreenerViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Stock Screener with advanced filtering."""

    permission_classes = [IsAuthenticated]
    queryset = StockScreener.objects.all()

    def get_serializer_class(self):
        if self.action == 'list':
            return StockScreenerListSerializer
        return StockScreenerSerializer

    def get_queryset(self):
        """Apply filters to screener data."""
        queryset = super().get_queryset()

        # Symbol search
        symbol = self.request.query_params.get('symbol')
        if symbol:
            queryset = queryset.filter(symbol__icontains=symbol.upper())

        # Sector filter
        sector = self.request.query_params.get('sector')
        if sector:
            queryset = queryset.filter(sector__iexact=sector)

        # Industry filter
        industry = self.request.query_params.get('industry')
        if industry:
            queryset = queryset.filter(industry__iexact=industry)

        # Exchange filter
        exchange = self.request.query_params.get('exchange')
        if exchange:
            queryset = queryset.filter(exchange__iexact=exchange)

        # Price range
        price_min = self.request.query_params.get('price_min')
        if price_min:
            queryset = queryset.filter(price__gte=Decimal(price_min))

        price_max = self.request.query_params.get('price_max')
        if price_max:
            queryset = queryset.filter(price__lte=Decimal(price_max))

        # Market cap range
        market_cap_min = self.request.query_params.get('market_cap_min')
        if market_cap_min:
            queryset = queryset.filter(market_cap__gte=int(market_cap_min))

        market_cap_max = self.request.query_params.get('market_cap_max')
        if market_cap_max:
            queryset = queryset.filter(market_cap__lte=int(market_cap_max))

        # Volume range
        volume_min = self.request.query_params.get('volume_min')
        if volume_min:
            queryset = queryset.filter(volume__gte=int(volume_min))

        volume_max = self.request.query_params.get('volume_max')
        if volume_max:
            queryset = queryset.filter(volume__lte=int(volume_max))

        # RSI range
        rsi_min = self.request.query_params.get('rsi_min')
        if rsi_min:
            queryset = queryset.filter(rsi__gte=Decimal(rsi_min))

        rsi_max = self.request.query_params.get('rsi_max')
        if rsi_max:
            queryset = queryset.filter(rsi__lte=Decimal(rsi_max))

        # P/E Ratio range
        pe_min = self.request.query_params.get('pe_min')
        if pe_min:
            queryset = queryset.filter(pe_ratio__gte=Decimal(pe_min))

        pe_max = self.request.query_params.get('pe_max')
        if pe_max:
            queryset = queryset.filter(pe_ratio__lte=Decimal(pe_max))

        # Change percentage range
        change_min = self.request.query_params.get('change_min')
        if change_min:
            queryset = queryset.filter(change_pct__gte=Decimal(change_min))

        change_max = self.request.query_params.get('change_max')
        if change_max:
            queryset = queryset.filter(change_pct__lte=Decimal(change_max))

        # Dividend yield range
        dividend_min = self.request.query_params.get('dividend_min')
        if dividend_min:
            queryset = queryset.filter(dividend_yield__gte=Decimal(dividend_min))

        # Technical filters
        above_sma_50 = self.request.query_params.get('above_sma_50')
        if above_sma_50 and above_sma_50.lower() == 'true':
            queryset = queryset.filter(price__gt=F('sma_50'))

        above_sma_200 = self.request.query_params.get('above_sma_200')
        if above_sma_200 and above_sma_200.lower() == 'true':
            queryset = queryset.filter(price__gt=F('sma_200'))

        # Ordering
        order_by = self.request.query_params.get('order_by', '-volume')
        valid_order_fields = [
            'symbol', 'price', 'change_pct', 'volume', 'market_cap',
            'pe_ratio', 'rsi', '-symbol', '-price', '-change_pct',
            '-volume', '-market_cap', '-pe_ratio', '-rsi'
        ]
        if order_by in valid_order_fields:
            queryset = queryset.order_by(order_by)

        return queryset

    @action(detail=False, methods=['get'])
    def sectors(self, request):
        """Get list of available sectors."""
        sectors = StockScreener.objects.values_list('sector', flat=True).distinct().order_by('sector')
        sectors = [s for s in sectors if s]  # Filter out empty strings

        return Response({
            'count': len(sectors),
            'sectors': sectors
        })

    @action(detail=False, methods=['get'])
    def industries(self, request):
        """Get list of available industries."""
        industries = StockScreener.objects.values_list('industry', flat=True).distinct().order_by('industry')
        industries = [i for i in industries if i]  # Filter out empty strings

        return Response({
            'count': len(industries),
            'industries': industries
        })

    @action(detail=False, methods=['get'])
    def top_gainers(self, request):
        """Get top gaining stocks."""
        limit = int(request.query_params.get('limit', 20))
        stocks = self.queryset.filter(change_pct__isnull=False).order_by('-change_pct')[:limit]
        serializer = self.get_serializer(stocks, many=True)

        return Response({
            'count': len(stocks),
            'stocks': serializer.data
        })

    @action(detail=False, methods=['get'])
    def top_losers(self, request):
        """Get top losing stocks."""
        limit = int(request.query_params.get('limit', 20))
        stocks = self.queryset.filter(change_pct__isnull=False).order_by('change_pct')[:limit]
        serializer = self.get_serializer(stocks, many=True)

        return Response({
            'count': len(stocks),
            'stocks': serializer.data
        })

    @action(detail=False, methods=['get'])
    def most_active(self, request):
        """Get most active stocks by volume."""
        limit = int(request.query_params.get('limit', 20))
        stocks = self.queryset.filter(volume__isnull=False).order_by('-volume')[:limit]
        serializer = self.get_serializer(stocks, many=True)

        return Response({
            'count': len(stocks),
            'stocks': serializer.data
        })
