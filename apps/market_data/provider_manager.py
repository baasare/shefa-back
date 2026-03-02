"""
Market data provider manager with fallback logic.

This module provides intelligent provider selection and automatic fallback
when primary providers fail or hit rate limits.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from django.conf import settings
import logging
import asyncio

from .providers import MassiveProvider, AlphaVantageProvider, MarketDataProvider
from .cache import MarketDataCache

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Base exception for provider errors."""
    pass


class RateLimitError(ProviderError):
    """Raised when API rate limit is exceeded."""
    pass


class DataNotFoundError(ProviderError):
    """Raised when requested data is not found."""
    pass


class ProviderManager:
    """
    Manages multiple market data providers with automatic failover.

    Features:
    - Automatic provider selection based on availability
    - Fallback to secondary provider on failure
    - Rate limit detection and handling
    - Caching integration
    - Provider health tracking
    """

    def __init__(self):
        """Initialize provider manager with configured providers."""
        self.providers = self._initialize_providers()
        self.provider_health = {name: True for name in self.providers.keys()}

    def _initialize_providers(self) -> Dict[str, MarketDataProvider]:
        """
        Initialize all configured providers.

        Returns:
            Dictionary of provider name -> provider instance
        """
        providers = {}

        # Initialize Massive.com provider
        massive_key = getattr(settings, 'MASSIVE_API_KEY', None)
        if massive_key:
            try:
                providers['massive'] = MassiveProvider(massive_key)
                logger.info("Massive.com provider initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Massive.com provider: {e}")

        # Initialize Alpha Vantage provider
        alpha_key = getattr(settings, 'ALPHA_VANTAGE_API_KEY', None)
        if alpha_key:
            try:
                providers['alpha_vantage'] = AlphaVantageProvider(alpha_key)
                logger.info("Alpha Vantage provider initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Alpha Vantage provider: {e}")

        if not providers:
            logger.warning("No market data providers configured!")

        return providers

    def get_provider_priority(self) -> List[str]:
        """
        Get provider priority order.

        Returns:
            List of provider names in priority order
        """
        # Default priority: Massive (fast, good free tier) -> Alpha Vantage (backup)
        priority = []

        if 'massive' in self.providers and self.provider_health.get('massive', True):
            priority.append('massive')

        if 'alpha_vantage' in self.providers and self.provider_health.get('alpha_vantage', True):
            priority.append('alpha_vantage')

        return priority

    def mark_provider_unhealthy(self, provider_name: str, duration_seconds: int = 300):
        """
        Mark a provider as unhealthy for a duration.

        Args:
            provider_name: Name of provider
            duration_seconds: How long to mark as unhealthy (default 5 minutes)
        """
        self.provider_health[provider_name] = False
        logger.warning(f"Marked {provider_name} as unhealthy for {duration_seconds}s")

        # Schedule re-enabling
        async def re_enable():
            await asyncio.sleep(duration_seconds)
            self.provider_health[provider_name] = True
            logger.info(f"Re-enabled {provider_name}")

        asyncio.create_task(re_enable())

    async def get_quote(self, symbol: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get latest quote with automatic provider fallback.

        Args:
            symbol: Stock symbol
            use_cache: Whether to use cached data (default True)

        Returns:
            Quote dictionary or None

        Raises:
            ProviderError: If all providers fail
        """
        # Check cache first
        if use_cache:
            cached = MarketDataCache.get_quote(symbol)
            if cached:
                logger.debug(f"Returning cached quote for {symbol}")
                return cached

        # Try providers in priority order
        priority = self.get_provider_priority()
        errors = []

        for provider_name in priority:
            provider = self.providers[provider_name]

            try:
                logger.debug(f"Fetching quote for {symbol} from {provider_name}")
                quote = await provider.get_quote(symbol)

                if quote:
                    # Cache the result
                    if use_cache:
                        MarketDataCache.set_quote(symbol, quote)

                    logger.info(f"Successfully fetched quote for {symbol} from {provider_name}")
                    return quote

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"{provider_name} failed for {symbol}: {error_msg}")
                errors.append(f"{provider_name}: {error_msg}")

                # Check if rate limit error
                if 'rate limit' in error_msg.lower() or 'api limit' in error_msg.lower():
                    self.mark_provider_unhealthy(provider_name, duration_seconds=600)

                # Continue to next provider
                continue

        # All providers failed
        logger.error(f"All providers failed for {symbol}: {errors}")
        raise ProviderError(f"Failed to fetch quote for {symbol}: {'; '.join(errors)}")

    async def get_quotes_batch(
        self,
        symbols: List[str],
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get quotes for multiple symbols with fallback.

        Args:
            symbols: List of stock symbols
            use_cache: Whether to use cached data

        Returns:
            List of quote dictionaries
        """
        quotes = []
        uncached_symbols = []

        # Check cache for each symbol
        if use_cache:
            for symbol in symbols:
                cached = MarketDataCache.get_quote(symbol)
                if cached:
                    quotes.append(cached)
                else:
                    uncached_symbols.append(symbol)
        else:
            uncached_symbols = symbols

        # Fetch uncached symbols
        if uncached_symbols:
            priority = self.get_provider_priority()

            for provider_name in priority:
                provider = self.providers[provider_name]

                try:
                    logger.debug(f"Fetching {len(uncached_symbols)} quotes from {provider_name}")
                    batch_quotes = await provider.get_quotes_batch(uncached_symbols)

                    # Cache results
                    if use_cache:
                        for quote in batch_quotes:
                            if quote:
                                MarketDataCache.set_quote(quote['symbol'], quote)

                    quotes.extend(batch_quotes)
                    logger.info(f"Fetched {len(batch_quotes)} quotes from {provider_name}")
                    break

                except Exception as e:
                    logger.warning(f"{provider_name} batch fetch failed: {e}")

                    # Check if rate limit error
                    if 'rate limit' in str(e).lower():
                        self.mark_provider_unhealthy(provider_name, duration_seconds=600)

                    continue

        return quotes

    async def get_historical_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        timeframe: str = '1D',
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get historical bars with automatic provider fallback.

        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            timeframe: Bar timeframe
            use_cache: Whether to use cached data

        Returns:
            List of bar dictionaries

        Raises:
            ProviderError: If all providers fail
        """
        # Check cache first
        if use_cache:
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            cached = MarketDataCache.get_bars(symbol, start_str, end_str, timeframe)

            if cached:
                logger.debug(f"Returning cached bars for {symbol}")
                return cached

        # Try providers in priority order
        priority = self.get_provider_priority()
        errors = []

        for provider_name in priority:
            provider = self.providers[provider_name]

            try:
                logger.debug(f"Fetching historical bars for {symbol} from {provider_name}")
                bars = await provider.get_historical_bars(
                    symbol, start_date, end_date, timeframe
                )

                if bars:
                    # Cache the result
                    if use_cache:
                        start_str = start_date.strftime('%Y-%m-%d')
                        end_str = end_date.strftime('%Y-%m-%d')
                        MarketDataCache.set_bars(symbol, start_str, end_str, timeframe, bars)

                    logger.info(
                        f"Successfully fetched {len(bars)} bars for {symbol} from {provider_name}"
                    )
                    return bars

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"{provider_name} failed for {symbol} historical: {error_msg}")
                errors.append(f"{provider_name}: {error_msg}")

                # Check if rate limit error
                if 'rate limit' in error_msg.lower():
                    self.mark_provider_unhealthy(provider_name, duration_seconds=600)

                continue

        # All providers failed
        logger.error(f"All providers failed for {symbol} historical: {errors}")
        raise ProviderError(
            f"Failed to fetch historical bars for {symbol}: {'; '.join(errors)}"
        )

    async def search_symbols(self, query: str, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Search for symbols with fallback.

        Args:
            query: Search query
            use_cache: Whether to use cached results

        Returns:
            List of matching symbols
        """
        # Check cache first
        if use_cache:
            cached = MarketDataCache.get_search_results(query)
            if cached:
                logger.debug(f"Returning cached search results for '{query}'")
                return cached

        # Try providers in priority order
        priority = self.get_provider_priority()

        for provider_name in priority:
            provider = self.providers[provider_name]

            try:
                logger.debug(f"Searching for '{query}' using {provider_name}")
                results = await provider.search_symbols(query)

                if results:
                    # Cache the results
                    if use_cache:
                        MarketDataCache.set_search_results(query, results)

                    logger.info(f"Found {len(results)} results for '{query}' from {provider_name}")
                    return results

            except Exception as e:
                logger.warning(f"{provider_name} search failed: {e}")
                continue

        # Return empty list if all fail
        logger.warning(f"No search results found for '{query}'")
        return []

    def get_provider_status(self) -> Dict[str, Any]:
        """
        Get status of all providers.

        Returns:
            Dictionary with provider status information
        """
        status = {}

        for name, provider in self.providers.items():
            status[name] = {
                'available': True,
                'healthy': self.provider_health.get(name, True),
                'provider_name': provider.get_provider_name(),
            }

        return status

    async def close_all(self):
        """Close all provider connections."""
        for name, provider in self.providers.items():
            try:
                await provider.close()
                logger.info(f"Closed {name} provider")
            except Exception as e:
                logger.error(f"Error closing {name} provider: {e}")


# Global provider manager instance
_provider_manager = None


def get_provider_manager() -> ProviderManager:
    """
    Get global provider manager instance (singleton).

    Returns:
        ProviderManager instance
    """
    global _provider_manager

    if _provider_manager is None:
        _provider_manager = ProviderManager()

    return _provider_manager


async def fetch_quote_with_fallback(symbol: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Convenience function to fetch quote with fallback.

    Args:
        symbol: Stock symbol
        use_cache: Whether to use cache

    Returns:
        Quote dictionary or None
    """
    manager = get_provider_manager()
    try:
        return await manager.get_quote(symbol, use_cache=use_cache)
    except ProviderError as e:
        logger.error(f"Failed to fetch quote for {symbol}: {e}")
        return None


async def fetch_historical_with_fallback(
    symbol: str,
    start_date: date,
    end_date: date,
    timeframe: str = '1D',
    use_cache: bool = True
) -> List[Dict[str, Any]]:
    """
    Convenience function to fetch historical data with fallback.

    Args:
        symbol: Stock symbol
        start_date: Start date
        end_date: End date
        timeframe: Timeframe
        use_cache: Whether to use cache

    Returns:
        List of bars
    """
    manager = get_provider_manager()
    try:
        return await manager.get_historical_bars(
            symbol, start_date, end_date, timeframe, use_cache=use_cache
        )
    except ProviderError as e:
        logger.error(f"Failed to fetch historical data for {symbol}: {e}")
        return []
