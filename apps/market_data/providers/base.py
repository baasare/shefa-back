"""
Abstract base class for market data providers.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from decimal import Decimal


class MarketDataProvider(ABC):
    """Abstract interface for market data providers."""

    def __init__(self, api_key: str):
        """
        Initialize provider with API key.

        Args:
            api_key: API key for the data provider
        """
        self.api_key = api_key

    @abstractmethod
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get latest quote for a symbol.

        Args:
            symbol: Stock symbol (e.g., 'AAPL')

        Returns:
            Dict with keys: symbol, timestamp, open, high, low, close, volume
        """
        pass

    @abstractmethod
    async def get_quotes_batch(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Get latest quotes for multiple symbols (batch request).

        Args:
            symbols: List of stock symbols

        Returns:
            List of quote dictionaries
        """
        pass

    @abstractmethod
    async def get_historical_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        timeframe: str = '1D'
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV bars for a symbol.

        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            timeframe: Bar timeframe ('1Min', '5Min', '1H', '1D', etc.)

        Returns:
            List of bar dictionaries with OHLCV data
        """
        pass

    @abstractmethod
    async def search_symbols(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for symbols matching query.

        Args:
            query: Search query string

        Returns:
            List of matching symbols with metadata
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get provider name.

        Returns:
            Provider name string
        """
        pass

    def normalize_quote(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize provider-specific quote data to standard format.

        Args:
            raw_data: Raw data from provider

        Returns:
            Normalized quote dictionary
        """
        # Override in subclass if needed
        return raw_data

    def validate_symbol(self, symbol: str) -> bool:
        """
        Validate symbol format.

        Args:
            symbol: Stock symbol

        Returns:
            True if valid, False otherwise
        """
        if not symbol or not isinstance(symbol, str):
            return False

        # Basic validation: uppercase letters, 1-5 characters
        return symbol.isupper() and 1 <= len(symbol) <= 5
