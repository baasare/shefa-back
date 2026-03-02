"""
Strategy views for ShefaAI Trading Platform.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Strategy, Backtest
from .serializers import (
    StrategySerializer, StrategyListSerializer,
    BacktestSerializer
)


class StrategyViewSet(viewsets.ModelViewSet):
    """ViewSet for Strategy CRUD operations."""
    
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return StrategyListSerializer
        return StrategySerializer
    
    def get_queryset(self):
        """Return strategies for authenticated user."""
        return Strategy.objects.filter(user=self.request.user).prefetch_related('backtests')
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a strategy."""
        strategy = self.get_object()
        strategy.status = 'active'
        strategy.activated_at = timezone.now()
        strategy.save()
        
        serializer = self.get_serializer(strategy)
        return Response({
            'message': 'Strategy activated successfully',
            'strategy': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause a strategy."""
        strategy = self.get_object()
        strategy.status = 'paused'
        strategy.save()
        
        serializer = self.get_serializer(strategy)
        return Response({
            'message': 'Strategy paused successfully',
            'strategy': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a strategy."""
        strategy = self.get_object()
        strategy.status = 'inactive'
        strategy.save()
        
        serializer = self.get_serializer(strategy)
        return Response({
            'message': 'Strategy deactivated successfully',
            'strategy': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def run_backtest(self, request, pk=None):
        """Start a new backtest for the strategy."""
        strategy = self.get_object()
        
        # Create backtest
        backtest = Backtest.objects.create(
            strategy=strategy,
            start_date=request.data.get('start_date'),
            end_date=request.data.get('end_date'),
            initial_capital=request.data.get('initial_capital'),
            status='pending'
        )
        
        # TODO: Queue backtest task with Celery
        
        serializer = BacktestSerializer(backtest)
        return Response({
            'message': 'Backtest queued successfully',
            'backtest': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get all active strategies."""
        strategies = self.get_queryset().filter(status='active')
        serializer = self.get_serializer(strategies, many=True)
        
        return Response({
            'count': strategies.count(),
            'strategies': serializer.data
        })


class BacktestViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for Backtest results."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = BacktestSerializer
    
    def get_queryset(self):
        """Return backtests for authenticated user's strategies."""
        return Backtest.objects.filter(
            strategy__user=self.request.user
        ).select_related('strategy')
    
    @action(detail=True, methods=['get'])
    def equity_curve(self, request, pk=None):
        """Get equity curve data for backtest."""
        backtest = self.get_object()
        
        if not backtest.equity_curve:
            return Response(
                {'error': 'Equity curve data not available'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response({
            'backtest_id': str(backtest.id),
            'equity_curve': backtest.equity_curve
        })
