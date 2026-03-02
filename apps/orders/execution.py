"""
Order execution engine for submitting and managing orders with brokers.

Handles order lifecycle: validation → submission → tracking → completion
Integrates with broker clients and portfolio management.
"""
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime
import logging

from django.db import transaction
from django.utils import timezone

from .models import Order, Trade
from apps.brokers.services import get_broker_client
from apps.brokers.models import BrokerConnection
from apps.portfolios.models import Portfolio, Position
from apps.market_data.cache import MarketDataCache
from apps.market_data.provider_manager import get_provider_manager

logger = logging.getLogger(__name__)


class OrderExecutionError(Exception):
    """Raised when order execution fails."""
    pass


class OrderExecutionEngine:
    """
    Engine for executing orders through broker APIs.

    Handles the complete order lifecycle including validation,
    submission to broker, tracking, and portfolio updates.
    """

    def __init__(self, user, broker_connection: Optional[BrokerConnection] = None):
        """
        Initialize execution engine.

        Args:
            user: User instance
            broker_connection: Optional specific broker connection (defaults to active)
        """
        self.user = user
        self.broker_connection = broker_connection

        if not self.broker_connection:
            # Get user's active broker connection
            from apps.brokers.services import get_active_broker_connection
            self.broker_connection = get_active_broker_connection(user)

            if not self.broker_connection:
                raise OrderExecutionError("No active broker connection found for user")

        self.broker_client = get_broker_client(self.broker_connection)
        logger.info(f"Initialized OrderExecutionEngine for user {user.id} with broker {self.broker_connection.broker}")

    async def submit_order(
        self,
        portfolio: Portfolio,
        symbol: str,
        quantity: int,
        side: str,
        order_type: str = 'market',
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: str = 'day',
        strategy_id: Optional[int] = None,
        agent_run_id: Optional[int] = None
    ) -> Order:
        """
        Submit order to broker.

        Args:
            portfolio: Portfolio to execute order for
            symbol: Stock symbol
            quantity: Number of shares
            side: 'buy' or 'sell'
            order_type: 'market', 'limit', 'stop', 'stop_limit'
            limit_price: Limit price (for limit orders)
            stop_price: Stop price (for stop orders)
            time_in_force: 'day', 'gtc', 'ioc', 'fok'
            strategy_id: Optional strategy ID
            agent_run_id: Optional agent run ID

        Returns:
            Created Order instance

        Raises:
            OrderExecutionError: If validation or submission fails
        """
        # Validate portfolio ownership
        if portfolio.user != self.user:
            raise OrderExecutionError("Portfolio does not belong to user")

        # Validate order parameters
        await self._validate_order(portfolio, symbol, quantity, side, order_type, limit_price, stop_price)

        # Create order in database (pending status)
        order = await self._create_order(
            portfolio=portfolio,
            symbol=symbol,
            quantity=quantity,
            side=side,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            strategy_id=strategy_id,
            agent_run_id=agent_run_id
        )

        try:
            # Submit to broker
            broker_response = await self.broker_client.submit_order(
                symbol=symbol,
                quantity=quantity,
                side=side,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
                time_in_force=time_in_force
            )

            # Update order with broker details
            order.broker_order_id = broker_response['broker_order_id']
            order.status = broker_response['status']
            order.submitted_at = broker_response.get('submitted_at', timezone.now())
            order.save()

            logger.info(f"Submitted order {order.id} to {self.broker_connection.broker}: {broker_response['broker_order_id']}")

            return order

        except Exception as e:
            # Update order as failed
            order.status = 'rejected'
            order.metadata = order.metadata or {}
            order.metadata['error'] = str(e)
            order.save()

            logger.error(f"Failed to submit order {order.id}: {e}")
            raise OrderExecutionError(f"Failed to submit order: {e}")

    async def cancel_order(self, order: Order) -> bool:
        """
        Cancel a pending order.

        Args:
            order: Order instance to cancel

        Returns:
            True if cancelled successfully

        Raises:
            OrderExecutionError: If cancellation fails
        """
        # Validate order ownership
        if order.portfolio.user != self.user:
            raise OrderExecutionError("Order does not belong to user")

        # Check if order is cancellable
        if order.status not in ['pending', 'submitted', 'partially_filled']:
            raise OrderExecutionError(f"Cannot cancel order with status: {order.status}")

        if not order.broker_order_id:
            raise OrderExecutionError("Order has no broker ID")

        try:
            # Cancel with broker
            success = await self.broker_client.cancel_order(order.broker_order_id)

            if success:
                order.status = 'cancelled'
                order.cancelled_at = timezone.now()
                order.save()

                logger.info(f"Cancelled order {order.id} (broker ID: {order.broker_order_id})")
                return True
            else:
                raise OrderExecutionError("Broker returned failure for cancellation")

        except Exception as e:
            logger.error(f"Failed to cancel order {order.id}: {e}")
            raise OrderExecutionError(f"Failed to cancel order: {e}")

    async def update_order_status(self, order: Order) -> Order:
        """
        Update order status from broker.

        Args:
            order: Order instance to update

        Returns:
            Updated Order instance
        """
        if not order.broker_order_id:
            logger.warning(f"Order {order.id} has no broker ID, cannot update status")
            return order

        try:
            broker_status = await self.broker_client.get_order_status(order.broker_order_id)

            # Update order fields
            old_status = order.status
            order.status = broker_status['status']
            order.filled_qty = broker_status.get('filled_qty', order.filled_qty)
            order.filled_avg_price = broker_status.get('filled_avg_price')

            if broker_status.get('filled_at'):
                order.filled_at = broker_status['filled_at']

            order.save()

            # If order status changed to filled, create trade record
            if old_status != 'filled' and order.status == 'filled':
                await self._create_trade_from_order(order)

            logger.debug(f"Updated order {order.id} status: {old_status} → {order.status}")

            return order

        except Exception as e:
            logger.error(f"Failed to update order {order.id} status: {e}")
            raise OrderExecutionError(f"Failed to update order status: {e}")

    async def _validate_order(
        self,
        portfolio: Portfolio,
        symbol: str,
        quantity: int,
        side: str,
        order_type: str,
        limit_price: Optional[Decimal],
        stop_price: Optional[Decimal]
    ):
        """Validate order parameters."""
        # Basic validation
        if quantity <= 0:
            raise OrderExecutionError("Quantity must be positive")

        if side not in ['buy', 'sell']:
            raise OrderExecutionError("Side must be 'buy' or 'sell'")

        if order_type not in ['market', 'limit', 'stop', 'stop_limit']:
            raise OrderExecutionError(f"Invalid order type: {order_type}")

        # Validate prices
        if order_type == 'limit' and not limit_price:
            raise OrderExecutionError("Limit price required for limit orders")

        if order_type == 'stop' and not stop_price:
            raise OrderExecutionError("Stop price required for stop orders")

        if order_type == 'stop_limit' and (not stop_price or not limit_price):
            raise OrderExecutionError("Stop price and limit price required for stop limit orders")

        # Check buying power for buy orders
        if side == 'buy':
            await self._validate_buying_power(portfolio, symbol, quantity, limit_price)

        # Check position for sell orders
        if side == 'sell':
            await self._validate_position(portfolio, symbol, quantity)

    async def _validate_buying_power(
        self,
        portfolio: Portfolio,
        symbol: str,
        quantity: int,
        limit_price: Optional[Decimal]
    ):
        """Validate sufficient buying power for purchase."""
        # Get current price
        if limit_price:
            estimated_price = limit_price
        else:
            quote = await self._get_quote(symbol)
            estimated_price = quote['ask']

        # Calculate estimated cost
        estimated_cost = estimated_price * quantity

        # Check against portfolio cash (simplified - should check actual account)
        if portfolio.cash < estimated_cost:
            raise OrderExecutionError(
                f"Insufficient buying power. Need ${estimated_cost}, have ${portfolio.cash}"
            )

    async def _validate_position(self, portfolio: Portfolio, symbol: str, quantity: int):
        """Validate sufficient position for sale."""
        position = Position.objects.filter(portfolio=portfolio, symbol=symbol).first()

        if not position:
            raise OrderExecutionError(f"No position in {symbol} to sell")

        if position.quantity < quantity:
            raise OrderExecutionError(
                f"Insufficient position. Trying to sell {quantity}, have {position.quantity}"
            )

    async def _get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote for symbol."""
        # Try cache first
        cached = MarketDataCache.get_quote(symbol)
        if cached:
            return cached

        # Fetch from provider
        provider_manager = get_provider_manager()
        quote = await provider_manager.get_quote(symbol, use_cache=True)

        return quote

    async def _create_order(
        self,
        portfolio: Portfolio,
        symbol: str,
        quantity: int,
        side: str,
        order_type: str,
        limit_price: Optional[Decimal],
        stop_price: Optional[Decimal],
        time_in_force: str,
        strategy_id: Optional[int],
        agent_run_id: Optional[int]
    ) -> Order:
        """Create order in database."""
        order = Order.objects.create(
            portfolio=portfolio,
            symbol=symbol,
            quantity=quantity,
            side=side,
            type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            status='pending',
            strategy_id=strategy_id,
            agent_run_id=agent_run_id
        )

        logger.info(f"Created order {order.id}: {side} {quantity} {symbol} @ {order_type}")
        return order

    @transaction.atomic
    async def _create_trade_from_order(self, order: Order):
        """Create trade record when order is filled."""
        if order.status != 'filled':
            return

        # Create trade
        trade = Trade.objects.create(
            order=order,
            portfolio=order.portfolio,
            symbol=order.symbol,
            quantity=order.filled_qty or order.quantity,
            price=order.filled_avg_price,
            side=order.side,
            executed_at=order.filled_at or timezone.now(),
            broker_trade_id=order.broker_order_id
        )

        # Update portfolio position
        await self._update_position_from_trade(trade)

        logger.info(f"Created trade {trade.id} from order {order.id}")

    @transaction.atomic
    async def _update_position_from_trade(self, trade: Trade):
        """Update portfolio position from executed trade."""
        position, created = Position.objects.get_or_create(
            portfolio=trade.portfolio,
            symbol=trade.symbol,
            defaults={
                'quantity': 0,
                'avg_price': Decimal('0'),
                'cost_basis': Decimal('0')
            }
        )

        if trade.side == 'buy':
            # Add to position
            total_cost = position.cost_basis + (trade.price * trade.quantity)
            total_qty = position.quantity + trade.quantity
            position.quantity = total_qty
            position.avg_price = total_cost / total_qty if total_qty > 0 else Decimal('0')
            position.cost_basis = total_cost

        elif trade.side == 'sell':
            # Reduce position
            position.quantity -= trade.quantity
            if position.quantity <= 0:
                # Closed position
                position.quantity = 0
                position.avg_price = Decimal('0')
                position.cost_basis = Decimal('0')
            else:
                # Partial sale - reduce cost basis proportionally
                position.cost_basis = position.avg_price * position.quantity

        position.save()

        logger.info(f"Updated position {position.id}: {position.symbol} qty={position.quantity}")


async def execute_order(
    user,
    portfolio: Portfolio,
    symbol: str,
    quantity: int,
    side: str,
    **kwargs
) -> Order:
    """
    Convenience function to execute an order.

    Args:
        user: User instance
        portfolio: Portfolio instance
        symbol: Stock symbol
        quantity: Number of shares
        side: 'buy' or 'sell'
        **kwargs: Additional order parameters

    Returns:
        Executed Order instance

    Example:
        >>> order = await execute_order(
        >>>     user=user,
        >>>     portfolio=portfolio,
        >>>     symbol='AAPL',
        >>>     quantity=10,
        >>>     side='buy',
        >>>     order_type='market'
        >>> )
    """
    engine = OrderExecutionEngine(user)
    return await engine.submit_order(portfolio, symbol, quantity, side, **kwargs)
