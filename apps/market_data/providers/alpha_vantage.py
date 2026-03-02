"""
Alpha Vantage market data provider.

Documentation: https://www.alphavantage.co/documentation/
"""
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging

from .base import MarketDataProvider

logger = logging.getLogger(__name__)


class AlphaVantageProvider(MarketDataProvider):
    """
    Alpha Vantage market data provider.

    Free tier includes:
    - 25 API requests per day
    - Real-time and historical data
    - Technical indicators
    - Fundamental data
    """

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str):
        """
        Initialize Alpha Vantage provider.

        Args:
            api_key: Alpha Vantage API key
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

        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": self.api_key
        }

        try:
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # Check for error or rate limit
            if "Error Message" in data:
                logger.error(f"Alpha Vantage error: {data['Error Message']}")
                raise ValueError(data["Error Message"])

            if "Note" in data:
                logger.warning(f"Alpha Vantage rate limit: {data['Note']}")
                raise ValueError("API rate limit exceeded")

            quote_data = data.get("Global Quote", {})
            if not quote_data:
                logger.warning(f"No quote data for {symbol}")
                return None

            return self._normalize_quote(symbol, quote_data)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching quote for {symbol}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            raise

    async def get_quotes_batch(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Get latest quotes for multiple symbols.

        Note: Alpha Vantage doesn't have batch endpoints,
        so we make individual requests (watch rate limits!).

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

        # Determine function based on timeframe
        function = self._get_function_for_timeframe(timeframe)
        params = {
            "function": function,
            "symbol": symbol,
            "apikey": self.api_key,
            "outputsize": "full",  # Get full historical data
            "datatype": "json"
        }

        # Add interval for intraday
        if "INTRADAY" in function:
            interval = self._parse_intraday_interval(timeframe)
            params["interval"] = interval

        try:
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # Check for errors
            if "Error Message" in data:
                logger.error(f"Alpha Vantage error: {data['Error Message']}")
                raise ValueError(data["Error Message"])

            if "Note" in data:
                logger.warning(f"Alpha Vantage rate limit: {data['Note']}")
                raise ValueError("API rate limit exceeded")

            # Get time series data
            time_series_key = self._get_time_series_key(data)
            if not time_series_key:
                logger.warning(f"No time series data for {symbol}")
                return []

            time_series = data.get(time_series_key, {})

            # Parse and filter by date range
            bars = []
            for timestamp_str, bar_data in time_series.items():
                timestamp = datetime.strptime(
                    timestamp_str,
                    "%Y-%m-%d %H:%M:%S" if " " in timestamp_str else "%Y-%m-%d"
                )

                # Filter by date range
                if start_date <= timestamp.date() <= end_date:
                    bar = self._normalize_bar(symbol, timestamp, bar_data)
                    bars.append(bar)

            # Sort by timestamp ascending
            bars.sort(key=lambda x: x["timestamp"])

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
        params = {
            "function": "SYMBOL_SEARCH",
            "keywords": query,
            "apikey": self.api_key
        }

        try:
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            if "Error Message" in data:
                logger.error(f"Alpha Vantage error: {data['Error Message']}")
                raise ValueError(data["Error Message"])

            results = []
            for match in data.get("bestMatches", []):
                results.append({
                    "symbol": match.get("1. symbol"),
                    "name": match.get("2. name"),
                    "type": match.get("3. type"),
                    "region": match.get("4. region"),
                    "market_open": match.get("5. marketOpen"),
                    "market_close": match.get("6. marketClose"),
                    "timezone": match.get("7. timezone"),
                    "currency": match.get("8. currency"),
                    "match_score": match.get("9. matchScore"),
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
        return "alpha_vantage"

    def _normalize_quote(self, symbol: str, quote_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize Alpha Vantage quote data.

        Args:
            symbol: Stock symbol
            quote_data: Raw quote from Alpha Vantage

        Returns:
            Normalized quote dictionary
        """
        # Alpha Vantage keys have numerical prefixes
        timestamp_str = quote_data.get("07. latest trading day")
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d") if timestamp_str else datetime.now()

        return {
            "symbol": symbol,
            "timestamp": timestamp,
            "open": Decimal(quote_data.get("02. open", "0")),
            "high": Decimal(quote_data.get("03. high", "0")),
            "low": Decimal(quote_data.get("04. low", "0")),
            "close": Decimal(quote_data.get("05. price", "0")),
            "volume": int(quote_data.get("06. volume", "0")),
            "source": self.get_provider_name(),
        }

    def _normalize_bar(self, symbol: str, timestamp: datetime, bar_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize Alpha Vantage bar data.

        Args:
            symbol: Stock symbol
            timestamp: Bar timestamp
            bar_data: Raw bar data

        Returns:
            Normalized bar dictionary
        """
        return {
            "symbol": symbol,
            "timestamp": timestamp,
            "open": Decimal(bar_data.get("1. open", "0")),
            "high": Decimal(bar_data.get("2. high", "0")),
            "low": Decimal(bar_data.get("3. low", "0")),
            "close": Decimal(bar_data.get("4. close", "0")),
            "volume": int(bar_data.get("5. volume", "0")),
            "source": self.get_provider_name(),
        }

    def _get_function_for_timeframe(self, timeframe: str) -> str:
        """
        Get Alpha Vantage function name for timeframe.

        Args:
            timeframe: Timeframe string

        Returns:
            Function name
        """
        timeframe = timeframe.upper()

        if 'MIN' in timeframe or 'H' in timeframe:
            return "TIME_SERIES_INTRADAY"
        elif 'D' in timeframe:
            return "TIME_SERIES_DAILY"
        elif 'W' in timeframe:
            return "TIME_SERIES_WEEKLY"
        elif 'M' in timeframe:
            return "TIME_SERIES_MONTHLY"
        else:
            return "TIME_SERIES_DAILY"

    def _parse_intraday_interval(self, timeframe: str) -> str:
        """
        Parse timeframe to Alpha Vantage intraday interval.

        Args:
            timeframe: Timeframe like '1Min', '5Min', '15Min', '30Min', '60Min'

        Returns:
            Alpha Vantage interval string
        """
        timeframe = timeframe.upper()

        if '1MIN' in timeframe or '1M' in timeframe:
            return "1min"
        elif '5MIN' in timeframe or '5M' in timeframe:
            return "5min"
        elif '15MIN' in timeframe or '15M' in timeframe:
            return "15min"
        elif '30MIN' in timeframe or '30M' in timeframe:
            return "30min"
        elif '60MIN' in timeframe or '1H' in timeframe:
            return "60min"
        else:
            return "5min"  # Default

    def _get_time_series_key(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Find the time series key in response data.

        Args:
            data: Response data

        Returns:
            Time series key or None
        """
        # Alpha Vantage uses different keys for different timeframes
        possible_keys = [
            "Time Series (Daily)",
            "Time Series (1min)",
            "Time Series (5min)",
            "Time Series (15min)",
            "Time Series (30min)",
            "Time Series (60min)",
            "Weekly Time Series",
            "Monthly Time Series",
        ]

        for key in possible_keys:
            if key in data:
                return key

        return None

    async def get_news_sentiment(
        self,
        tickers: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
        sort: str = "LATEST",
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get news and sentiment data for stocks.

        Alpha Vantage News Sentiment API provides real-time and historical
        news articles with AI-powered sentiment analysis.

        Args:
            tickers: List of stock symbols (e.g., ['AAPL', 'GOOGL'])
            topics: List of topics (e.g., ['technology', 'earnings'])
            time_from: Start time in YYYYMMDDTHHMM format
            time_to: End time in YYYYMMDDTHHMM format
            sort: Sort order - LATEST, EARLIEST, or RELEVANCE
            limit: Number of results (default 50, max 1000)

        Returns:
            Dictionary containing news articles with sentiment scores

        Sentiment Score Interpretation:
            x <= -0.35: Bearish
            -0.35 < x <= -0.15: Somewhat Bearish
            -0.15 < x < 0.15: Neutral
            0.15 <= x < 0.35: Somewhat Bullish
            x >= 0.35: Bullish
        """
        params = {
            "function": "NEWS_SENTIMENT",
            "apikey": self.api_key,
            "sort": sort,
            "limit": limit
        }

        # Add tickers filter
        if tickers:
            params["tickers"] = ",".join(tickers)

        # Add topics filter
        if topics:
            params["topics"] = ",".join(topics)

        # Add time range
        if time_from:
            params["time_from"] = time_from
        if time_to:
            params["time_to"] = time_to

        try:
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # Check for errors
            if "Error Message" in data:
                logger.error(f"Alpha Vantage error: {data['Error Message']}")
                raise ValueError(data["Error Message"])

            if "Note" in data:
                logger.warning(f"Alpha Vantage rate limit: {data['Note']}")
                raise ValueError("API rate limit exceeded")

            # Process news feed
            feed = data.get("feed", [])
            processed_news = []

            for article in feed:
                processed_article = self._normalize_news_article(article, tickers)
                processed_news.append(processed_article)

            logger.info(f"Fetched {len(processed_news)} news articles")

            return {
                "items": len(processed_news),
                "sentiment_score_definition": data.get("sentiment_score_definition"),
                "relevance_score_definition": data.get("relevance_score_definition"),
                "feed": processed_news
            }

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching news sentiment: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching news sentiment: {e}")
            raise

    def _normalize_news_article(
        self,
        article: Dict[str, Any],
        filter_tickers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Normalize news article data from Alpha Vantage.

        Args:
            article: Raw article data
            filter_tickers: Tickers to filter sentiment for

        Returns:
            Normalized article dictionary
        """
        # Extract overall sentiment
        overall_sentiment = article.get("overall_sentiment_score", 0)
        overall_label = article.get("overall_sentiment_label", "Neutral")

        # Extract ticker-specific sentiment
        ticker_sentiments = []
        for ticker_data in article.get("ticker_sentiment", []):
            ticker = ticker_data.get("ticker")

            # Only include filtered tickers if specified
            if filter_tickers and ticker not in filter_tickers:
                continue

            ticker_sentiments.append({
                "ticker": ticker,
                "relevance_score": float(ticker_data.get("relevance_score", 0)),
                "sentiment_score": float(ticker_data.get("ticker_sentiment_score", 0)),
                "sentiment_label": ticker_data.get("ticker_sentiment_label", "Neutral")
            })

        # Parse time published
        time_published = article.get("time_published", "")
        try:
            published_dt = datetime.strptime(time_published, "%Y%m%dT%H%M%S")
        except:
            published_dt = datetime.now()

        return {
            "title": article.get("title", ""),
            "url": article.get("url", ""),
            "time_published": published_dt,
            "authors": article.get("authors", []),
            "summary": article.get("summary", ""),
            "source": article.get("source", ""),
            "category_within_source": article.get("category_within_source", ""),
            "source_domain": article.get("source_domain", ""),
            "topics": [
                {
                    "topic": topic.get("topic"),
                    "relevance_score": float(topic.get("relevance_score", 0))
                }
                for topic in article.get("topics", [])
            ],
            "overall_sentiment_score": float(overall_sentiment),
            "overall_sentiment_label": overall_label,
            "ticker_sentiment": ticker_sentiments
        }

    def interpret_sentiment_score(self, score: float) -> str:
        """
        Interpret sentiment score into a label.

        Args:
            score: Sentiment score between -1 and 1

        Returns:
            Sentiment label
        """
        if score <= -0.35:
            return "Bearish"
        elif -0.35 < score <= -0.15:
            return "Somewhat Bearish"
        elif -0.15 < score < 0.15:
            return "Neutral"
        elif 0.15 <= score < 0.35:
            return "Somewhat Bullish"
        else:
            return "Bullish"

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
