"""
Massive.com (formerly Polygon.io) market data provider.

Documentation: https://massive.com/docs/rest/quickstart
"""
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from decimal import Decimal
import logging

from apps.market_data.providers.base import MarketDataProvider

logger = logging.getLogger(__name__)


class MassiveProvider(MarketDataProvider):
    """
    Massive.com (formerly Polygon.io) market data provider.

    Free tier includes:
    - Real-time quotes (15-minute delay)
    - Historical data
    - Stock aggregates (bars)
    """

    BASE_URL = "https://api.massive.com"

    def __init__(self, api_key: str):
        """
        Initialize Massive.com provider.

        Args:
            api_key: Massive.com API key (legacy Polygon.io keys still work)
        """
        super().__init__(api_key)
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get latest NBBO (National Best Bid and Offer) quote for a symbol.

        Args:
            symbol: Stock symbol (e.g., 'AAPL')

        Returns:
            Quote dictionary with bid/ask prices, sizes, and timestamps
        """
        if not self.validate_symbol(symbol):
            raise ValueError(f"Invalid symbol: {symbol}")

        url = f"{self.BASE_URL}/v2/last/nbbo/{symbol}"
        params = {"apiKey": self.api_key}

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "OK" or not data.get("results"):
                logger.warning(f"No quote data found for symbol {symbol}")
                return None

            result = data["results"]
            return self._normalize_quote(symbol, result)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching quote for {symbol}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            raise

    async def get_quotes_batch(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Get latest quotes for multiple symbols.

        Note: Massive.com doesn't have a true batch endpoint for free tier,
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

    async def search_symbols(self, query: str, market: str) -> List[Dict[str, Any]]:
        """
        Search for symbols.

        Args:
            query: Search query
            market: Market type (e.g., 'stocks', 'crypto', 'fx', 'otc', 'indices')

        Returns:
            List of matching symbols
        """
        url = f"{self.BASE_URL}/v3/reference/tickers"
        params = {
            "apiKey": self.api_key,
            "ticker": query,
            "market": market,
            "active": "true",
            "order": "asc",
            "limit": 50,
            "sort": "ticker"
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

    def _normalize_quote(self, symbol: str, quote_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize Massive.com quote data to standard format.

        Args:
            symbol: Stock symbol
            quote_data: Raw quote data from Massive.com Last Quote endpoint

        Returns:
            Normalized quote dictionary
        """
        # Timestamp is in nanoseconds, convert to datetime
        timestamp_ns = quote_data.get("t")
        timestamp = datetime.fromtimestamp(timestamp_ns / 1_000_000_000) if timestamp_ns else None

        return {
            "symbol": symbol,
            "timestamp": timestamp,
            "bid_price": Decimal(str(quote_data.get("p", 0))),
            "bid_size": int(quote_data.get("s", 0)),
            "ask_price": Decimal(str(quote_data.get("P", 0))),
            "ask_size": int(quote_data.get("S", 0)),
            "bid_exchange_id": quote_data.get("x"),
            "ask_exchange_id": quote_data.get("X"),
            "sequence_number": quote_data.get("q"),
            "sip_timestamp": datetime.fromtimestamp(quote_data["t"] / 1_000_000_000) if quote_data.get("t") else None,
            "participant_timestamp": datetime.fromtimestamp(quote_data["y"] / 1_000_000_000) if quote_data.get("y") else None,
            "trf_timestamp": datetime.fromtimestamp(quote_data["f"] / 1_000_000_000) if quote_data.get("f") else None,
            "tape": quote_data.get("z"),
            "conditions": quote_data.get("c", []),
            "indicators": quote_data.get("i", []),
            "source": self.get_provider_name(),
        }

    def _normalize_bar(self, symbol: str, bar_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize Massive.com bar data to standard format.

        Args:
            symbol: Stock symbol
            bar_data: Raw bar data from Massive.com

        Returns:
            Normalized bar dictionary
        """
        # Massive.com timestamp is in milliseconds
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
        Parse timeframe string to Massive.com format.

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
