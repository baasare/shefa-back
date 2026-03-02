"""
Portfolio service utilities for P&L calculations, performance metrics, and position management.

Provides comprehensive portfolio analytics and management functions.
"""
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Sum, Avg, Q
from django.utils import timezone
import logging

from .models import Portfolio, Position, PortfolioSnapshot
from apps.orders.models import Trade
from apps.market_data.cache import MarketDataCache
from apps.market_data.provider_manager import get_provider_manager

logger = logging.getLogger(__name__)


async def calculate_portfolio_value(portfolio: Portfolio) -> Dict[str, Decimal]:
    """
    Calculate current portfolio value including cash and positions.

    Args:
        portfolio: Portfolio instance

    Returns:
        Dictionary with value breakdown:
        - cash: Cash balance
        - positions_value: Total value of positions
        - total_value: Total portfolio value
        - unrealized_pnl: Total unrealized P&L
    """
    cash = portfolio.cash
    positions_value = Decimal('0')
    unrealized_pnl = Decimal('0')

    # Get all positions
    positions = Position.objects.filter(portfolio=portfolio, quantity__gt=0)

    # Calculate value of each position
    for position in positions:
        position_data = await calculate_position_value(position)
        positions_value += position_data['market_value']
        unrealized_pnl += position_data['unrealized_pnl']

    total_value = cash + positions_value

    return {
        'cash': cash,
        'positions_value': positions_value,
        'total_value': total_value,
        'unrealized_pnl': unrealized_pnl
    }


async def calculate_position_value(position: Position) -> Dict[str, Decimal]:
    """
    Calculate current value and P&L for a position.

    Args:
        position: Position instance

    Returns:
        Dictionary with position metrics:
        - market_value: Current market value
        - cost_basis: Original cost basis
        - unrealized_pnl: Unrealized profit/loss
        - unrealized_pnl_pct: Unrealized P&L percentage
        - current_price: Current market price
    """
    if position.quantity <= 0:
        return {
            'market_value': Decimal('0'),
            'cost_basis': Decimal('0'),
            'unrealized_pnl': Decimal('0'),
            'unrealized_pnl_pct': Decimal('0'),
            'current_price': Decimal('0')
        }

    # Get current price
    current_price = await get_current_price(position.symbol)

    # Calculate values
    market_value = current_price * position.quantity
    cost_basis = position.cost_basis
    unrealized_pnl = market_value - cost_basis

    # Calculate percentage
    if cost_basis > 0:
        unrealized_pnl_pct = (unrealized_pnl / cost_basis) * 100
    else:
        unrealized_pnl_pct = Decimal('0')

    return {
        'market_value': market_value,
        'cost_basis': cost_basis,
        'unrealized_pnl': unrealized_pnl,
        'unrealized_pnl_pct': unrealized_pnl_pct,
        'current_price': current_price
    }


async def get_current_price(symbol: str) -> Decimal:
    """
    Get current market price for a symbol.

    Args:
        symbol: Stock symbol

    Returns:
        Current price
    """
    # Try cache first
    cached = MarketDataCache.get_quote(symbol)
    if cached:
        # Use mid-price or last price
        if 'last' in cached:
            return Decimal(str(cached['last']))
        elif 'close' in cached:
            return Decimal(str(cached['close']))
        else:
            # Average of bid/ask
            bid = Decimal(str(cached.get('bid', 0)))
            ask = Decimal(str(cached.get('ask', 0)))
            return (bid + ask) / 2 if bid and ask else bid or ask

    # Fetch from provider
    try:
        provider_manager = get_provider_manager()
        quote = await provider_manager.get_quote(symbol, use_cache=True)

        if 'last' in quote:
            return Decimal(str(quote['last']))
        elif 'close' in quote:
            return Decimal(str(quote['close']))
        else:
            bid = Decimal(str(quote.get('bid', 0)))
            ask = Decimal(str(quote.get('ask', 0)))
            return (bid + ask) / 2 if bid and ask else bid or ask

    except Exception as e:
        logger.error(f"Error fetching price for {symbol}: {e}")
        # Return last known price from position if available
        return Decimal('0')


