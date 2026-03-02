"""
Custom tools for DeepAgents integration.
These tools wrap existing services and make them available to AI agents.
"""
from typing import List, Dict, Any, Literal, Optional
from decimal import Decimal
from datetime import datetime, timedelta
import asyncio

from langchain.tools import tool
from django.utils import timezone

# Import existing services
from apps.market_data.providers.massive import MassiveProvider
from apps.market_data.providers.alpha_vantage import AlphaVantageProvider
from apps.market_data.indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_sma,
    calculate_ema
)
from apps.market_data.analysis import detect_trend, detect_double_top, detect_double_bottom
from django.conf import settings
from apps.strategies.services import (
    evaluate_entry_conditions,
    evaluate_exit_conditions,
    generate_signals
)
from apps.orders.services import (
    calculate_position_size,
    validate_order,
    check_buying_power
)
from apps.portfolios.services import (
    calculate_portfolio_equity,
    calculate_position_pnl
)
from apps.portfolios.analytics import (
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_sortino_ratio,
    calculate_cagr
)
from apps.orders.models import Order
from apps.portfolios.models import Portfolio, Position
from apps.strategies.models import Strategy


# ============================================================================
# MARKET DATA TOOLS
# ============================================================================

@tool
def get_stock_quote(symbol: str) -> Dict[str, Any]:
    """
    Get real-time stock quote for a given symbol.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT')

    Returns:
        Dictionary with price, volume, and other quote data
    """
    try:
        provider = MassiveProvider()
        quote = provider.get_quote(symbol)
        return {
            "success": True,
            "symbol": symbol,
            "data": quote
        }
    except Exception as e:
        return {
            "success": False,
            "symbol": symbol,
            "error": str(e)
        }


@tool
def get_historical_prices(symbol: str, days: int = 30) -> Dict[str, Any]:
    """
    Get historical price data for a stock.

    Args:
        symbol: Stock ticker symbol
        days: Number of days of historical data (default: 30)

    Returns:
        Dictionary with historical OHLCV data
    """
    try:
        provider = MassiveProvider()
        data = provider.get_historical_data(symbol, days=days)
        return {
            "success": True,
            "symbol": symbol,
            "days": days,
            "data": data
        }
    except Exception as e:
        return {
            "success": False,
            "symbol": symbol,
            "error": str(e)
        }


@tool
def calculate_technical_indicators(
    symbol: str,
    indicators: List[str],
    period: int = 14
) -> Dict[str, Any]:
    """
    Calculate technical indicators for a stock.

    Args:
        symbol: Stock ticker symbol
        indicators: List of indicators to calculate (rsi, macd, sma, ema, bollinger_bands)
        period: Period for calculations (default: 14)

    Returns:
        Dictionary with calculated indicator values
    """
    try:
        # Get historical data
        provider = MassiveProvider()
        historical_data = provider.get_historical_data(symbol, days=max(period * 2, 50))

        if not historical_data:
            return {
                "success": False,
                "symbol": symbol,
                "error": "No historical data available"
            }

        # Extract closing prices
        prices = [float(d['close']) for d in historical_data]

        results = {}

        for indicator in indicators:
            if indicator.lower() == 'rsi':
                results['rsi'] = calculate_rsi(prices, period=period)
            elif indicator.lower() == 'macd':
                results['macd'] = calculate_macd(prices)
            elif indicator.lower() == 'sma':
                results['sma'] = calculate_sma(prices, period=period)
            elif indicator.lower() == 'ema':
                results['ema'] = calculate_ema(prices, period=period)
            elif indicator.lower() == 'bollinger_bands':
                results['bollinger_bands'] = calculate_bollinger_bands(prices, period=period)

        return {
            "success": True,
            "symbol": symbol,
            "indicators": results
        }
    except Exception as e:
        return {
            "success": False,
            "symbol": symbol,
            "error": str(e)
        }


