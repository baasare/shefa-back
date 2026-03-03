"""
Advanced portfolio analytics and reporting.
"""
import statistics
from datetime import timedelta
from django.utils import timezone
from typing import Dict, Any, List
from django.db.models import Sum, Avg

from apps.orders.models import Trade
from apps.portfolios.models import Portfolio, PortfolioSnapshot


def calculate_advanced_metrics(portfolio: Portfolio, days: int = 30) -> Dict[str, Any]:
    """
    Calculate advanced portfolio metrics.

    Args:
        portfolio: Portfolio instance
        days: Period for analysis

    Returns:
        Dictionary with advanced metrics
    """
    start_date = timezone.now() - timedelta(days=days)

    # Get trades for period
    trades = Trade.objects.filter(
        portfolio=portfolio,
        executed_at__gte=start_date
    )

    # Get snapshots
    snapshots = PortfolioSnapshot.objects.filter(
        portfolio=portfolio,
        timestamp__gte=start_date
    ).order_by('timestamp')

    metrics = {
        'trade_metrics': _calculate_trade_metrics(trades),
        'risk_metrics': _calculate_risk_metrics(snapshots),
        'return_metrics': _calculate_return_metrics(snapshots),
        'efficiency_metrics': _calculate_efficiency_metrics(trades, snapshots)
    }

    return metrics


def _calculate_trade_metrics(trades) -> Dict[str, Any]:
    """Calculate trading activity metrics."""
    if not trades.exists():
        return {
            'total_trades': 0,
            'avg_trade_size': 0,
            'largest_win': 0,
            'largest_loss': 0
        }

    buy_trades = trades.filter(side='buy')
    sell_trades = trades.filter(side='sell')

    return {
        'total_trades': trades.count(),
        'buy_trades': buy_trades.count(),
        'sell_trades': sell_trades.count(),
        'avg_trade_size': float(trades.aggregate(Avg('quantity'))['quantity__avg'] or 0),
        'total_volume': float(trades.aggregate(Sum('quantity'))['quantity__sum'] or 0)
    }


def _calculate_risk_metrics(snapshots) -> Dict[str, Any]:
    """Calculate risk metrics."""
    if snapshots.count() < 2:
        return {
            'volatility': 0,
            'max_drawdown': 0,
            'var_95': 0
        }

    values = [float(s.total_value) for s in snapshots]

    # Daily returns
    returns = []
    for i in range(1, len(values)):
        if values[i-1] > 0:
            ret = (values[i] - values[i-1]) / values[i-1]
            returns.append(ret)

    # Volatility (std dev of returns)
    volatility = statistics.stdev(returns) * 100 if len(returns) > 1 else 0

    # Max drawdown
    peak = values[0]
    max_dd = 0
    for value in values:
        if value > peak:
            peak = value
        dd = ((peak - value) / peak) * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # VaR (95th percentile of losses)
    losses = [r for r in returns if r < 0]
    var_95 = abs(statistics.quantiles(losses, n=20)[1]) * 100 if len(losses) > 20 else 0

    return {
        'volatility': volatility,
        'max_drawdown': max_dd,
        'var_95': var_95,
        'downside_deviation': _calculate_downside_deviation(returns)
    }


def _calculate_return_metrics(snapshots) -> Dict[str, Any]:
    """Calculate return metrics."""
    if snapshots.count() < 2:
        return {'total_return': 0, 'cagr': 0}

    first_value = float(snapshots.first().total_value)
    last_value = float(snapshots.last().total_value)

    total_return = ((last_value - first_value) / first_value) * 100 if first_value > 0 else 0

    # CAGR
    days = (snapshots.last().timestamp - snapshots.first().timestamp).days
    years = days / 365.25
    cagr = (((last_value / first_value) ** (1 / years)) - 1) * 100 if years > 0 and first_value > 0 else 0

    return {
        'total_return': total_return,
        'cagr': cagr
    }


def _calculate_efficiency_metrics(trades, snapshots) -> Dict[str, Any]:
    """Calculate efficiency metrics."""
    return {
        'turnover_ratio': trades.count() / max(1, snapshots.count()),
        'trades_per_day': trades.count() / max(1, (timezone.now() - trades.first().executed_at).days) if trades.exists() else 0
    }


def _calculate_downside_deviation(returns: List[float]) -> float:
    """Calculate downside deviation (only negative returns)."""
    negative_returns = [r for r in returns if r < 0]
    return statistics.stdev(negative_returns) * 100 if len(negative_returns) > 1 else 0


