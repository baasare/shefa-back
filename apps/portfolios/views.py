"""
Portfolio views for ShefaAI Trading Platform.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.portfolios.models import Portfolio, Position, PortfolioSnapshot
from apps.portfolios.serializers import (
    PortfolioSerializer, PortfolioListSerializer,
    PositionSerializer, PositionListSerializer,
    PortfolioSnapshotSerializer
)


class PortfolioViewSet(viewsets.ModelViewSet):
    """ViewSet for Portfolio CRUD operations."""
    
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PortfolioListSerializer
        return PortfolioSerializer
    
    def get_queryset(self):
        """Return portfolios for authenticated user."""
        return Portfolio.objects.filter(user=self.request.user).prefetch_related('positions')
    
    @action(detail=True, methods=['post'])
    def calculate_equity(self, request, pk=None):
        """Calculate and update portfolio equity."""
        portfolio = self.get_object()
        equity = portfolio.calculate_equity()
        portfolio.calculate_pnl()
        
        serializer = self.get_serializer(portfolio)
        return Response({
            'message': 'Portfolio equity calculated successfully',
            'total_equity': float(equity),
            'portfolio': serializer.data
        })
    
    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        """Get portfolio performance history."""
        portfolio = self.get_object()
        snapshots = portfolio.snapshots.all()[:30]  # Last 30 days
        
        serializer = PortfolioSnapshotSerializer(snapshots, many=True)
        return Response({
            'portfolio_id': str(portfolio.id),
            'portfolio_name': portfolio.name,
            'snapshots': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a portfolio."""
        portfolio = self.get_object()
        portfolio.is_active = True
        portfolio.save()
        
        serializer = self.get_serializer(portfolio)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a portfolio."""
        portfolio = self.get_object()
        portfolio.is_active = False
        portfolio.save()
        
        serializer = self.get_serializer(portfolio)
        return Response(serializer.data)


class PositionViewSet(viewsets.ModelViewSet):
    """ViewSet for Position CRUD operations."""
    
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PositionListSerializer
        return PositionSerializer
    
    def get_queryset(self):
        """Return positions for authenticated user's portfolios."""
        return Position.objects.filter(
            portfolio__user=self.request.user
        ).select_related('portfolio', 'strategy')
    
    @action(detail=True, methods=['post'])
    def update_price(self, request, pk=None):
        """Update position with current price."""
        position = self.get_object()
        current_price = request.data.get('current_price')
        
        if not current_price:
            return Response(
                {'error': 'current_price is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        position.update_current_value(float(current_price))
        serializer = self.get_serializer(position)
        
        return Response({
            'message': 'Position price updated successfully',
            'position': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def by_symbol(self, request):
        """Get all positions for a specific symbol."""
        symbol = request.query_params.get('symbol', '').upper()
        
        if not symbol:
            return Response(
                {'error': 'symbol parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        positions = self.get_queryset().filter(symbol=symbol)
        serializer = self.get_serializer(positions, many=True)
        
        return Response({
            'symbol': symbol,
            'positions': serializer.data
        })


class PortfolioSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for PortfolioSnapshot."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = PortfolioSnapshotSerializer
    
    def get_queryset(self):
        """Return snapshots for authenticated user's portfolios."""
        return PortfolioSnapshot.objects.filter(
            portfolio__user=self.request.user
        ).select_related('portfolio')
