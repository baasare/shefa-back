"""
Strategy execution engine for manual and automated trading.

Handles strategy signal generation and order placement with risk management.
"""
from typing import Dict, Any, List, Optional
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
import logging
import asyncio

from .models import Strategy
from .services import StrategyEvaluator, update_strategy_performance
from apps.orders.execution import OrderExecutionEngine, OrderExecutionError
from apps.orders.models import Order
from apps.portfolios.models import Portfolio, Position
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


class StrategyExecutionError(Exception):
    """Raised when strategy execution fails."""
    pass


class StrategyExecutor:
    """
    Executes trading strategies by evaluating signals and placing orders.

    Supports both manual (user-triggered) and automated execution.
    """

    def __init__(self, strategy: Strategy, dry_run: bool = False):
        """
        Initialize executor with strategy.

        Args:
            strategy: Strategy instance to execute
            dry_run: If True, only generate signals without placing orders
        """
        self.strategy = strategy
        self.dry_run = dry_run
        self.evaluator = StrategyEvaluator(strategy)

        if not self.strategy.portfolio:
            raise StrategyExecutionError("Strategy must be associated with a portfolio")

        self.order_engine = OrderExecutionEngine(
            user=strategy.user,
            broker_connection=strategy.portfolio.user.brokerconnection_set.filter(is_active=True).first()
        )

        logger.info(f"Initialized StrategyExecutor for {strategy.name} (dry_run={dry_run})")

    async def execute_single_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Execute strategy for a single symbol.

        Args:
            symbol: Stock symbol to evaluate

        Returns:
            Dictionary with execution results:
            - symbol: str
            - signal: 'buy', 'sell', 'hold'
            - executed: bool
            - order_id: Optional[str]
            - reason: str
            - details: dict
        """
        try:
            # Evaluate strategy
            evaluation = await self.evaluator.evaluate_symbol(symbol)

            result = {
                'symbol': symbol,
                'signal': evaluation['signal'],
                'confidence': evaluation['confidence'],
                'reasons': evaluation['reasons'],
                'executed': False,
                'order_id': None,
                'error': None
            }

            # Check if should execute
            if not evaluation['should_execute']:
                result['reason'] = 'Risk limits or conditions not met'
                return result

            # Dry run - don't place orders
            if self.dry_run:
                result['reason'] = 'Dry run - signal generated but not executed'
                return result

            # Execute based on signal
            if evaluation['signal'] == 'buy':
                order = await self._execute_buy_signal(symbol, evaluation)
                result['executed'] = True
                result['order_id'] = str(order.id)
                result['reason'] = 'Buy order placed'

            elif evaluation['signal'] == 'sell':
                order = await self._execute_sell_signal(symbol, evaluation)
                result['executed'] = True
                result['order_id'] = str(order.id)
                result['reason'] = 'Sell order placed'

            else:
                result['reason'] = 'Hold - no action taken'

            return result

        except Exception as e:
            logger.error(f"Error executing strategy for {symbol}: {e}")
            return {
                'symbol': symbol,
                'signal': 'error',
                'executed': False,
                'error': str(e),
                'reason': f'Execution failed: {e}'
            }

    async def execute_watchlist(self) -> List[Dict[str, Any]]:
        """
        Execute strategy for all symbols in watchlist.

        Returns:
            List of execution results for each symbol
        """
        results = []

        logger.info(f"Executing strategy {self.strategy.name} on {len(self.strategy.watchlist)} symbols")

        for symbol in self.strategy.watchlist:
            result = await self.execute_single_symbol(symbol)
            results.append(result)

        # Send summary notification
        await self._send_execution_summary(results)

        return results

    async def _execute_buy_signal(self, symbol: str, evaluation: Dict[str, Any]) -> Order:
        """
        Execute buy signal by placing order.

        Args:
            symbol: Stock symbol
            evaluation: Strategy evaluation results

        Returns:
            Created Order instance
        """
        # Calculate position size
        quantity = self._calculate_position_size(
            symbol=symbol,
            current_price=Decimal(str(evaluation['current_price']))
        )

        if quantity <= 0:
            raise StrategyExecutionError("Position size calculation resulted in 0 shares")

        # Place order
        order = await self.order_engine.submit_order(
            portfolio=self.strategy.portfolio,
            symbol=symbol,
            quantity=quantity,
            side='buy',
            order_type='market',  # TODO: Support limit orders from strategy config
            strategy_id=str(self.strategy.id)
        )

        logger.info(f"Placed buy order for {quantity} shares of {symbol} (order {order.id})")

        # Send notification
        await self._send_order_notification(order, evaluation)

        return order

    async def _execute_sell_signal(self, symbol: str, evaluation: Dict[str, Any]) -> Order:
        """
        Execute sell signal by placing order.

        Args:
            symbol: Stock symbol
            evaluation: Strategy evaluation results

        Returns:
            Created Order instance
        """
        # Get current position
        position = Position.objects.filter(
            portfolio=self.strategy.portfolio,
            symbol=symbol,
            quantity__gt=0
        ).first()

        if not position:
            raise StrategyExecutionError(f"No position in {symbol} to sell")

        # Sell entire position (TODO: Support partial exits)
        quantity = position.quantity

        # Place order
        order = await self.order_engine.submit_order(
            portfolio=self.strategy.portfolio,
            symbol=symbol,
            quantity=quantity,
            side='sell',
            order_type='market',
            strategy_id=str(self.strategy.id)
        )

        logger.info(f"Placed sell order for {quantity} shares of {symbol} (order {order.id})")

        # Send notification
        await self._send_order_notification(order, evaluation)

        return order

    def _calculate_position_size(self, symbol: str, current_price: Decimal) -> int:
        """
        Calculate position size based on strategy risk parameters.

        Args:
            symbol: Stock symbol
            current_price: Current market price

        Returns:
            Number of shares to buy
        """
        # Get portfolio value
        portfolio = self.strategy.portfolio
        portfolio_value = portfolio.cash + sum(
            p.cost_basis for p in Position.objects.filter(portfolio=portfolio, quantity__gt=0)
        )

        # Calculate position size as % of portfolio
        position_value = portfolio_value * (self.strategy.position_size_pct / 100)

        # Calculate shares
        shares = int(position_value / current_price)

        # Ensure we have enough cash
        cost = shares * current_price
        if cost > portfolio.cash:
            shares = int(portfolio.cash / current_price)

        logger.debug(f"Position size for {symbol}: {shares} shares @ ${current_price} = ${shares * current_price}")

        return shares

    async def _send_order_notification(self, order: Order, evaluation: Dict[str, Any]):
        """Send notification about order placement."""
        Notification.objects.create(
            user=self.strategy.user,
            type='trade_signal',
            title=f"Strategy Signal: {order.side.upper()} {order.symbol}",
            message=f"Strategy '{self.strategy.name}' generated {order.side} signal for {order.quantity} shares of {order.symbol}. Reasons: {', '.join(evaluation['reasons'][:3])}",
            data={
                'order_id': str(order.id),
                'strategy_id': str(self.strategy.id),
                'symbol': order.symbol,
                'signal': evaluation['signal'],
                'confidence': evaluation['confidence']
            }
        )

    async def _send_execution_summary(self, results: List[Dict[str, Any]]):
        """Send summary notification after executing watchlist."""
        buy_signals = sum(1 for r in results if r['signal'] == 'buy')
        sell_signals = sum(1 for r in results if r['signal'] == 'sell')
        executed = sum(1 for r in results if r['executed'])
        errors = sum(1 for r in results if r.get('error'))

        Notification.objects.create(
            user=self.strategy.user,
            type='strategy_execution',
            title=f"Strategy Execution: {self.strategy.name}",
            message=f"Scanned {len(results)} symbols: {buy_signals} buy signals, {sell_signals} sell signals, {executed} executed, {errors} errors",
            data={
                'strategy_id': str(self.strategy.id),
                'results': results
            }
        )


async def execute_strategy(strategy_id: str, symbol: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    """
    Convenience function to execute a strategy.

    Args:
        strategy_id: Strategy UUID
        symbol: Optional specific symbol to evaluate (if None, executes entire watchlist)
        dry_run: If True, only generates signals without placing orders

    Returns:
        Execution results

    Example:
        >>> # Execute strategy on entire watchlist
        >>> results = await execute_strategy('strategy-uuid-123')

        >>> # Execute strategy on single symbol
        >>> result = await execute_strategy('strategy-uuid-123', symbol='AAPL')

        >>> # Dry run (signal generation only)
        >>> results = await execute_strategy('strategy-uuid-123', dry_run=True)
    """
    try:
        strategy = Strategy.objects.get(id=strategy_id)
        executor = StrategyExecutor(strategy, dry_run=dry_run)

        if symbol:
            result = await executor.execute_single_symbol(symbol)
            return {
                'strategy_id': strategy_id,
                'strategy_name': strategy.name,
                'result': result
            }
        else:
            results = await executor.execute_watchlist()
            return {
                'strategy_id': strategy_id,
                'strategy_name': strategy.name,
                'results': results,
                'summary': {
                    'total': len(results),
                    'buy_signals': sum(1 for r in results if r['signal'] == 'buy'),
                    'sell_signals': sum(1 for r in results if r['signal'] == 'sell'),
                    'hold_signals': sum(1 for r in results if r['signal'] == 'hold'),
                    'executed': sum(1 for r in results if r['executed']),
                    'errors': sum(1 for r in results if r.get('error'))
                }
            }

    except Strategy.DoesNotExist:
        raise StrategyExecutionError(f"Strategy {strategy_id} not found")
    except Exception as e:
        logger.error(f"Error executing strategy {strategy_id}: {e}")
        raise StrategyExecutionError(f"Failed to execute strategy: {e}")


def execute_strategy_sync(strategy_id: str, symbol: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    """
    Synchronous wrapper for execute_strategy.

    Use this from non-async contexts (e.g., Django views, Celery tasks).

    Args:
        strategy_id: Strategy UUID
        symbol: Optional specific symbol
        dry_run: Signal generation only

    Returns:
        Execution results
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(execute_strategy(strategy_id, symbol, dry_run))
    finally:
        loop.close()


