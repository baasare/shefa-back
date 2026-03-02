"""
Celery tasks for autonomous agent execution.
These tasks enable background processing of trading decisions.
"""
from celery import shared_task
from decimal import Decimal
import asyncio
from typing import List, Dict, Any

from apps.agents.orchestrator import AgentOrchestrator
from apps.portfolios.models import Portfolio
from apps.strategies.models import Strategy
from apps.orders.models import Order
from apps.orders.execution import OrderExecutor
from apps.notifications.tasks import send_strategy_signal_notification, send_approval_request


@shared_task(bind=True, max_retries=3)
def run_agent_analysis(self, portfolio_id: str, symbol: str):
    """
    Run AI agent analysis on a stock.

    Args:
        portfolio_id: Portfolio UUID
        symbol: Stock ticker symbol

    Returns:
        Dictionary with analysis results
    """
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)

        # Create orchestrator
        orchestrator = AgentOrchestrator(portfolio=portfolio)

        # Run analysis synchronously
        result = orchestrator.run_sync(symbol)

        return {
            "success": True,
            "portfolio_id": portfolio_id,
            "symbol": symbol,
            "analysis": {
                "symbol": result["symbol"],
                "timestamp": result["timestamp"],
                "final_recommendation": result["final_recommendation"]["messages"][-1].content
            }
        }

    except Portfolio.DoesNotExist:
        return {
            "success": False,
            "error": f"Portfolio {portfolio_id} not found"
        }
    except Exception as e:
        # Retry on failure
        self.retry(exc=e, countdown=60)  # Retry after 1 minute


@shared_task(bind=True, max_retries=3)
def run_watchlist_monitoring(self, strategy_id: str):
    """
    Monitor watchlist for a strategy and generate trading signals.

    Args:
        strategy_id: Strategy UUID

    Returns:
        List of trading signals generated
    """
    try:
        strategy = Strategy.objects.get(id=strategy_id)

        if not strategy.is_active:
            return {
                "success": False,
                "error": "Strategy is not active"
            }

        if not strategy.portfolio:
            return {
                "success": False,
                "error": "Strategy has no associated portfolio"
            }

        # Create orchestrator
        orchestrator = AgentOrchestrator(
            portfolio=strategy.portfolio,
            strategy=strategy
        )

        # Monitor watchlist
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            recommendations = loop.run_until_complete(
                orchestrator.monitor_watchlist(strategy.watchlist)
            )
        finally:
            loop.close()

        # Process recommendations
        signals = []

        for rec in recommendations:
            if rec.get("success", True):  # Skip error entries
                try:
                    # Extract recommendation from final result
                    final_content = rec["final_recommendation"]["messages"][-1].content

                    # Send notification about the signal
                    send_strategy_signal_notification.delay(
                        strategy.user.id,
                        {
                            'symbol': rec["symbol"],
                            'strategy_name': strategy.name,
                            'recommendation': final_content[:200]  # First 200 chars
                        }
                    )

                    signals.append({
                        "symbol": rec["symbol"],
                        "recommendation": final_content[:200],
                        "status": "notified"
                    })

                except Exception as e:
                    signals.append({
                        "symbol": rec.get("symbol", "unknown"),
                        "error": str(e)
                    })

        return {
            "success": True,
            "strategy_id": strategy_id,
            "signals_generated": len(signals),
            "signals": signals
        }

    except Strategy.DoesNotExist:
        return {
            "success": False,
            "error": f"Strategy {strategy_id} not found"
        }
    except Exception as e:
        # Retry on failure
        self.retry(exc=e, countdown=300)  # Retry after 5 minutes


