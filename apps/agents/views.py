"""
Views for Agents

Provides API endpoints for:
1. Agent run history (AgentRun, AgentDecision, AgentLog models)
2. Triggering agent analysis and autonomous trading
3. Managing strategy autonomous trading settings
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
import logging

from apps.agents.models import AgentRun, AgentDecision, AgentLog
from apps.agents.serializers import (
    AgentRunSerializer, AgentDecisionSerializer, AgentLogSerializer
)
from apps.portfolios.models import Portfolio
from apps.strategies.models import Strategy
from apps.agents.tasks import (
    run_agent_analysis,
    run_watchlist_monitoring,
    execute_autonomous_trade,
    run_multi_agent_consensus
)

logger = logging.getLogger(__name__)


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


class AgentAnalysisViewSet(viewsets.ViewSet):
    """
    ViewSet for triggering AI agent analysis and trading.

    Provides endpoints to:
    - Analyze individual stocks
    - Monitor strategy watchlists
    - Execute autonomous trades
    - Run multi-agent consensus
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='analyze-stock')
    def analyze_stock(self, request):
        """
        Run AI agent analysis on a specific stock.

        POST /api/agent-analysis/analyze-stock/

        Request body:
        {
            "portfolio_id": "uuid",
            "symbol": "AAPL"
        }

        Returns:
        {
            "success": true,
            "task_id": "celery-task-id",
            "message": "Analysis started for AAPL"
        }
        """
        portfolio_id = request.data.get('portfolio_id')
        symbol = request.data.get('symbol')

        if not portfolio_id or not symbol:
            return Response(
                {'error': 'portfolio_id and symbol are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify portfolio belongs to user
        portfolio = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)

        # Queue analysis task
        task = run_agent_analysis.delay(str(portfolio.id), symbol)

        logger.info(f"Started agent analysis for {symbol} in portfolio {portfolio.id}")

        return Response({
            'success': True,
            'task_id': task.id,
            'portfolio_id': str(portfolio.id),
            'symbol': symbol,
            'message': f'Analysis started for {symbol}'
        })

    @action(detail=False, methods=['post'], url_path='monitor-watchlist')
    def monitor_watchlist(self, request):
        """
        Monitor strategy watchlist and generate trading signals.

        POST /api/agent-analysis/monitor-watchlist/

        Request body:
        {
            "strategy_id": "uuid"
        }

        Returns:
        {
            "success": true,
            "task_id": "celery-task-id",
            "message": "Watchlist monitoring started"
        }
        """
        strategy_id = request.data.get('strategy_id')

        if not strategy_id:
            return Response(
                {'error': 'strategy_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify strategy belongs to user
        strategy = get_object_or_404(Strategy, id=strategy_id, user=request.user)

        if not strategy.is_active:
            return Response(
                {'error': 'Strategy is not active'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not strategy.watchlist:
            return Response(
                {'error': 'Strategy has no watchlist'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Queue monitoring task
        task = run_watchlist_monitoring.delay(str(strategy.id))

        logger.info(f"Started watchlist monitoring for strategy {strategy.id}")

        return Response({
            'success': True,
            'task_id': task.id,
            'strategy_id': str(strategy.id),
            'watchlist_size': len(strategy.watchlist),
            'message': 'Watchlist monitoring started'
        })

    @action(detail=False, methods=['post'], url_path='execute-trade')
    def execute_trade(self, request):
        """
        Execute autonomous trade based on agent recommendation.

        POST /api/agent-analysis/execute-trade/

        Request body:
        {
            "strategy_id": "uuid",
            "symbol": "AAPL"
        }

        Returns:
        {
            "success": true,
            "task_id": "celery-task-id",
            "message": "Trade execution started for AAPL"
        }
        """
        strategy_id = request.data.get('strategy_id')
        symbol = request.data.get('symbol')

        if not strategy_id or not symbol:
            return Response(
                {'error': 'strategy_id and symbol are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify strategy belongs to user
        strategy = get_object_or_404(Strategy, id=strategy_id, user=request.user)

        if not strategy.is_active:
            return Response(
                {'error': 'Strategy is not active'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Queue trade execution task
        task = execute_autonomous_trade.delay(str(strategy.id), symbol)

        logger.info(f"Started autonomous trade execution for {symbol} in strategy {strategy.id}")

        return Response({
            'success': True,
            'task_id': task.id,
            'strategy_id': str(strategy.id),
            'symbol': symbol,
            'message': f'Trade execution started for {symbol}'
        })

    @action(detail=False, methods=['post'], url_path='multi-agent-consensus')
    def multi_agent_consensus(self, request):
        """
        Run multi-agent consensus analysis on multiple stocks.

        POST /api/agent-analysis/multi-agent-consensus/

        Request body:
        {
            "portfolio_id": "uuid",
            "symbols": ["AAPL", "GOOGL", "MSFT"]
        }

        Returns:
        {
            "success": true,
            "task_id": "celery-task-id",
            "message": "Multi-agent consensus analysis started"
        }
        """
        portfolio_id = request.data.get('portfolio_id')
        symbols = request.data.get('symbols', [])

        if not portfolio_id or not symbols:
            return Response(
                {'error': 'portfolio_id and symbols are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not isinstance(symbols, list):
            return Response(
                {'error': 'symbols must be a list'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify portfolio belongs to user
        portfolio = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)

        # Queue consensus task
        task = run_multi_agent_consensus.delay(str(portfolio.id), symbols)

        logger.info(f"Started multi-agent consensus for {len(symbols)} symbols in portfolio {portfolio.id}")

        return Response({
            'success': True,
            'task_id': task.id,
            'portfolio_id': str(portfolio.id),
            'symbols_count': len(symbols),
            'message': f'Multi-agent consensus analysis started for {len(symbols)} stocks'
        })

    @action(detail=False, methods=['get'], url_path='task-status/(?P<task_id>[^/.]+)')
    def task_status(self, request, task_id=None):
        """
        Get status of an agent task.

        GET /api/agent-analysis/task-status/{task_id}/

        Returns:
        {
            "task_id": "celery-task-id",
            "state": "PENDING|STARTED|SUCCESS|FAILURE",
            "result": {...},
            "error": "error message if failed"
        }
        """
        from celery.result import AsyncResult

        if not task_id:
            return Response(
                {'error': 'task_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        task_result = AsyncResult(task_id)

        response_data = {
            'task_id': task_id,
            'state': task_result.state,
        }

        if task_result.state == 'SUCCESS':
            response_data['result'] = task_result.result
        elif task_result.state == 'FAILURE':
            response_data['error'] = str(task_result.info)

        return Response(response_data)


class StrategyAgentViewSet(viewsets.ViewSet):
    """
    ViewSet for strategy-specific agent operations.

    Provides endpoints for managing autonomous trading on strategies.
    """
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'], url_path='enable-autonomous')
    def enable_autonomous(self, request, pk=None):
        """
        Enable autonomous trading for a strategy.

        POST /api/strategy-agents/{strategy_id}/enable-autonomous/

        Returns:
        {
            "success": true,
            "strategy_id": "uuid",
            "message": "Autonomous trading enabled"
        }
        """
        strategy = get_object_or_404(Strategy, id=pk, user=request.user)

        # Update strategy config to enable autonomous trading
        config = strategy.config or {}
        config['autonomous_trading'] = True
        strategy.config = config
        strategy.save()

        logger.info(f"Enabled autonomous trading for strategy {strategy.id}")

        return Response({
            'success': True,
            'strategy_id': str(strategy.id),
            'message': 'Autonomous trading enabled'
        })

    @action(detail=True, methods=['post'], url_path='disable-autonomous')
    def disable_autonomous(self, request, pk=None):
        """
        Disable autonomous trading for a strategy.

        POST /api/strategy-agents/{strategy_id}/disable-autonomous/

        Returns:
        {
            "success": true,
            "strategy_id": "uuid",
            "message": "Autonomous trading disabled"
        }
        """
        strategy = get_object_or_404(Strategy, id=pk, user=request.user)

        # Update strategy config to disable autonomous trading
        config = strategy.config or {}
        config['autonomous_trading'] = False
        strategy.config = config
        strategy.save()

        logger.info(f"Disabled autonomous trading for strategy {strategy.id}")

        return Response({
            'success': True,
            'strategy_id': str(strategy.id),
            'message': 'Autonomous trading disabled'
        })

    @action(detail=True, methods=['get'], url_path='status')
    def status(self, request, pk=None):
        """
        Get autonomous trading status for a strategy.

        GET /api/strategy-agents/{strategy_id}/status/

        Returns:
        {
            "strategy_id": "uuid",
            "autonomous_enabled": true,
            "is_active": true,
            "watchlist_size": 10,
            "recent_signals": [...]
        }
        """
        strategy = get_object_or_404(Strategy, id=pk, user=request.user)

        config = strategy.config or {}
        autonomous_enabled = config.get('autonomous_trading', False)

        # Get recent orders for this strategy (as a proxy for signals)
        from apps.orders.models import Order
        recent_orders = Order.objects.filter(
            portfolio=strategy.portfolio
        ).order_by('-created_at')[:5]

        recent_signals = [
            {
                'id': str(order.id),
                'symbol': order.symbol,
                'side': order.side,
                'status': order.status,
                'created_at': order.created_at.isoformat()
            }
            for order in recent_orders
        ] if strategy.portfolio else []

        return Response({
            'strategy_id': str(strategy.id),
            'strategy_name': strategy.name,
            'autonomous_enabled': autonomous_enabled,
            'is_active': strategy.status == 'active',
            'watchlist_size': len(strategy.watchlist) if strategy.watchlist else 0,
            'recent_signals': recent_signals
        })
