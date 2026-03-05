"""
Strategy views for ShefaFx Trading Platform.
"""
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from apps.strategies.models import Strategy, Backtest, StrategyTemplate, Watchlist
from rest_framework.permissions import IsAuthenticated
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from apps.strategies.serializers import (
    StrategySerializer, StrategyListSerializer, BacktestSerializer,
    StrategyTemplateSerializer, StrategyTemplateListSerializer,
    CreateStrategyFromTemplateSerializer, WatchlistSerializer, WatchlistListSerializer
)
from apps.strategies.pagination import StandardResultsSetPagination


class StrategyViewSet(viewsets.ModelViewSet):
    """ViewSet for Strategy CRUD operations."""
    
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'strategy_type']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at', 'win_rate', 'total_pnl', 'total_trades']
    ordering = ['-created_at']
    
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


class StrategyTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Strategy Templates (read-only for users)."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'difficulty', 'is_featured']
    search_fields = ['name', 'description', 'tags']
    ordering_fields = ['name', 'created_at', 'usage_count', 'expected_win_rate']
    ordering = ['-usage_count']

    def get_serializer_class(self):
        if self.action == 'list':
            return StrategyTemplateListSerializer
        return StrategyTemplateSerializer

    def get_queryset(self):
        """Return active templates."""
        queryset = StrategyTemplate.objects.filter(is_active=True)

        # Filter by category
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category=category)

        # Filter by difficulty
        difficulty = self.request.query_params.get('difficulty', None)
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)

        # Filter by tags
        tags = self.request.query_params.get('tags', None)
        if tags:
            tag_list = tags.split(',')
            for tag in tag_list:
                queryset = queryset.filter(tags__contains=[tag.strip()])

        # Featured only
        featured = self.request.query_params.get('featured', None)
        if featured and featured.lower() == 'true':
            queryset = queryset.filter(is_featured=True)

        return queryset

    @action(detail=True, methods=['post'])
    def create_strategy(self, request, pk=None):
        """Create a strategy from this template."""
        template = self.get_object()

        serializer = CreateStrategyFromTemplateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        # Create strategy from template
        strategy = Strategy.objects.create(
            user=request.user,
            portfolio_id=data.get('portfolio'),
            name=data['name'],
            description=template.description,
            strategy_type=template.strategy_type,
            config=template.config.copy(),
            entry_rules=template.entry_rules.copy(),
            exit_rules=template.exit_rules.copy(),
            watchlist=data.get('watchlist', []),
            position_size_pct=data.get('position_size_pct', template.default_position_size_pct),
            max_positions=data.get('max_positions', template.default_max_positions),
            max_daily_loss_pct=data.get('max_daily_loss_pct', template.default_max_daily_loss_pct),
            status='inactive'
        )

        # Increment template usage count
        template.usage_count += 1
        template.save(update_fields=['usage_count'])

        strategy_serializer = StrategySerializer(strategy)
        return Response({
            'message': 'Strategy created successfully from template',
            'strategy': strategy_serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured templates."""
        templates = self.get_queryset().filter(is_featured=True)
        serializer = self.get_serializer(templates, many=True)

        return Response({
            'count': templates.count(),
            'templates': serializer.data
        })


class WatchlistViewSet(viewsets.ModelViewSet):
    """ViewSet for Watchlist CRUD operations."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return WatchlistListSerializer
        return WatchlistSerializer

    def get_queryset(self):
        """Return watchlists for authenticated user."""
        return Watchlist.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def add_symbol(self, request, pk=None):
        """Add a symbol to the watchlist."""
        watchlist = self.get_object()
        symbol = request.data.get('symbol', '').upper().strip()

        if not symbol:
            return Response(
                {'error': 'Symbol is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if symbol in watchlist.symbols:
            return Response(
                {'error': 'Symbol already in watchlist'},
                status=status.HTTP_400_BAD_REQUEST
            )

        watchlist.symbols.append(symbol)
        watchlist.save()

        serializer = self.get_serializer(watchlist)
        return Response({
            'message': f'Symbol {symbol} added successfully',
            'watchlist': serializer.data
        })

    @action(detail=True, methods=['post'])
    def remove_symbol(self, request, pk=None):
        """Remove a symbol from the watchlist."""
        watchlist = self.get_object()
        symbol = request.data.get('symbol', '').upper().strip()

        if not symbol:
            return Response(
                {'error': 'Symbol is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if symbol not in watchlist.symbols:
            return Response(
                {'error': 'Symbol not in watchlist'},
                status=status.HTTP_400_BAD_REQUEST
            )

        watchlist.symbols.remove(symbol)
        watchlist.save()

        serializer = self.get_serializer(watchlist)
        return Response({
            'message': f'Symbol {symbol} removed successfully',
            'watchlist': serializer.data
        })

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set this watchlist as default."""
        watchlist = self.get_object()
        watchlist.is_default = True
        watchlist.save()

        serializer = self.get_serializer(watchlist)
        return Response({
            'message': 'Watchlist set as default',
            'watchlist': serializer.data
        })

    @action(detail=False, methods=['get'])
    def default(self, request):
        """Get the default watchlist."""
        watchlist = self.get_queryset().filter(is_default=True).first()

        if not watchlist:
            return Response(
                {'error': 'No default watchlist found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(watchlist)
        return Response(serializer.data)