@tool
def get_market_news(
    symbol: str,
    limit: int = 10,
    days_back: int = 7
) -> Dict[str, Any]:
    """
    Get recent market news and sentiment for a stock.

    Uses Alpha Vantage News Sentiment API to fetch real-time news articles
    with AI-powered sentiment analysis.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL')
        limit: Number of news articles to fetch (default: 10, max: 50)
        days_back: Number of days to look back (default: 7)

    Returns:
        Dictionary with news articles and sentiment scores

    Sentiment interpretation:
        - Bearish: Score <= -0.35
        - Somewhat Bearish: -0.35 < Score <= -0.15
        - Neutral: -0.15 < Score < 0.15
        - Somewhat Bullish: 0.15 <= Score < 0.35
        - Bullish: Score >= 0.35
    """
    try:
        # Initialize Alpha Vantage provider
        api_key = getattr(settings, 'ALPHA_VANTAGE_API_KEY', None)
        if not api_key:
            return {
                "success": False,
                "symbol": symbol,
                "error": "Alpha Vantage API key not configured"
            }

        provider = AlphaVantageProvider(api_key=api_key)

        # Calculate time range
        time_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%dT%H%M")

        # Fetch news sentiment
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If in async context, use sync wrapper
            import nest_asyncio
            nest_asyncio.apply()
            news_data = loop.run_until_complete(
                provider.get_news_sentiment(
                    tickers=[symbol],
                    limit=limit,
                    time_from=time_from,
                    sort="LATEST"
                )
            )
        else:
            news_data = asyncio.run(
                provider.get_news_sentiment(
                    tickers=[symbol],
                    limit=limit,
                    time_from=time_from,
                    sort="LATEST"
                )
            )

        # Calculate aggregate sentiment
        feed = news_data.get('feed', [])
        if feed:
            sentiment_scores = []
            for article in feed:
                # Get ticker-specific sentiment if available
                ticker_sentiments = article.get('ticker_sentiment', [])
                for ts in ticker_sentiments:
                    if ts.get('ticker') == symbol:
                        sentiment_scores.append(ts.get('sentiment_score', 0))
                        break
                else:
                    # Use overall sentiment if ticker-specific not found
                    sentiment_scores.append(article.get('overall_sentiment_score', 0))

            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
            sentiment_label = provider.interpret_sentiment_score(avg_sentiment)
        else:
            avg_sentiment = 0
            sentiment_label = "Neutral"

        # Format articles for agent consumption
        formatted_articles = []
        for article in feed[:limit]:
            # Get ticker-specific sentiment
            ticker_sentiment = None
            for ts in article.get('ticker_sentiment', []):
                if ts.get('ticker') == symbol:
                    ticker_sentiment = ts
                    break

            formatted_articles.append({
                "title": article.get('title'),
                "summary": article.get('summary'),
                "source": article.get('source'),
                "published": article.get('time_published').isoformat() if isinstance(article.get('time_published'), datetime) else str(article.get('time_published')),
                "url": article.get('url'),
                "sentiment_score": ticker_sentiment.get('sentiment_score') if ticker_sentiment else article.get('overall_sentiment_score'),
                "sentiment_label": ticker_sentiment.get('sentiment_label') if ticker_sentiment else article.get('overall_sentiment_label'),
                "relevance_score": ticker_sentiment.get('relevance_score') if ticker_sentiment else 0
            })

        return {
            "success": True,
            "symbol": symbol,
            "articles_count": len(formatted_articles),
            "average_sentiment": round(avg_sentiment, 3),
            "sentiment_label": sentiment_label,
            "articles": formatted_articles,
            "news_summary": f"Found {len(formatted_articles)} recent articles for {symbol}. Average sentiment: {sentiment_label} ({round(avg_sentiment, 3)})"
        }

    except Exception as e:
        return {
            "success": False,
            "symbol": symbol,
            "error": str(e)
        }


@tool
def detect_chart_patterns(symbol: str, pattern_type: str = "all") -> Dict[str, Any]:
    """
    Detect chart patterns in stock price data.

    Args:
        symbol: Stock ticker symbol
        pattern_type: Type of pattern to detect (trend, double_top, double_bottom, all)

    Returns:
        Dictionary with detected patterns
    """
    try:
        # Get historical data
        provider = MassiveProvider()
        historical_data = provider.get_historical_data(symbol, days=60)

        if not historical_data:
            return {
                "success": False,
                "symbol": symbol,
                "error": "No historical data available"
            }

        prices = [float(d['close']) for d in historical_data]

        patterns = {}

        if pattern_type in ['trend', 'all']:
            patterns['trend'] = detect_trend(prices)

        if pattern_type in ['double_top', 'all']:
            patterns['double_top'] = detect_double_top(prices)

        if pattern_type in ['double_bottom', 'all']:
            patterns['double_bottom'] = detect_double_bottom(prices)

        return {
            "success": True,
            "symbol": symbol,
            "patterns": patterns
        }
    except Exception as e:
        return {
            "success": False,
            "symbol": symbol,
            "error": str(e)
        }