def calculate_realized_pnl(portfolio: Portfolio, symbol: Optional[str] = None) -> Decimal:
    """
    Calculate realized P&L from closed trades.

    Args:
        portfolio: Portfolio instance
        symbol: Optional symbol filter

    Returns:
        Total realized P&L
    """
    # Get all trades
    trades = Trade.objects.filter(portfolio=portfolio)

    if symbol:
        trades = trades.filter(symbol=symbol.upper())

    # Group by symbol and calculate FIFO P&L
    realized_pnl = Decimal('0')

    if symbol:
        symbols = [symbol.upper()]
    else:
        symbols = trades.values_list('symbol', flat=True).distinct()

    for sym in symbols:
        symbol_trades = trades.filter(symbol=sym).order_by('executed_at')

        # Separate buys and sells
        buy_queue = []
        total_pnl = Decimal('0')

        for trade in symbol_trades:
            if trade.side == 'buy':
                # Add to buy queue
                buy_queue.append({
                    'quantity': trade.quantity,
                    'price': trade.price,
                    'remaining': trade.quantity
                })

            elif trade.side == 'sell':
                # Match with oldest buys (FIFO)
                sell_qty = trade.quantity
                sell_price = trade.price

                while sell_qty > 0 and buy_queue:
                    buy = buy_queue[0]

                    if buy['remaining'] <= sell_qty:
                        # Fully close this buy
                        qty = buy['remaining']
                        pnl = (sell_price - buy['price']) * qty
                        total_pnl += pnl
                        sell_qty -= qty
                        buy_queue.pop(0)
                    else:
                        # Partially close this buy
                        qty = sell_qty
                        pnl = (sell_price - buy['price']) * qty
                        total_pnl += pnl
                        buy['remaining'] -= qty
                        sell_qty = 0

        realized_pnl += total_pnl

    return realized_pnl


async def get_portfolio_performance(portfolio: Portfolio, days: int = 30) -> Dict[str, Any]:
    """
    Get portfolio performance metrics over a period.

    Args:
        portfolio: Portfolio instance
        days: Number of days to analyze

    Returns:
        Dictionary with performance metrics
    """
    start_date = timezone.now() - timedelta(days=days)

    # Get snapshots for the period
    snapshots = PortfolioSnapshot.objects.filter(
        portfolio=portfolio,
        timestamp__gte=start_date
    ).order_by('timestamp')

    if not snapshots.exists():
        # No historical data
        current_value = await calculate_portfolio_value(portfolio)
        return {
            'current_value': current_value['total_value'],
            'start_value': current_value['total_value'],
            'change': Decimal('0'),
            'change_pct': Decimal('0'),
            'realized_pnl': calculate_realized_pnl(portfolio),
            'unrealized_pnl': current_value['unrealized_pnl']
        }

    # Get first and current values
    first_snapshot = snapshots.first()
    start_value = first_snapshot.total_value

    current_value = await calculate_portfolio_value(portfolio)
    end_value = current_value['total_value']

    # Calculate changes
    change = end_value - start_value
    change_pct = (change / start_value * 100) if start_value > 0 else Decimal('0')

    # Get realized and unrealized P&L
    realized_pnl = calculate_realized_pnl(portfolio)

    return {
        'current_value': end_value,
        'start_value': start_value,
        'change': change,
        'change_pct': change_pct,
        'realized_pnl': realized_pnl,
        'unrealized_pnl': current_value['unrealized_pnl'],
        'total_pnl': realized_pnl + current_value['unrealized_pnl']
    }


def get_position_summary(portfolio: Portfolio) -> List[Dict[str, Any]]:
    """
    Get summary of all positions in portfolio.

    Args:
        portfolio: Portfolio instance

    Returns:
        List of position summaries
    """
    positions = Position.objects.filter(portfolio=portfolio, quantity__gt=0)

    summary = []
    for position in positions:
        summary.append({
            'symbol': position.symbol,
            'quantity': position.quantity,
            'avg_price': position.avg_price,
            'cost_basis': position.cost_basis,
            'current_price': None,  # Will be filled by async call
            'market_value': None,
            'unrealized_pnl': None,
            'unrealized_pnl_pct': None
        })

    return summary


async def get_position_summary_with_prices(portfolio: Portfolio) -> List[Dict[str, Any]]:
    """
    Get summary of all positions with current prices.

    Args:
        portfolio: Portfolio instance

    Returns:
        List of position summaries with current values
    """
    positions = Position.objects.filter(portfolio=portfolio, quantity__gt=0)

    summary = []
    for position in positions:
        position_data = await calculate_position_value(position)

        summary.append({
            'symbol': position.symbol,
            'quantity': position.quantity,
            'avg_price': position.avg_price,
            'cost_basis': position.cost_basis,
            'current_price': position_data['current_price'],
            'market_value': position_data['market_value'],
            'unrealized_pnl': position_data['unrealized_pnl'],
            'unrealized_pnl_pct': position_data['unrealized_pnl_pct']
        })

    return summary


def get_top_positions(portfolio: Portfolio, limit: int = 10) -> List[Position]:
    """
    Get top positions by value.

    Args:
        portfolio: Portfolio instance
        limit: Number of positions to return

    Returns:
        List of top Position instances
    """
    # Note: This sorts by cost_basis, not market value
    # For accurate sorting by market value, use get_position_summary_with_prices
    return Position.objects.filter(
        portfolio=portfolio,
        quantity__gt=0
    ).order_by('-cost_basis')[:limit]


