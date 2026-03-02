"""
Order service utilities and helper functions.

Provides convenience functions for order management, validation, and queries.
"""
from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
import logging

from .models import Order, Trade
from apps.portfolios.models import Portfolio

logger = logging.getLogger(__name__)


def get_user_orders(
    user,
    status: Optional[str] = None,
    portfolio_id: Optional[int] = None,
    symbol: Optional[str] = None,
    limit: int = 100
) -> List[Order]:
    """
    Get user's orders with optional filtering.

    Args:
        user: User instance
        status: Filter by status ('pending', 'filled', 'cancelled', etc.)
        portfolio_id: Filter by portfolio ID
        symbol: Filter by symbol
        limit: Maximum number of orders to return

    Returns:
        List of Order instances

    Example:
        >>> orders = get_user_orders(user, status='filled', symbol='AAPL')
    """
    query = Order.objects.filter(portfolio__user=user)

    if status:
        query = query.filter(status=status)

    if portfolio_id:
        query = query.filter(portfolio_id=portfolio_id)

    if symbol:
        query = query.filter(symbol=symbol.upper())

    return query.order_by('-created_at')[:limit]


def get_pending_orders(user, portfolio: Optional[Portfolio] = None) -> List[Order]:
    """
    Get user's pending orders.

    Args:
        user: User instance
        portfolio: Optional portfolio filter

    Returns:
        List of pending Order instances
    """
    query = Order.objects.filter(
        portfolio__user=user,
        status__in=['pending', 'submitted', 'partially_filled']
    )

    if portfolio:
        query = query.filter(portfolio=portfolio)

    return query.order_by('-created_at')


def get_order_history(
    user,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    symbol: Optional[str] = None
) -> List[Order]:
    """
    Get order history for a date range.

    Args:
        user: User instance
        start_date: Start date (default: 30 days ago)
        end_date: End date (default: now)
        symbol: Optional symbol filter

    Returns:
        List of Order instances
    """
    if not start_date:
        start_date = timezone.now() - timedelta(days=30)

    if not end_date:
        end_date = timezone.now()

    query = Order.objects.filter(
        portfolio__user=user,
        created_at__range=(start_date, end_date)
    )

    if symbol:
        query = query.filter(symbol=symbol.upper())

    return query.order_by('-created_at')


def get_trades_for_symbol(user, symbol: str, limit: int = 100) -> List[Trade]:
    """
    Get all trades for a specific symbol.

    Args:
        user: User instance
        symbol: Stock symbol
        limit: Maximum trades to return

    Returns:
        List of Trade instances
    """
    return Trade.objects.filter(
        portfolio__user=user,
        symbol=symbol.upper()
    ).order_by('-executed_at')[:limit]


def calculate_order_cost(order: Order, use_filled: bool = False) -> Decimal:
    """
    Calculate total cost/proceeds of an order.

    Args:
        order: Order instance
        use_filled: Use filled quantities instead of order quantities

    Returns:
        Total cost (positive for buys, negative for sells)
    """
    if use_filled and order.filled_avg_price:
        price = order.filled_avg_price
        quantity = order.filled_qty or order.quantity
    else:
        price = order.limit_price or Decimal('0')
        quantity = order.quantity

    cost = price * quantity

    # Negative for sells
    if order.side == 'sell':
        cost = -cost

    return cost


def get_order_statistics(user, portfolio: Optional[Portfolio] = None) -> Dict[str, Any]:
    """
    Get order statistics for user or portfolio.

    Args:
        user: User instance
        portfolio: Optional portfolio filter

    Returns:
        Dictionary with order statistics
    """
    query = Order.objects.filter(portfolio__user=user)

    if portfolio:
        query = query.filter(portfolio=portfolio)

    stats = query.aggregate(
        total_orders=Count('id'),
        filled_orders=Count('id', filter=Q(status='filled')),
        cancelled_orders=Count('id', filter=Q(status='cancelled')),
        pending_orders=Count('id', filter=Q(status__in=['pending', 'submitted', 'partially_filled'])),
    )

    # Calculate fill rate
    if stats['total_orders'] > 0:
        stats['fill_rate'] = (stats['filled_orders'] / stats['total_orders']) * 100
    else:
        stats['fill_rate'] = 0

    return stats


def get_trade_statistics(user, portfolio: Optional[Portfolio] = None) -> Dict[str, Any]:
    """
    Get trade statistics for user or portfolio.

    Args:
        user: User instance
        portfolio: Optional portfolio filter

    Returns:
        Dictionary with trade statistics
    """
    query = Trade.objects.filter(portfolio__user=user)

    if portfolio:
        query = query.filter(portfolio=portfolio)

    stats = query.aggregate(
        total_trades=Count('id'),
        buy_trades=Count('id', filter=Q(side='buy')),
        sell_trades=Count('id', filter=Q(side='sell')),
        total_volume=Sum('quantity'),
        avg_price=Avg('price')
    )

    return stats


def validate_order_modification(order: Order) -> tuple[bool, Optional[str]]:
    """
    Validate if an order can be modified or cancelled.

    Args:
        order: Order instance

    Returns:
        Tuple of (can_modify, error_message)
    """
    # Check if in modifiable state
    if order.status in ['filled', 'cancelled', 'rejected', 'expired']:
        return False, f"Cannot modify order in status: {order.status}"

    # Check if broker order ID exists
    if not order.broker_order_id:
        return False, "Order not yet submitted to broker"

    return True, None


