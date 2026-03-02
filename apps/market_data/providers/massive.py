"""
Massive.com (formerly Polygon.io) market data provider.

Documentation: https://polygon.io/docs/stocks/getting-started
"""
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from decimal import Decimal
import logging

from .base import MarketDataProvider

logger = logging.getLogger(__name__)


class MassiveProvider(MarketDataProvider):
    """
    Massive.com (Polygon.io) market data provider.

    Free tier includes:
    - Real-time quotes (15-minute delay)
    - Historical data
    - Stock aggregates (bars)
    """

    BASE_URL = "https://api.polygon.io"

    def __init__(self, api_key: str):
        """
        Initialize Massive.com provider.

        Args:
            api_key: Polygon.io API key
        """
        super().__init__(api_key)
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get latest quote for a symbol.

        Args:
            symbol: Stock symbol (e.g., 'AAPL')

        Returns:
            Quote dictionary
        """
        if not self.validate_symbol(symbol):
            raise ValueError(f"Invalid symbol: {symbol}")

        url = f"{self.BASE_URL}/v2/aggs/ticker/{symbol}/prev"
        params = {"apiKey": self.api_key}

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "OK" or not data.get("results"):
                logger.warning(f"No data found for symbol {symbol}")
                return None

            result = data["results"][0]
            return self._normalize_bar(symbol, result)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching quote for {symbol}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            raise

    async def get_quotes_batch(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Get latest quotes for multiple symbols.

        Note: Polygon doesn't have a true batch endpoint for free tier,
        so we make individual requests.

        Args:
            symbols: List of stock symbols

        Returns:
            List of quote dictionaries
        """
        quotes = []
        for symbol in symbols:
            try:
                quote = await self.get_quote(symbol)
                if quote:
                    quotes.append(quote)
            except Exception as e:
                logger.error(f"Error fetching quote for {symbol}: {e}")
                continue

        return quotes

    async def get_historical_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        timeframe: str = '1D'
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV bars.

        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            timeframe: '1Min', '5Min', '15Min', '1H', '1D', etc.

        Returns:
            List of bar dictionaries
        """
        if not self.validate_symbol(symbol):
            raise ValueError(f"Invalid symbol: {symbol}")

        # Map timeframe to Polygon format
        multiplier, timespan = self._parse_timeframe(timeframe)

        url = f"{self.BASE_URL}/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_date}/{end_date}"
        params = {
            "apiKey": self.api_key,
            "adjusted": "true",
            "sort": "asc",
            "limit": 50000
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "OK" or not data.get("results"):
                logger.warning(f"No historical data for {symbol} from {start_date} to {end_date}")
                return []

            bars = []
            for result in data["results"]:
                bar = self._normalize_bar(symbol, result)
                bars.append(bar)

            logger.info(f"Fetched {len(bars)} bars for {symbol}")
            return bars

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching historical data for {symbol}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            raise

    async def search_symbols(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for symbols.

        Args:
            query: Search query

        Returns:
            List of matching symbols
        """
        url = f"{self.BASE_URL}/v3/reference/tickers"
        params = {
            "apiKey": self.api_key,
            "search": query,
            "active": "true",
            "limit": 20
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            results = []
            for ticker in data.get("results", []):
                results.append({
                    "symbol": ticker.get("ticker"),
                    "name": ticker.get("name"),
                    "market": ticker.get("market"),
                    "locale": ticker.get("locale"),
                    "type": ticker.get("type"),
                    "active": ticker.get("active"),
                })

            return results

        except httpx.HTTPError as e:
            logger.error(f"HTTP error searching symbols: {e}")
            raise
        except Exception as e:
            logger.error(f"Error searching symbols: {e}")
            raise

    def get_provider_name(self) -> str:
        """Get provider name."""
        return "massive"

    def _normalize_bar(self, symbol: str, bar_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize Polygon bar data to standard format.

        Args:
            symbol: Stock symbol
            bar_data: Raw bar data from Polygon

        Returns:
            Normalized bar dictionary
        """
        # Polygon timestamp is in milliseconds
        timestamp_ms = bar_data.get("t")
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000) if timestamp_ms else None

        return {
            "symbol": symbol,
            "timestamp": timestamp,
            "open": Decimal(str(bar_data.get("o", 0))),
            "high": Decimal(str(bar_data.get("h", 0))),
            "low": Decimal(str(bar_data.get("l", 0))),
            "close": Decimal(str(bar_data.get("c", 0))),
            "volume": int(bar_data.get("v", 0)),
            "source": self.get_provider_name(),
        }

    def _parse_timeframe(self, timeframe: str) -> tuple:
        """
        Parse timeframe string to Polygon format.

        Args:
            timeframe: Timeframe like '1Min', '5Min', '1H', '1D'

        Returns:
            Tuple of (multiplier, timespan)
        """
        timeframe = timeframe.upper()

        # Extract multiplier and unit
        if 'MIN' in timeframe:
            multiplier = int(timeframe.replace('MIN', ''))
            return (multiplier, 'minute')
        elif 'H' in timeframe:
            multiplier = int(timeframe.replace('H', ''))
            return (multiplier, 'hour')
        elif 'D' in timeframe:
            multiplier = int(timeframe.replace('D', ''))
            return (multiplier, 'day')
        elif 'W' in timeframe:
            multiplier = int(timeframe.replace('W', ''))
            return (multiplier, 'week')
        elif 'M' in timeframe:
            multiplier = int(timeframe.replace('M', ''))
            return (multiplier, 'month')
        else:
            # Default to 1 day
            return (1, 'day')

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
