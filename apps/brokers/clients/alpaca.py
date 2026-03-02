"""
Alpaca broker API client implementation.

Documentation: https://docs.alpaca.markets/
Python SDK: https://github.com/alpacahq/alpaca-py
"""
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
    GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

from typing import Dict, List, Any, Optional
from decimal import Decimal
import logging

from .base import BrokerClient

logger = logging.getLogger(__name__)


class AlpacaClient(BrokerClient):
    """
    Alpaca broker API client.

    Supports both paper and live trading.
    """

    def __init__(self, api_key: str, api_secret: str, paper: bool = True):
        """
        Initialize Alpaca client.

        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            paper: Use paper trading (default True)
        """
        super().__init__(api_key, api_secret, paper)

        # Trading client
        self.trading_client = TradingClient(
            api_key=api_key,
            secret_key=api_secret,
            paper=paper
        )

        # Data client (for quotes)
        self.data_client = StockHistoricalDataClient(
            api_key=api_key,
            secret_key=api_secret
        )

        logger.info(f"Initialized Alpaca client (paper={paper})")

    async def get_account_info(self) -> Dict[str, Any]:
        """Get Alpaca account information."""
        try:
            account = self.trading_client.get_account()

            return {
                'account_number': account.account_number,
                'cash': Decimal(str(account.cash)),
                'buying_power': Decimal(str(account.buying_power)),
                'portfolio_value': Decimal(str(account.portfolio_value)),
                'currency': account.currency,
                'pattern_day_trader': account.pattern_day_trader,
                'trading_blocked': account.trading_blocked,
                'status': account.status,
            }

        except Exception as e:
            logger.error(f"Error getting Alpaca account info: {e}")
            raise

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
        """Submit order to Alpaca."""
        self._validate_order_params(symbol, quantity, side, order_type)

        try:
            # Convert side to Alpaca enum
            alpaca_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL

            # Convert time_in_force to Alpaca enum
            tif_map = {
                'day': TimeInForce.DAY,
                'gtc': TimeInForce.GTC,
                'ioc': TimeInForce.IOC,
                'fok': TimeInForce.FOK
            }
            alpaca_tif = tif_map.get(time_in_force.lower(), TimeInForce.DAY)

            # Create appropriate order request
            if order_type.lower() == 'market':
                order_request = MarketOrderRequest(
                    symbol=symbol.upper(),
                    qty=quantity,
                    side=alpaca_side,
                    time_in_force=alpaca_tif
                )

            elif order_type.lower() == 'limit':
                if not limit_price:
                    raise ValueError("Limit price required for limit orders")

                order_request = LimitOrderRequest(
                    symbol=symbol.upper(),
                    qty=quantity,
                    side=alpaca_side,
                    time_in_force=alpaca_tif,
                    limit_price=float(limit_price)
                )

            elif order_type.lower() == 'stop':
                if not stop_price:
                    raise ValueError("Stop price required for stop orders")

                order_request = StopOrderRequest(
                    symbol=symbol.upper(),
                    qty=quantity,
                    side=alpaca_side,
                    time_in_force=alpaca_tif,
                    stop_price=float(stop_price)
                )

            elif order_type.lower() == 'stop_limit':
                if not stop_price or not limit_price:
                    raise ValueError("Stop price and limit price required for stop limit orders")

                order_request = StopLimitOrderRequest(
                    symbol=symbol.upper(),
                    qty=quantity,
                    side=alpaca_side,
                    time_in_force=alpaca_tif,
                    stop_price=float(stop_price),
                    limit_price=float(limit_price)
                )

            else:
                raise ValueError(f"Unsupported order type: {order_type}")

            # Submit order
            order = self.trading_client.submit_order(order_request)

            logger.info(f"Submitted Alpaca order: {order.id} for {symbol}")

            return self._normalize_order(order)

        except Exception as e:
            logger.error(f"Error submitting Alpaca order: {e}")
            raise

    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an Alpaca order."""
        try:
            self.trading_client.cancel_order_by_id(broker_order_id)
            logger.info(f"Cancelled Alpaca order: {broker_order_id}")
            return True

        except Exception as e:
            logger.error(f"Error cancelling Alpaca order {broker_order_id}: {e}")
            return False

    async def get_order_status(self, broker_order_id: str) -> Dict[str, Any]:
        """Get Alpaca order status."""
        try:
            order = self.trading_client.get_order_by_id(broker_order_id)
            return self._normalize_order(order)

        except Exception as e:
            logger.error(f"Error getting Alpaca order status {broker_order_id}: {e}")
            raise

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get all Alpaca positions."""
        try:
            positions = self.trading_client.get_all_positions()

            return [self._normalize_position(pos) for pos in positions]

        except Exception as e:
            logger.error(f"Error getting Alpaca positions: {e}")
            raise

    async def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get Alpaca position for a symbol."""
        try:
            position = self.trading_client.get_open_position(symbol.upper())
            return self._normalize_position(position)

        except Exception as e:
            # Alpaca raises exception if no position found
            logger.debug(f"No position found for {symbol}: {e}")
            return None

    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close Alpaca position."""
        try:
            order = self.trading_client.close_position(symbol.upper())
            logger.info(f"Closed Alpaca position for {symbol}")
            return self._normalize_order(order)

        except Exception as e:
            logger.error(f"Error closing Alpaca position {symbol}: {e}")
            raise

    async def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get Alpaca orders."""
        try:
            # Map status to Alpaca enum
            if status:
                status_map = {
                    'open': QueryOrderStatus.OPEN,
                    'closed': QueryOrderStatus.CLOSED,
                    'all': QueryOrderStatus.ALL
                }
                alpaca_status = status_map.get(status.lower(), QueryOrderStatus.ALL)
            else:
                alpaca_status = QueryOrderStatus.ALL

            # Create request
            request = GetOrdersRequest(
                status=alpaca_status,
                limit=limit
            )

            orders = self.trading_client.get_orders(request)

            return [self._normalize_order(order) for order in orders]

        except Exception as e:
            logger.error(f"Error getting Alpaca orders: {e}")
            raise

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get latest quote from Alpaca."""
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol.upper())
            quotes = self.data_client.get_stock_latest_quote(request)
            quote = quotes[symbol.upper()]

            return {
                'symbol': symbol.upper(),
                'bid': Decimal(str(quote.bid_price)),
                'ask': Decimal(str(quote.ask_price)),
                'bid_size': quote.bid_size,
                'ask_size': quote.ask_size,
                'timestamp': quote.timestamp
            }

        except Exception as e:
            logger.error(f"Error getting Alpaca quote for {symbol}: {e}")
            raise

    def get_broker_name(self) -> str:
        """Get broker name."""
        return 'alpaca_paper' if self.paper else 'alpaca'

    def _normalize_order(self, order) -> Dict[str, Any]:
        """
        Normalize Alpaca order to standard format.

        Args:
            order: Alpaca Order object

        Returns:
            Normalized order dictionary
        """
        return {
            'broker_order_id': str(order.id),
            'status': self._map_order_status(order.status),
            'symbol': order.symbol,
            'quantity': int(order.qty),
            'filled_qty': int(order.filled_qty) if order.filled_qty else 0,
            'side': order.side.value,
            'type': order.type.value,
            'time_in_force': order.time_in_force.value,
            'limit_price': Decimal(str(order.limit_price)) if order.limit_price else None,
            'stop_price': Decimal(str(order.stop_price)) if order.stop_price else None,
            'filled_avg_price': Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None,
            'submitted_at': order.submitted_at,
            'filled_at': order.filled_at,
            'created_at': order.created_at,
            'updated_at': order.updated_at,
        }

    def _normalize_position(self, position) -> Dict[str, Any]:
        """
        Normalize Alpaca position to standard format.

        Args:
            position: Alpaca Position object

        Returns:
            Normalized position dictionary
        """
        qty = int(position.qty)
        side = 'long' if qty > 0 else 'short'

        return {
            'symbol': position.symbol,
            'quantity': abs(qty),
            'side': side,
            'avg_entry_price': Decimal(str(position.avg_entry_price)),
            'current_price': Decimal(str(position.current_price)),
            'market_value': Decimal(str(position.market_value)),
            'cost_basis': Decimal(str(position.cost_basis)),
            'unrealized_pnl': Decimal(str(position.unrealized_pl)),
            'unrealized_pnl_pct': Decimal(str(position.unrealized_plpc)) * 100,
        }

    def _map_order_status(self, alpaca_status: str) -> str:
        """
        Map Alpaca order status to our standard status.

        Args:
            alpaca_status: Alpaca order status

        Returns:
            Standard order status
        """
        status_map = {
            'new': 'submitted',
            'accepted': 'submitted',
            'pending_new': 'pending',
            'accepted_for_bidding': 'submitted',
            'stopped': 'submitted',
            'rejected': 'rejected',
            'suspended': 'submitted',
            'calculated': 'submitted',
            'partial_fill': 'partially_filled',
            'filled': 'filled',
            'done_for_day': 'filled',
            'canceled': 'cancelled',
            'expired': 'expired',
            'replaced': 'cancelled',
            'pending_cancel': 'submitted',
            'pending_replace': 'submitted',
        }

        return status_map.get(alpaca_status.lower(), 'pending')