class ManualTradeExecutor:
    """
    Handles manual trade execution outside of strategies.

    For users who want to manually place trades without a strategy.
    """

    def __init__(self, user, portfolio: Portfolio):
        """Initialize manual trade executor."""
        self.user = user
        self.portfolio = portfolio
        self.order_engine = OrderExecutionEngine(
            user=user,
            broker_connection=user.brokerconnection_set.filter(is_active=True).first()
        )

    async def place_market_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        notes: Optional[str] = None
    ) -> Order:
        """
        Place manual market order.

        Args:
            symbol: Stock symbol
            quantity: Number of shares
            side: 'buy' or 'sell'
            notes: Optional trade notes

        Returns:
            Created Order instance
        """
        order = await self.order_engine.submit_order(
            portfolio=self.portfolio,
            symbol=symbol,
            quantity=quantity,
            side=side,
            order_type='market'
        )

        # Add notes to metadata
        if notes:
            order.metadata = order.metadata or {}
            order.metadata['notes'] = notes
            order.save()

        # Send notification
        Notification.objects.create(
            user=self.user,
            type='manual_trade',
            title=f"Manual {side.upper()}: {symbol}",
            message=f"Placed manual {side} order for {quantity} shares of {symbol}",
            data={'order_id': str(order.id)}
        )

        return order

    async def place_limit_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        limit_price: Decimal,
        time_in_force: str = 'day',
        notes: Optional[str] = None
    ) -> Order:
        """
        Place manual limit order.

        Args:
            symbol: Stock symbol
            quantity: Number of shares
            side: 'buy' or 'sell'
            limit_price: Limit price
            time_in_force: 'day', 'gtc', 'ioc', 'fok'
            notes: Optional trade notes

        Returns:
            Created Order instance
        """
        order = await self.order_engine.submit_order(
            portfolio=self.portfolio,
            symbol=symbol,
            quantity=quantity,
            side=side,
            order_type='limit',
            limit_price=limit_price,
            time_in_force=time_in_force
        )

        if notes:
            order.metadata = order.metadata or {}
            order.metadata['notes'] = notes
            order.save()

        Notification.objects.create(
            user=self.user,
            type='manual_trade',
            title=f"Manual Limit {side.upper()}: {symbol}",
            message=f"Placed limit {side} order for {quantity} shares of {symbol} @ ${limit_price}",
            data={'order_id': str(order.id)}
        )

        return order