def calculate_max_drawdown(portfolio: Portfolio, days: int = 90) -> float:
    """
    Calculate maximum drawdown for portfolio.

    Args:
        portfolio: Portfolio instance
        days: Period for calculation

    Returns:
        Maximum drawdown percentage
    """
    start_date = timezone.now() - timedelta(days=days)

    snapshots = PortfolioSnapshot.objects.filter(
        portfolio=portfolio,
        timestamp__gte=start_date
    ).order_by('timestamp')

    if snapshots.count() < 2:
        return 0.0

    values = [float(s.total_value) for s in snapshots]

    peak = values[0]
    max_dd = 0.0

    for value in values:
        if value > peak:
            peak = value
        dd = ((peak - value) / peak) * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    return max_dd


def calculate_sortino_ratio(portfolio: Portfolio, days: int = 30, risk_free_rate: float = 0.04) -> float:
    """
    Calculate Sortino ratio for portfolio (similar to Sharpe but only uses downside deviation).

    Args:
        portfolio: Portfolio instance
        days: Period for calculation
        risk_free_rate: Annual risk-free rate (default 4%)

    Returns:
        Sortino ratio or 0 if insufficient data
    """
    start_date = timezone.now() - timedelta(days=days)

    snapshots = PortfolioSnapshot.objects.filter(
        portfolio=portfolio,
        timestamp__gte=start_date
    ).order_by('timestamp')

    if snapshots.count() < 2:
        return 0.0

    # Calculate daily returns
    returns = []
    snapshots_list = list(snapshots)

    for i in range(1, len(snapshots_list)):
        prev_value = float(snapshots_list[i-1].total_value)
        curr_value = float(snapshots_list[i].total_value)

        if prev_value > 0:
            daily_return = (curr_value - prev_value) / prev_value
            returns.append(daily_return)

    if not returns:
        return 0.0

    # Calculate average return and downside deviation
    avg_return = statistics.mean(returns)

    # Only consider negative returns for downside deviation
    negative_returns = [r for r in returns if r < 0]
    if len(negative_returns) < 2:
        return 0.0

    downside_std = statistics.stdev(negative_returns)

    if downside_std == 0:
        return 0.0

    # Annualize (assuming 252 trading days)
    annual_return = avg_return * 252
    annual_downside_std = downside_std * (252 ** 0.5)

    # Calculate Sortino ratio
    sortino = (annual_return - risk_free_rate) / annual_downside_std

    return sortino


def calculate_cagr(portfolio: Portfolio) -> float:
    """
    Calculate Compound Annual Growth Rate (CAGR) for portfolio.

    Args:
        portfolio: Portfolio instance

    Returns:
        CAGR as percentage
    """
    # Get first and last snapshots
    snapshots = PortfolioSnapshot.objects.filter(
        portfolio=portfolio
    ).order_by('timestamp')

    if snapshots.count() < 2:
        return 0.0

    first_snapshot = snapshots.first()
    last_snapshot = snapshots.last()

    start_value = float(first_snapshot.total_value)
    end_value = float(last_snapshot.total_value)

    if start_value <= 0:
        return 0.0

    # Calculate number of years
    days = (last_snapshot.timestamp - first_snapshot.timestamp).days
    years = days / 365.25

    if years <= 0:
        return 0.0

    # Calculate CAGR
    cagr = (((end_value / start_value) ** (1 / years)) - 1) * 100

    return cagr


def generate_trade_journal(portfolio: Portfolio, days: int = 30) -> List[Dict[str, Any]]:
    """
    Generate trade journal with all trades and notes.

    Args:
        portfolio: Portfolio instance
        days: Days to include

    Returns:
        List of trade entries
    """
    start_date = timezone.now() - timedelta(days=days)

    trades = Trade.objects.filter(
        portfolio=portfolio,
        executed_at__gte=start_date
    ).select_related('order').order_by('-executed_at')

    journal = []
    for trade in trades:
        entry = {
            'date': trade.executed_at.isoformat(),
            'symbol': trade.symbol,
            'side': trade.side,
            'quantity': trade.quantity,
            'price': float(trade.price),
            'total': float(trade.price * trade.quantity),
            'strategy': trade.order.strategy_id if trade.order and trade.order.strategy_id else None,
            'notes': trade.order.metadata.get('notes', '') if trade.order and trade.order.metadata else ''
        }
        journal.append(entry)

    return journal
