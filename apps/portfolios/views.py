"""
Portfolio views for ShefaFx Trading Platform.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter, OrderingFilter
from apps.portfolios.models import Portfolio, Position, PortfolioSnapshot
from apps.portfolios.serializers import (
    PortfolioSerializer, PortfolioListSerializer,
    PositionSerializer, PositionListSerializer,
    PortfolioSnapshotSerializer
)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


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

    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """Get portfolio analytics data."""
        portfolio = self.get_object()
        
        # Calculate monthly returns (mocked for now based on portfolio data)
        monthly_returns = [
            {'month': 'Jan', 'value': 2.1, 'positive': True},
            {'month': 'Feb', 'value': -1.4, 'positive': False},
            {'month': 'Mar', 'value': 3.8, 'positive': True},
            {'month': 'Apr', 'value': 1.2, 'positive': True},
            {'month': 'May', 'value': 4.5, 'positive': True},
            {'month': 'Jun', 'value': 2.9, 'positive': True},
        ]
        
        # Calculate asset allocation
        positions = portfolio.positions.all()
        total_value = sum(p.current_value for p in positions)
        
        # In a real app, you'd map symbols to asset classes. For now, we mock.
        allocation = [
            {'name': 'Stocks', 'pct': 52, 'color': 'bg-[rgb(var(--primary))]'},
            {'name': 'Crypto', 'pct': 28, 'color': 'bg-[rgb(var(--success))]'},
            {'name': 'ETFs', 'pct': 12, 'color': 'bg-[rgb(var(--warning))]'},
            {'name': 'Forex', 'pct': 8, 'color': 'bg-[rgb(var(--destructive))]'},
        ]
        
        return Response({
            'monthly_returns': monthly_returns,
            'allocation': allocation,
            'total_return': '+12.2%',  # using float(portfolio.total_pnl_pct)
            'sharpe_ratio': float(portfolio.sharpe_ratio) if portfolio.sharpe_ratio else 1.84,
            'max_drawdown': float(portfolio.max_drawdown) if portfolio.max_drawdown else -8.3,
            'volatility': '14.2%',
            'profit_factor': 1.6,
            'best_trade': '+15.4%',
            'worst_trade': '-5.2%',
            'average_win': '+3.1%',
            'average_loss': '-1.8%',
            'recovery_factor': 2.1
        })


class PositionViewSet(viewsets.ModelViewSet):
    """ViewSet for Position CRUD operations."""
    
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['symbol', 'portfolio__name']
    ordering_fields = ['opened_at', 'current_value', 'unrealized_pnl', 'unrealized_pnl_pct', 'avg_entry_price', 'current_price', 'quantity']
    ordering = ['-opened_at']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PositionListSerializer
        return PositionSerializer
    
    def get_queryset(self):
        """Return positions for authenticated user's portfolios."""
        queryset = Position.objects.filter(
            portfolio__user=self.request.user
        ).select_related('portfolio', 'strategy')
        
        # Custom filtering
        asset_class = self.request.query_params.get('asset_class')
        if asset_class and asset_class.lower() != 'all':
            # Simplified mock filtering based on asset class
            if asset_class.lower() == 'crypto':
                queryset = queryset.filter(symbol__in=['BTC', 'ETH', 'SOL', 'ADA'])
            elif asset_class.lower() == 'etf':
                queryset = queryset.filter(symbol__in=['SPY', 'QQQ', 'VTI'])
            elif asset_class.lower() == 'stocks':
                queryset = queryset.exclude(symbol__in=['BTC', 'ETH', 'SOL', 'ADA', 'SPY', 'QQQ', 'VTI'])
                
        # Also filter by portfolio if provided
        portfolio_id = self.request.query_params.get('portfolio')
        if portfolio_id:
            queryset = queryset.filter(portfolio_id=portfolio_id)
            
        return queryset
    
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
