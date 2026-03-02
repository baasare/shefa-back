"""
Abstract base class for broker API clients.

All broker implementations must inherit from this class and implement
the required methods.
"""
from decimal import Decimal
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class BrokerClient(ABC):
    """Abstract interface for broker API clients."""

    def __init__(self, api_key: str, api_secret: str = "", paper: bool = True):
        """
        Initialize broker client.

        Args:
            api_key: Broker API key
            api_secret: Broker API secret (if required)
            paper: Whether to use paper trading (default True)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper = paper

    @abstractmethod
    async def get_account_info(self) -> Dict[str, Any]:
        """
        Get account information.

        Returns:
            Dictionary containing:
            - account_number: Account ID
            - cash: Available cash
            - buying_power: Total buying power
            - portfolio_value: Total portfolio value
            - currency: Account currency
        """
        pass

    @abstractmethod
    async def submit_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        order_type: str,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: str = 'day'
    ) -> Dict[str, Any]:
        """
        Submit an order.

        Args:
            symbol: Stock symbol
            quantity: Number of shares
            side: 'buy' or 'sell'
            order_type: 'market', 'limit', 'stop', 'stop_limit'
            limit_price: Limit price (for limit orders)
            stop_price: Stop price (for stop orders)
            time_in_force: 'day', 'gtc', 'ioc', 'fok'

        Returns:
            Dictionary containing:
            - broker_order_id: Broker's order ID
            - status: Order status
            - submitted_at: Submission timestamp
            - symbol: Stock symbol
            - quantity: Order quantity
            - side: Order side
            - type: Order type
        """
        pass

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            broker_order_id: Broker's order ID

        Returns:
            True if cancelled successfully
        """
        pass

    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> Dict[str, Any]:
        """
        Get order status.

        Args:
            broker_order_id: Broker's order ID

        Returns:
            Dictionary containing:
            - broker_order_id: Broker's order ID
            - status: Current status
            - filled_qty: Quantity filled
            - filled_avg_price: Average fill price
            - filled_at: Fill timestamp (if filled)
        """
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get all current positions.

        Returns:
            List of positions, each containing:
            - symbol: Stock symbol
            - quantity: Position quantity
            - side: 'long' or 'short'
            - avg_entry_price: Average entry price
            - current_price: Current market price
            - market_value: Current market value
            - unrealized_pnl: Unrealized profit/loss
            - cost_basis: Total cost basis
        """
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get position for a specific symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Position dictionary or None if no position
        """
        pass

    @abstractmethod
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """
        Close an entire position.

        Args:
            symbol: Stock symbol

        Returns:
            Order dictionary for the closing order
        """
        pass

    @abstractmethod
    async def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get orders.

        Args:
            status: Filter by status ('open', 'closed', 'all')
            limit: Maximum number of orders to return

        Returns:
            List of order dictionaries
        """
        pass

    @abstractmethod
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get current quote for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Quote dictionary containing:
            - symbol: Stock symbol
            - bid: Bid price
            - ask: Ask price
            - last: Last trade price
            - timestamp: Quote timestamp
        """
        pass

    @abstractmethod
    def get_broker_name(self) -> str:
        """
        Get broker name.

        Returns:
            Broker name (e.g., 'alpaca', 'ibkr')
        """
        pass

    async def close(self):
        """Close any open connections."""
        pass

    def _validate_order_params(
        self,
        symbol: str,
        quantity: int,
        side: str,
        order_type: str
    ):
        """
        Validate order parameters.

        Raises:
            ValueError: If parameters are invalid
        """
        if not symbol:
            raise ValueError("Symbol is required")

        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        if side not in ['buy', 'sell']:
            raise ValueError("Side must be 'buy' or 'sell'")

        if order_type not in ['market', 'limit', 'stop', 'stop_limit', 'trailing_stop']:
            raise ValueError(f"Invalid order type: {order_type}")

    def _normalize_side(self, side: str) -> str:
        """
        Normalize order side to lowercase.

        Args:
            side: Order side ('buy', 'sell', 'BUY', 'SELL')

        Returns:
            Normalized side ('buy' or 'sell')
        """
        return side.lower()

    def _normalize_order_type(self, order_type: str) -> str:
        """
        Normalize order type to lowercase.

        Args:
            order_type: Order type

        Returns:
            Normalized order type
        """
        return order_type.lower()