def calculate_portfolio_allocation(portfolio: Portfolio) -> Dict[str, Decimal]:
    """
    Calculate portfolio allocation percentages.

    Args:
        portfolio: Portfolio instance

    Returns:
        Dictionary mapping symbol to allocation percentage
    """
    positions = Position.objects.filter(portfolio=portfolio, quantity__gt=0)

    total_value = sum(p.cost_basis for p in positions)

    if total_value == 0:
        return {}

    allocation = {}
    for position in positions:
        pct = (position.cost_basis / total_value) * 100
        allocation[position.symbol] = pct

    return allocation


async def update_portfolio_snapshot(portfolio: Portfolio) -> PortfolioSnapshot:
    """
    Create a snapshot of current portfolio state.

    Args:
        portfolio: Portfolio instance

    Returns:
        Created PortfolioSnapshot instance
    """
    values = await calculate_portfolio_value(portfolio)
    realized_pnl = calculate_realized_pnl(portfolio)

    snapshot = PortfolioSnapshot.objects.create(
        portfolio=portfolio,
        timestamp=timezone.now(),
        total_value=values['total_value'],
        cash=values['cash'],
        positions_value=values['positions_value'],
        realized_pnl=realized_pnl,
        unrealized_pnl=values['unrealized_pnl']
    )

    logger.info(f"Created snapshot for portfolio {portfolio.id}: ${values['total_value']}")
    return snapshot


def get_portfolio_history(
    portfolio: Portfolio,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[PortfolioSnapshot]:
    """
    Get portfolio value history.

    Args:
        portfolio: Portfolio instance
        start_date: Start date (default: 30 days ago)
        end_date: End date (default: now)

    Returns:
        List of PortfolioSnapshot instances
    """
    if not start_date:
        start_date = timezone.now() - timedelta(days=30)

    if not end_date:
        end_date = timezone.now()

    return PortfolioSnapshot.objects.filter(
        portfolio=portfolio,
        timestamp__range=(start_date, end_date)
    ).order_by('timestamp')


def calculate_sharpe_ratio(portfolio: Portfolio, days: int = 30, risk_free_rate: Decimal = Decimal('0.04')) -> Optional[Decimal]:
    """
    Calculate Sharpe ratio for portfolio.

    Args:
        portfolio: Portfolio instance
        days: Period for calculation
        risk_free_rate: Annual risk-free rate (default 4%)

    Returns:
        Sharpe ratio or None if insufficient data
    """
    start_date = timezone.now() - timedelta(days=days)

    snapshots = PortfolioSnapshot.objects.filter(
        portfolio=portfolio,
        timestamp__gte=start_date
    ).order_by('timestamp')

    if snapshots.count() < 2:
        return None

    # Calculate daily returns
    returns = []
    snapshots_list = list(snapshots)

    for i in range(1, len(snapshots_list)):
        prev_value = snapshots_list[i-1].total_value
        curr_value = snapshots_list[i].total_value

        if prev_value > 0:
            daily_return = (curr_value - prev_value) / prev_value
            returns.append(float(daily_return))

    if not returns:
        return None

    # Calculate average return and standard deviation
    import statistics

    avg_return = Decimal(str(statistics.mean(returns)))
    std_return = Decimal(str(statistics.stdev(returns))) if len(returns) > 1 else Decimal('0')

    if std_return == 0:
        return None

    # Annualize (assuming 252 trading days)
    annual_return = avg_return * 252
    annual_std = std_return * (Decimal('252') ** Decimal('0.5'))

    # Calculate Sharpe ratio
    sharpe = (annual_return - risk_free_rate) / annual_std

    return sharpe


def get_trade_history_summary(portfolio: Portfolio, days: int = 30) -> Dict[str, Any]:
    """
    Get summary of trading activity.

    Args:
        portfolio: Portfolio instance
        days: Number of days to analyze

    Returns:
        Dictionary with trade statistics
    """
    start_date = timezone.now() - timedelta(days=days)

    trades = Trade.objects.filter(
        portfolio=portfolio,
        executed_at__gte=start_date
    )

    stats = trades.aggregate(
        total_trades=Sum('id'),
        buy_trades=Sum('id', filter=Q(side='buy')),
        sell_trades=Sum('id', filter=Q(side='sell')),
        total_volume=Sum('quantity'),
        avg_price=Avg('price')
    )

    return {
        'total_trades': trades.count(),
        'buy_trades': trades.filter(side='buy').count(),
        'sell_trades': trades.filter(side='sell').count(),
        'total_volume': stats['total_volume'] or 0,
        'avg_price': stats['avg_price'] or Decimal('0'),
        'realized_pnl': calculate_realized_pnl(portfolio)
    }