@shared_task(bind=True, max_retries=3)
def execute_autonomous_trade(self, strategy_id: str, symbol: str):
    """
    Execute autonomous trade based on agent recommendation.
    This task includes HITL (Human-in-the-Loop) if required.

    Args:
        strategy_id: Strategy UUID
        symbol: Stock ticker symbol

    Returns:
        Dictionary with execution results
    """
    try:
        strategy = Strategy.objects.get(id=strategy_id)

        if not strategy.is_active:
            return {
                "success": False,
                "error": "Strategy is not active"
            }

        if not strategy.portfolio:
            return {
                "success": False,
                "error": "Strategy has no associated portfolio"
            }

        # Create orchestrator
        orchestrator = AgentOrchestrator(
            portfolio=strategy.portfolio,
            strategy=strategy
        )

        # Get trading recommendation
        result = orchestrator.run_sync(symbol)

        # Extract recommendation details
        final_content = result["final_recommendation"]["messages"][-1].content

        # Parse recommendation (simplified - would need better parsing in production)
        # For now, we'll look for key indicators in the text
        content_lower = final_content.lower()

        if "buy" in content_lower and "strong buy" in content_lower:
            action = "buy"
        elif "buy" in content_lower:
            action = "buy"
        elif "sell" in content_lower and "strong sell" in content_lower:
            action = "sell"
        elif "sell" in content_lower:
            action = "sell"
        else:
            action = "hold"

        if action == "hold":
            return {
                "success": True,
                "action": "hold",
                "symbol": symbol,
                "reason": "Agent recommended HOLD - no action taken"
            }

        # Get current price
        from apps.market_data.providers.massive import MassiveProvider
        provider = MassiveProvider()
        quote = provider.get_quote(symbol)
        current_price = Decimal(str(quote.get('price', 0)))

        # Calculate position size (using strategy config or default)
        from apps.orders.services import calculate_position_size

        config = strategy.config or {}
        position_sizing = config.get('position_sizing', {})
        sizing_type = position_sizing.get('type', 'percentage')
        size_value = Decimal(str(position_sizing.get('value', 10)))

        quantity = calculate_position_size(
            strategy.portfolio,
            current_price,
            sizing_type=sizing_type,
            size_value=size_value
        )

        # Create order
        order = Order.objects.create(
            portfolio=strategy.portfolio,
            symbol=symbol,
            quantity=quantity,
            side=action,
            order_type='market',
            estimated_price=current_price,
            status='pending',
            notes=f"Autonomous agent order - {final_content[:500]}"
        )

        # Check if approval required
        from apps.orders.services import requires_approval

        if requires_approval(order, strategy.user):
            order.approval_required = True
            order.status = 'pending_approval'
            order.save()

            # Send approval request
            send_approval_request.delay(order.id)

            return {
                "success": True,
                "action": action,
                "symbol": symbol,
                "order_id": str(order.id),
                "quantity": quantity,
                "status": "pending_approval",
                "approval_required": True
            }

        # Execute order
        executor = OrderExecutor()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            execution_result = loop.run_until_complete(executor.execute_order(order.id))
        finally:
            loop.close()

        return {
            "success": execution_result.get("success", False),
            "action": action,
            "symbol": symbol,
            "order_id": str(order.id),
            "quantity": quantity,
            "execution_result": execution_result
        }

    except Strategy.DoesNotExist:
        return {
            "success": False,
            "error": f"Strategy {strategy_id} not found"
        }
    except Exception as e:
        # Retry on failure
        self.retry(exc=e, countdown=300)  # Retry after 5 minutes


@shared_task
def run_periodic_agent_scan():
    """
    Periodic task to run agent analysis on all active strategies.
    Should be scheduled to run every 15-30 minutes during market hours.

    Returns:
        Summary of scans performed
    """
    try:
        # Get all active strategies
        active_strategies = Strategy.objects.filter(is_active=True)

        results = []

        for strategy in active_strategies:
            # Skip if no portfolio or watchlist
            if not strategy.portfolio or not strategy.watchlist:
                continue

            # Queue watchlist monitoring
            task = run_watchlist_monitoring.delay(str(strategy.id))

            results.append({
                "strategy_id": str(strategy.id),
                "strategy_name": strategy.name,
                "task_id": task.id,
                "watchlist_size": len(strategy.watchlist)
            })

        return {
            "success": True,
            "strategies_scanned": len(results),
            "details": results
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@shared_task(bind=True, max_retries=3)
def run_multi_agent_consensus(self, portfolio_id: str, symbols: List[str]):
    """
    Run multi-agent consensus analysis on multiple stocks.
    Aggregates signals from all symbols to find best opportunities.

    Args:
        portfolio_id: Portfolio UUID
        symbols: List of stock ticker symbols

    Returns:
        Ranked list of trading opportunities
    """
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)

        # Create orchestrator
        orchestrator = AgentOrchestrator(portfolio=portfolio)

        # Monitor watchlist
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            recommendations = loop.run_until_complete(
                orchestrator.monitor_watchlist(symbols)
            )
        finally:
            loop.close()

        # Rank opportunities
        opportunities = []

        for rec in recommendations:
            if rec.get("success", True):
                try:
                    final_content = rec["final_recommendation"]["messages"][-1].content
                    content_lower = final_content.lower()

                    # Simple scoring (would be more sophisticated in production)
                    score = 0
                    if "strong buy" in content_lower:
                        score = 10
                    elif "buy" in content_lower:
                        score = 7
                    elif "hold" in content_lower:
                        score = 5
                    elif "sell" in content_lower:
                        score = 3

                    if "high" in content_lower and "confidence" in content_lower:
                        score += 2

                    opportunities.append({
                        "symbol": rec["symbol"],
                        "score": score,
                        "recommendation": final_content[:200]
                    })

                except Exception as e:
                    pass

        # Sort by score
        opportunities.sort(key=lambda x: x['score'], reverse=True)

        return {
            "success": True,
            "portfolio_id": portfolio_id,
            "opportunities_analyzed": len(symbols),
            "top_opportunities": opportunities[:5]  # Top 5
        }

    except Portfolio.DoesNotExist:
        return {
            "success": False,
            "error": f"Portfolio {portfolio_id} not found"
        }
    except Exception as e:
        # Retry on failure
        self.retry(exc=e, countdown=300)
