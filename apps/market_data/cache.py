"""
Redis caching utilities for market data.

This module provides caching functions to reduce API calls to market data providers
and improve response times.
"""
from django.core.cache import cache
from django.conf import settings
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from decimal import Decimal
import json
import logging

logger = logging.getLogger(__name__)


class MarketDataCache:
    """
    Cache manager for market data.

    Uses Redis to cache:
    - Latest quotes (5-minute TTL)
    - Historical bars (1-hour TTL)
    - Calculated indicators (15-minute TTL)
    """

    # Cache key prefixes
    QUOTE_PREFIX = "market:quote:"
    BARS_PREFIX = "market:bars:"
    INDICATOR_PREFIX = "market:indicator:"
    SEARCH_PREFIX = "market:search:"

    # Cache TTLs (in seconds)
    QUOTE_TTL = 300  # 5 minutes
    BARS_TTL = 3600  # 1 hour
    INDICATOR_TTL = 900  # 15 minutes
    SEARCH_TTL = 86400  # 24 hours

    @classmethod
    def get_quote_key(cls, symbol: str) -> str:
        """
        Get cache key for quote.

        Args:
            symbol: Stock symbol

        Returns:
            Cache key string
        """
        return f"{cls.QUOTE_PREFIX}{symbol.upper()}"

    @classmethod
    def get_bars_key(cls, symbol: str, start_date: str, end_date: str, timeframe: str) -> str:
        """
        Get cache key for historical bars.

        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            timeframe: Timeframe string

        Returns:
            Cache key string
        """
        return f"{cls.BARS_PREFIX}{symbol.upper()}:{start_date}:{end_date}:{timeframe}"

    @classmethod
    def get_indicator_key(cls, symbol: str, indicator_type: str, period: int = None) -> str:
        """
        Get cache key for indicator.

        Args:
            symbol: Stock symbol
            indicator_type: Indicator type (rsi, macd, etc.)
            period: Period parameter (optional)

        Returns:
            Cache key string
        """
        period_str = f":{period}" if period else ""
        return f"{cls.INDICATOR_PREFIX}{symbol.upper()}:{indicator_type}{period_str}"

    @classmethod
    def get_search_key(cls, query: str) -> str:
        """
        Get cache key for symbol search.

        Args:
            query: Search query

        Returns:
            Cache key string
        """
        return f"{cls.SEARCH_PREFIX}{query.lower()}"

    @classmethod
    def get_quote(cls, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get cached quote for symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Quote dictionary or None if not cached
        """
        key = cls.get_quote_key(symbol)
        cached_data = cache.get(key)

        if cached_data:
            logger.debug(f"Cache HIT for quote: {symbol}")
            return cls._deserialize_quote(cached_data)

        logger.debug(f"Cache MISS for quote: {symbol}")
        return None

    @classmethod
    def set_quote(cls, symbol: str, quote_data: Dict[str, Any], ttl: int = None) -> bool:
        """
        Cache quote for symbol.

        Args:
            symbol: Stock symbol
            quote_data: Quote dictionary
            ttl: Time-to-live in seconds (default: QUOTE_TTL)

        Returns:
            True if cached successfully
        """
        key = cls.get_quote_key(symbol)
        ttl = ttl or cls.QUOTE_TTL

        try:
            serialized = cls._serialize_quote(quote_data)
            cache.set(key, serialized, ttl)
            logger.debug(f"Cached quote for {symbol} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Error caching quote for {symbol}: {e}")
            return False

    @classmethod
    def get_bars(cls, symbol: str, start_date: str, end_date: str, timeframe: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached historical bars.

        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            timeframe: Timeframe

        Returns:
            List of bar dictionaries or None
        """
        key = cls.get_bars_key(symbol, start_date, end_date, timeframe)
        cached_data = cache.get(key)

        if cached_data:
            logger.debug(f"Cache HIT for bars: {symbol} ({start_date} to {end_date})")
            return cls._deserialize_bars(cached_data)

        logger.debug(f"Cache MISS for bars: {symbol}")
        return None

    @classmethod
    def set_bars(
        cls,
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe: str,
        bars_data: List[Dict[str, Any]],
        ttl: int = None
    ) -> bool:
        """
        Cache historical bars.

        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            timeframe: Timeframe
            bars_data: List of bar dictionaries
            ttl: Time-to-live in seconds

        Returns:
            True if cached successfully
        """
        key = cls.get_bars_key(symbol, start_date, end_date, timeframe)
        ttl = ttl or cls.BARS_TTL

        try:
            serialized = cls._serialize_bars(bars_data)
            cache.set(key, serialized, ttl)
            logger.debug(f"Cached {len(bars_data)} bars for {symbol} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Error caching bars for {symbol}: {e}")
            return False

    @classmethod
    def get_indicator(cls, symbol: str, indicator_type: str, period: int = None) -> Optional[Any]:
        """
        Get cached indicator value.

        Args:
            symbol: Stock symbol
            indicator_type: Indicator type
            period: Period parameter

        Returns:
            Indicator value or None
        """
        key = cls.get_indicator_key(symbol, indicator_type, period)
        cached_data = cache.get(key)

        if cached_data:
            logger.debug(f"Cache HIT for indicator: {symbol} {indicator_type}")
            return cached_data

        logger.debug(f"Cache MISS for indicator: {symbol} {indicator_type}")
        return None

    @classmethod
    def set_indicator(
        cls,
        symbol: str,
        indicator_type: str,
        value: Any,
        period: int = None,
        ttl: int = None
    ) -> bool:
        """
        Cache indicator value.

        Args:
            symbol: Stock symbol
            indicator_type: Indicator type
            value: Indicator value
            period: Period parameter
            ttl: Time-to-live in seconds

        Returns:
            True if cached successfully
        """
        key = cls.get_indicator_key(symbol, indicator_type, period)
        ttl = ttl or cls.INDICATOR_TTL

        try:
            cache.set(key, value, ttl)
            logger.debug(f"Cached indicator {indicator_type} for {symbol} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Error caching indicator for {symbol}: {e}")
            return False

    @classmethod
    def invalidate_symbol(cls, symbol: str) -> int:
        """
        Invalidate all cached data for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Number of keys deleted
        """
        symbol_upper = symbol.upper()
        patterns = [
            f"{cls.QUOTE_PREFIX}{symbol_upper}",
            f"{cls.BARS_PREFIX}{symbol_upper}:*",
            f"{cls.INDICATOR_PREFIX}{symbol_upper}:*",
        ]

        deleted_count = 0
        for pattern in patterns:
            try:
                # Delete by pattern (if Redis supports it)
                cache.delete_pattern(pattern)
                deleted_count += 1
            except AttributeError:
                # Fallback: just delete the quote key
                cache.delete(f"{cls.QUOTE_PREFIX}{symbol_upper}")
                deleted_count += 1
                break

        logger.info(f"Invalidated cache for {symbol} ({deleted_count} patterns)")
        return deleted_count

    @classmethod
    def get_search_results(cls, query: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached search results.

        Args:
            query: Search query

        Returns:
            List of search results or None
        """
        key = cls.get_search_key(query)
        cached_data = cache.get(key)

        if cached_data:
            logger.debug(f"Cache HIT for search: {query}")
            return cached_data

        logger.debug(f"Cache MISS for search: {query}")
        return None

    @classmethod
    def set_search_results(cls, query: str, results: List[Dict[str, Any]], ttl: int = None) -> bool:
        """
        Cache search results.

        Args:
            query: Search query
            results: List of search results
            ttl: Time-to-live in seconds

        Returns:
            True if cached successfully
        """
        key = cls.get_search_key(query)
        ttl = ttl or cls.SEARCH_TTL

        try:
            cache.set(key, results, ttl)
            logger.debug(f"Cached search results for '{query}' (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Error caching search results: {e}")
            return False

    @classmethod
    def _serialize_quote(cls, quote_data: Dict[str, Any]) -> str:
        """
        Serialize quote data for caching.

        Converts Decimal and datetime to JSON-serializable formats.
        """
        serializable = {}
        for key, value in quote_data.items():
            if isinstance(value, Decimal):
                serializable[key] = str(value)
            elif isinstance(value, datetime):
                serializable[key] = value.isoformat()
            else:
                serializable[key] = value

        return json.dumps(serializable)

    @classmethod
    def _deserialize_quote(cls, cached_data: str) -> Dict[str, Any]:
        """Deserialize quote data from cache."""
        data = json.loads(cached_data)

        # Convert string decimals back to Decimal
        for key in ['open', 'high', 'low', 'close']:
            if key in data and data[key]:
                data[key] = Decimal(data[key])

        # Convert ISO timestamp back to datetime
        if 'timestamp' in data and data['timestamp']:
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])

        return data

    @classmethod
    def _serialize_bars(cls, bars_data: List[Dict[str, Any]]) -> str:
        """Serialize bars data for caching."""
        serializable = []
        for bar in bars_data:
            serialized_bar = {}
            for key, value in bar.items():
                if isinstance(value, Decimal):
                    serialized_bar[key] = str(value)
                elif isinstance(value, datetime):
                    serialized_bar[key] = value.isoformat()
                else:
                    serialized_bar[key] = value
            serializable.append(serialized_bar)

        return json.dumps(serializable)

    @classmethod
    def _deserialize_bars(cls, cached_data: str) -> List[Dict[str, Any]]:
        """Deserialize bars data from cache."""
        data = json.loads(cached_data)

        deserialized = []
        for bar in data:
            # Convert string decimals back to Decimal
            for key in ['open', 'high', 'low', 'close']:
                if key in bar and bar[key]:
                    bar[key] = Decimal(bar[key])

            # Convert ISO timestamp back to datetime
            if 'timestamp' in bar and bar['timestamp']:
                bar['timestamp'] = datetime.fromisoformat(bar['timestamp'])

            deserialized.append(bar)

        return deserialized

    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        try:
            # Try to get Redis info (if using django-redis)
            from django_redis import get_redis_connection
            redis_conn = get_redis_connection("default")
            info = redis_conn.info()

            return {
                "connected": True,
                "used_memory": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "total_commands_processed": info.get("total_commands_processed"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"connected": False, "error": str(e)}


def cache_quote(func):
    """
    Decorator to cache quote fetching functions.

    Usage:
        @cache_quote
        async def get_quote(symbol):
            # fetch quote
            return quote_data
    """
    async def wrapper(symbol: str, *args, **kwargs):
        # Check cache first
        cached = MarketDataCache.get_quote(symbol)
        if cached:
            return cached

        # Cache miss - fetch from provider
        result = await func(symbol, *args, **kwargs)

        # Cache the result
        if result:
            MarketDataCache.set_quote(symbol, result)

        return result

    return wrapper


def cache_bars(func):
    """
    Decorator to cache historical bars fetching.

    Usage:
        @cache_bars
        async def get_historical_bars(symbol, start_date, end_date, timeframe):
            # fetch bars
            return bars_data
    """
    async def wrapper(symbol: str, start_date, end_date, timeframe, *args, **kwargs):
        # Convert dates to strings for cache key
        start_str = start_date.strftime('%Y-%m-%d') if hasattr(start_date, 'strftime') else str(start_date)
        end_str = end_date.strftime('%Y-%m-%d') if hasattr(end_date, 'strftime') else str(end_date)

        # Check cache first
        cached = MarketDataCache.get_bars(symbol, start_str, end_str, timeframe)
        if cached:
            return cached

        # Cache miss - fetch from provider
        result = await func(symbol, start_date, end_date, timeframe, *args, **kwargs)

        # Cache the result
        if result:
            MarketDataCache.set_bars(symbol, start_str, end_str, timeframe, result)

        return result

    return wrapper