def get_open_orders_by_symbol(user, symbol: str) -> List[Order]:
    """
    Get all open orders for a specific symbol.

    Args:
        user: User instance
        symbol: Stock symbol

    Returns:
        List of open Order instances
    """
    return Order.objects.filter(
        portfolio__user=user,
        symbol=symbol.upper(),
        status__in=['pending', 'submitted', 'partially_filled']
    ).order_by('-created_at')


def get_order_exposure(user, symbol: Optional[str] = None) -> Dict[str, Decimal]:
    """
    Calculate total order exposure (pending orders).

    Args:
        user: User instance
        symbol: Optional symbol filter

    Returns:
        Dictionary with buy and sell exposure
    """
    query = Order.objects.filter(
        portfolio__user=user,
        status__in=['pending', 'submitted']
    )

    if symbol:
        query = query.filter(symbol=symbol.upper())

    exposure = {
        'buy_exposure': Decimal('0'),
        'sell_exposure': Decimal('0')
    }

    for order in query:
        cost = abs(calculate_order_cost(order, use_filled=False))

        if order.side == 'buy':
            exposure['buy_exposure'] += cost
        elif order.side == 'sell':
            exposure['sell_exposure'] += cost

    return exposure


def get_average_fill_price(symbol: str, user, days: int = 30) -> Optional[Decimal]:
    """
    Get average fill price for a symbol over a period.

    Args:
        symbol: Stock symbol
        user: User instance
        days: Number of days to look back

    Returns:
        Average fill price or None
    """
    start_date = timezone.now() - timedelta(days=days)

    trades = Trade.objects.filter(
        portfolio__user=user,
        symbol=symbol.upper(),
        executed_at__gte=start_date
    )

    result = trades.aggregate(avg_price=Avg('price'))
    return result['avg_price']


def check_duplicate_order(
    user,
    symbol: str,
    quantity: int,
    side: str,
    order_type: str,
    minutes: int = 1
) -> Optional[Order]:
    """
    Check for duplicate orders within a time window.

    Args:
        user: User instance
        symbol: Stock symbol
        quantity: Order quantity
        side: Order side
        order_type: Order type
        minutes: Time window in minutes

    Returns:
        Existing order if duplicate found, None otherwise
    """
    threshold = timezone.now() - timedelta(minutes=minutes)

    existing = Order.objects.filter(
        portfolio__user=user,
        symbol=symbol.upper(),
        quantity=quantity,
        side=side,
        type=order_type,
        created_at__gte=threshold,
        status__in=['pending', 'submitted']
    ).first()

    return existing


def get_order_summary_by_symbol(user, days: int = 30) -> Dict[str, Dict[str, Any]]:
    """
    Get order summary grouped by symbol.

    Args:
        user: User instance
        days: Number of days to look back

    Returns:
        Dictionary mapping symbol to summary statistics
    """
    start_date = timezone.now() - timedelta(days=days)

    orders = Order.objects.filter(
        portfolio__user=user,
        created_at__gte=start_date
    ).values('symbol').annotate(
        total_orders=Count('id'),
        filled_orders=Count('id', filter=Q(status='filled')),
        total_quantity=Sum('quantity'),
        avg_fill_price=Avg('filled_avg_price', filter=Q(status='filled'))
    )

    summary = {}
    for order_data in orders:
        symbol = order_data['symbol']
        summary[symbol] = {
            'total_orders': order_data['total_orders'],
            'filled_orders': order_data['filled_orders'],
            'total_quantity': order_data['total_quantity'] or 0,
            'avg_fill_price': order_data['avg_fill_price'] or Decimal('0'),
            'fill_rate': (
                (order_data['filled_orders'] / order_data['total_orders'] * 100)
                if order_data['total_orders'] > 0 else 0
            )
        }

    return summary


def get_recent_trades(user, limit: int = 50) -> List[Trade]:
    """
    Get recent trades for user.

    Args:
        user: User instance
        limit: Maximum trades to return

    Returns:
        List of Trade instances
    """
    return Trade.objects.filter(
        portfolio__user=user
    ).select_related('order', 'portfolio').order_by('-executed_at')[:limit]


def is_market_hours() -> bool:
    """
    Check if current time is within market hours (US markets).

    Returns:
        True if market is open

    Note:
        This is a simplified check. For production, use a proper market calendar.
    """
    now = timezone.now()

    # Check if weekend
    if now.weekday() >= 5:  # Saturday or Sunday
        return False

    # Check time (9:30 AM - 4:00 PM ET)
    # This is simplified - should convert to ET timezone
    hour = now.hour
    minute = now.minute

    market_open = (hour > 9) or (hour == 9 and minute >= 30)
    market_close = hour < 16

    return market_open and market_close


def format_order_for_display(order: Order) -> Dict[str, Any]:
    """
    Format order data for display/API response.

    Args:
        order: Order instance

    Returns:
        Formatted dictionary with order details
    """
    return {
        'id': order.id,
        'symbol': order.symbol,
        'quantity': order.quantity,
        'filled_qty': order.filled_qty,
        'side': order.side,
        'type': order.type,
        'status': order.status,
        'limit_price': float(order.limit_price) if order.limit_price else None,
        'stop_price': float(order.stop_price) if order.stop_price else None,
        'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
        'time_in_force': order.time_in_force,
        'created_at': order.created_at.isoformat(),
        'submitted_at': order.submitted_at.isoformat() if order.submitted_at else None,
        'filled_at': order.filled_at.isoformat() if order.filled_at else None,
        'broker_order_id': order.broker_order_id,
        'portfolio_id': order.portfolio_id,
    }