# ============================================================================
# STRATEGY TOOLS
# ============================================================================

@tool
def evaluate_trading_signal(
    symbol: str,
    strategy_config: Dict[str, Any],
    current_position: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evaluate trading signals based on strategy configuration.

    Args:
        symbol: Stock ticker symbol
        strategy_config: Strategy configuration with entry/exit conditions
        current_position: Optional current position data

    Returns:
        Dictionary with trading signal (buy, sell, hold) and reasoning
    """
    try:
        # Get market data
        provider = MassiveProvider()
        quote = provider.get_quote(symbol)
        historical_data = provider.get_historical_data(symbol, days=50)

        # Calculate indicators
        prices = [float(d['close']) for d in historical_data]

        market_data = {
            'price': float(quote.get('price', 0)),
            'rsi': calculate_rsi(prices, period=14),
            'macd': calculate_macd(prices).get('macd', 0),
            'sma_20': calculate_sma(prices, period=20),
            'ema_12': calculate_ema(prices, period=12)
        }

        # Generate signal
        has_position = current_position is not None and current_position.get('quantity', 0) > 0
        signal = generate_signals(strategy_config, market_data, has_position=has_position)

        return {
            "success": True,
            "symbol": symbol,
            "signal": signal,
            "market_data": market_data
        }
    except Exception as e:
        return {
            "success": False,
            "symbol": symbol,
            "error": str(e)
        }


@tool
def check_entry_conditions(
    symbol: str,
    conditions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Check if entry conditions are met for a stock.

    Args:
        symbol: Stock ticker symbol
        conditions: List of entry condition dictionaries

    Returns:
        Dictionary indicating if entry conditions are met
    """
    try:
        # Get market data
        provider = MassiveProvider()
        historical_data = provider.get_historical_data(symbol, days=50)
        prices = [float(d['close']) for d in historical_data]

        market_data = {
            'rsi': calculate_rsi(prices, period=14),
            'macd': calculate_macd(prices).get('macd', 0),
            'sma_20': calculate_sma(prices, period=20),
            'ema_12': calculate_ema(prices, period=12)
        }

        entry_met = evaluate_entry_conditions(conditions, market_data)

        return {
            "success": True,
            "symbol": symbol,
            "entry_conditions_met": entry_met,
            "market_data": market_data
        }
    except Exception as e:
        return {
            "success": False,
            "symbol": symbol,
            "error": str(e)
        }


@tool
def check_exit_conditions(
    symbol: str,
    conditions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Check if exit conditions are met for a stock position.

    Args:
        symbol: Stock ticker symbol
        conditions: List of exit condition dictionaries

    Returns:
        Dictionary indicating if exit conditions are met
    """
    try:
        # Get market data
        provider = MassiveProvider()
        historical_data = provider.get_historical_data(symbol, days=50)
        prices = [float(d['close']) for d in historical_data]

        market_data = {
            'rsi': calculate_rsi(prices, period=14),
            'macd': calculate_macd(prices).get('macd', 0),
            'sma_20': calculate_sma(prices, period=20),
            'ema_12': calculate_ema(prices, period=12)
        }

        exit_met = evaluate_exit_conditions(conditions, market_data)

        return {
            "success": True,
            "symbol": symbol,
            "exit_conditions_met": exit_met,
            "market_data": market_data
        }
    except Exception as e:
        return {
            "success": False,
            "symbol": symbol,
            "error": str(e)
        }


# ============================================================================
# PORTFOLIO TOOLS
# ============================================================================

@tool
def get_portfolio_status(portfolio_id: str) -> Dict[str, Any]:
    """
    Get current portfolio status including cash, positions, and equity.

    Args:
        portfolio_id: Portfolio UUID

    Returns:
        Dictionary with portfolio status
    """
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)

        # Get positions
        positions = Position.objects.filter(portfolio=portfolio)
        positions_data = [
            {
                'symbol': pos.symbol,
                'quantity': pos.quantity,
                'avg_entry_price': float(pos.avg_entry_price),
                'current_price': float(pos.current_price) if pos.current_price else None,
                'unrealized_pnl': float(pos.unrealized_pnl) if pos.unrealized_pnl else None,
                'unrealized_pnl_pct': float(pos.unrealized_pnl_pct) if pos.unrealized_pnl_pct else None,
                'market_value': float(pos.market_value) if pos.market_value else None
            }
            for pos in positions
        ]

        # Calculate total equity
        equity = calculate_portfolio_equity(portfolio)

        return {
            "success": True,
            "portfolio_id": str(portfolio.id),
            "cash": float(portfolio.cash),
            "equity": float(equity),
            "positions": positions_data,
            "position_count": len(positions_data)
        }
    except Portfolio.DoesNotExist:
        return {
            "success": False,
            "portfolio_id": portfolio_id,
            "error": "Portfolio not found"
        }
    except Exception as e:
        return {
            "success": False,
            "portfolio_id": portfolio_id,
            "error": str(e)
        }


@tool
def calculate_portfolio_metrics(portfolio_id: str) -> Dict[str, Any]:
    """
    Calculate portfolio performance metrics (Sharpe, max drawdown, etc.).

    Args:
        portfolio_id: Portfolio UUID

    Returns:
        Dictionary with performance metrics
    """
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)

        metrics = {
            'sharpe_ratio': float(calculate_sharpe_ratio(portfolio)) if calculate_sharpe_ratio(portfolio) else None,
            'max_drawdown': float(calculate_max_drawdown(portfolio)) if calculate_max_drawdown(portfolio) else None,
            'sortino_ratio': float(calculate_sortino_ratio(portfolio)) if calculate_sortino_ratio(portfolio) else None,
            'cagr': float(calculate_cagr(portfolio)) if calculate_cagr(portfolio) else None
        }

        return {
            "success": True,
            "portfolio_id": str(portfolio.id),
            "metrics": metrics
        }
    except Portfolio.DoesNotExist:
        return {
            "success": False,
            "portfolio_id": portfolio_id,
            "error": "Portfolio not found"
        }
    except Exception as e:
        return {
            "success": False,
            "portfolio_id": portfolio_id,
            "error": str(e)
        }


@tool
def check_portfolio_buying_power(portfolio_id: str, estimated_cost: float) -> Dict[str, Any]:
    """
    Check if portfolio has sufficient buying power for a trade.

    Args:
        portfolio_id: Portfolio UUID
        estimated_cost: Estimated cost of the trade

    Returns:
        Dictionary with buying power check result
    """
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)

        result = check_buying_power(portfolio, Decimal(str(estimated_cost)))

        return {
            "success": True,
            "portfolio_id": str(portfolio.id),
            "has_buying_power": result['has_buying_power'],
            "available_cash": float(result['available_cash']),
            "required_cash": estimated_cost,
            "message": result.get('message', 'Sufficient buying power')
        }
    except Portfolio.DoesNotExist:
        return {
            "success": False,
            "portfolio_id": portfolio_id,
            "error": "Portfolio not found"
        }
    except Exception as e:
        return {
            "success": False,
            "portfolio_id": portfolio_id,
            "error": str(e)
        }


@tool
def calculate_optimal_position_size(
    portfolio_id: str,
    symbol: str,
    price: float,
    sizing_type: Literal["fixed", "percentage", "shares"] = "percentage",
    size_value: float = 10.0
) -> Dict[str, Any]:
    """
    Calculate optimal position size based on portfolio and risk parameters.

    Args:
        portfolio_id: Portfolio UUID
        symbol: Stock ticker symbol
        price: Current stock price
        sizing_type: Type of position sizing (fixed, percentage, shares)
        size_value: Size value based on sizing_type

    Returns:
        Dictionary with recommended position size
    """
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)

        quantity = calculate_position_size(
            portfolio,
            Decimal(str(price)),
            sizing_type=sizing_type,
            size_value=Decimal(str(size_value))
        )

        estimated_cost = quantity * Decimal(str(price))

        return {
            "success": True,
            "portfolio_id": str(portfolio.id),
            "symbol": symbol,
            "recommended_quantity": quantity,
            "price": price,
            "estimated_cost": float(estimated_cost),
            "sizing_type": sizing_type,
            "size_value": size_value
        }
    except Portfolio.DoesNotExist:
        return {
            "success": False,
            "portfolio_id": portfolio_id,
            "error": "Portfolio not found"
        }
    except Exception as e:
        return {
            "success": False,
            "portfolio_id": portfolio_id,
            "error": str(e)
        }


# ============================================================================
# ORDER TOOLS
# ============================================================================

@tool
def create_order_recommendation(
    portfolio_id: str,
    symbol: str,
    side: Literal["buy", "sell"],
    quantity: int,
    order_type: Literal["market", "limit"] = "market",
    limit_price: Optional[float] = None
) -> Dict[str, Any]:
    """
    Create an order recommendation (does not execute, only prepares).

    Args:
        portfolio_id: Portfolio UUID
        symbol: Stock ticker symbol
        side: Order side (buy or sell)
        quantity: Number of shares
        order_type: Order type (market or limit)
        limit_price: Limit price (required for limit orders)

    Returns:
        Dictionary with order recommendation and validation
    """
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)

        # Get current price
        provider = MassiveProvider()
        quote = provider.get_quote(symbol)
        current_price = float(quote.get('price', 0))

        # Validate order parameters
        if order_type == 'limit' and limit_price is None:
            return {
                "success": False,
                "error": "Limit price required for limit orders"
            }

        execution_price = limit_price if order_type == 'limit' else current_price
        estimated_cost = quantity * execution_price

        # Check buying power for buy orders
        if side == 'buy':
            buying_power_check = check_buying_power(portfolio, Decimal(str(estimated_cost)))
            if not buying_power_check['has_buying_power']:
                return {
                    "success": False,
                    "error": "Insufficient buying power",
                    "details": buying_power_check
                }

        # Check position for sell orders
        if side == 'sell':
            try:
                position = Position.objects.get(portfolio=portfolio, symbol=symbol)
                if position.quantity < quantity:
                    return {
                        "success": False,
                        "error": f"Insufficient shares. Available: {position.quantity}, Requested: {quantity}"
                    }
            except Position.DoesNotExist:
                return {
                    "success": False,
                    "error": f"No position found for {symbol}"
                }

        return {
            "success": True,
            "recommendation": {
                "portfolio_id": str(portfolio.id),
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "order_type": order_type,
                "limit_price": limit_price,
                "current_price": current_price,
                "estimated_cost": estimated_cost,
                "validated": True
            }
        }
    except Portfolio.DoesNotExist:
        return {
            "success": False,
            "portfolio_id": portfolio_id,
            "error": "Portfolio not found"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# RISK MANAGEMENT TOOLS
# ============================================================================

@tool
def calculate_risk_metrics(
    portfolio_id: str,
    symbol: str,
    quantity: int,
    entry_price: float
) -> Dict[str, Any]:
    """
    Calculate risk metrics for a potential trade.

    Args:
        portfolio_id: Portfolio UUID
        symbol: Stock ticker symbol
        quantity: Number of shares
        entry_price: Entry price for the position

    Returns:
        Dictionary with risk metrics
    """
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)

        # Calculate position value
        position_value = quantity * entry_price

        # Calculate portfolio equity
        equity = calculate_portfolio_equity(portfolio)

        # Calculate position as percentage of portfolio
        position_pct = (position_value / float(equity)) * 100 if equity > 0 else 0

        # Get historical volatility
        provider = MassiveProvider()
        historical_data = provider.get_historical_data(symbol, days=30)
        prices = [float(d['close']) for d in historical_data]

        # Calculate volatility (simplified)
        if len(prices) > 1:
            returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
            volatility = (sum([r**2 for r in returns]) / len(returns)) ** 0.5
        else:
            volatility = 0

        return {
            "success": True,
            "portfolio_id": str(portfolio.id),
            "symbol": symbol,
            "risk_metrics": {
                "position_value": position_value,
                "portfolio_equity": float(equity),
                "position_percentage": round(position_pct, 2),
                "volatility": round(volatility * 100, 2),
                "risk_level": "high" if position_pct > 20 else "medium" if position_pct > 10 else "low"
            }
        }
    except Portfolio.DoesNotExist:
        return {
            "success": False,
            "portfolio_id": portfolio_id,
            "error": "Portfolio not found"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# TOOL COLLECTION
# ============================================================================

# All available tools for agents
TRADING_TOOLS = [
    # Market Data
    get_stock_quote,
    get_historical_prices,
    calculate_technical_indicators,
    get_market_news,  # NEW: News and sentiment analysis
    detect_chart_patterns,

    # Strategy
    evaluate_trading_signal,
    check_entry_conditions,
    check_exit_conditions,

    # Portfolio
    get_portfolio_status,
    calculate_portfolio_metrics,
    check_portfolio_buying_power,
    calculate_optimal_position_size,

    # Orders
    create_order_recommendation,

    # Risk Management
    calculate_risk_metrics,
]
