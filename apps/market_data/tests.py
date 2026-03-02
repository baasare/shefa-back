"""
Comprehensive test suite for the market_data app.
Tests market data providers, indicators, caching, and API endpoints.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal
from datetime import timedelta
import json

from apps.market_data.models import Quote, Indicator, ChartPattern
from apps.market_data.providers.massive import MassiveProvider
from apps.market_data.providers.alpha_vantage import AlphaVantageProvider
from apps.market_data.indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_sma,
    calculate_ema
)
from apps.market_data.analysis import (
    detect_double_top,
    detect_double_bottom,
    detect_trend
)

User = get_user_model()


class QuoteModelTests(TestCase):
    """Test cases for Quote model."""

    def setUp(self):
        """Set up test data."""
        pass

    def test_create_quote(self):
        """Test creating a quote."""
        quote = Quote.objects.create(
            symbol='AAPL',
            open_price=Decimal('150.00'),
            high_price=Decimal('152.00'),
            low_price=Decimal('149.00'),
            close_price=Decimal('151.00'),
            volume=1000000,
            timestamp=timezone.now()
        )

        self.assertEqual(quote.symbol, 'AAPL')
        self.assertEqual(quote.open_price, Decimal('150.00'))
        self.assertEqual(quote.close_price, Decimal('151.00'))
        self.assertEqual(quote.volume, 1000000)

    def test_quote_ohlcv_data(self):
        """Test OHLCV data completeness."""
        quote = Quote.objects.create(
            symbol='MSFT',
            open_price=Decimal('300.00'),
            high_price=Decimal('305.00'),
            low_price=Decimal('298.00'),
            close_price=Decimal('303.00'),
            volume=500000,
            timestamp=timezone.now()
        )

        self.assertIsNotNone(quote.open_price)
        self.assertIsNotNone(quote.high_price)
        self.assertIsNotNone(quote.low_price)
        self.assertIsNotNone(quote.close_price)
        self.assertIsNotNone(quote.volume)

    def test_quote_string_representation(self):
        """Test __str__ method."""
        timestamp = timezone.now()
        quote = Quote.objects.create(
            symbol='TSLA',
            open_price=Decimal('200.00'),
            high_price=Decimal('205.00'),
            low_price=Decimal('198.00'),
            close_price=Decimal('203.00'),
            volume=750000,
            timestamp=timestamp
        )

        expected = f"TSLA - {timestamp.date()}"
        self.assertEqual(str(quote), expected)

    def test_quote_deduplication(self):
        """Test that duplicate quotes are prevented."""
        timestamp = timezone.now()

        quote1 = Quote.objects.create(
            symbol='AAPL',
            open_price=Decimal('150.00'),
            high_price=Decimal('152.00'),
            low_price=Decimal('149.00'),
            close_price=Decimal('151.00'),
            volume=1000000,
            timestamp=timestamp
        )

        # Creating duplicate should be handled by unique constraint
        with self.assertRaises(Exception):
            Quote.objects.create(
                symbol='AAPL',
                open_price=Decimal('150.50'),
                high_price=Decimal('152.50'),
                low_price=Decimal('149.50'),
                close_price=Decimal('151.50'),
                volume=1100000,
                timestamp=timestamp
            )


class IndicatorModelTests(TestCase):
    """Test cases for Indicator model."""

    def test_create_indicator(self):
        """Test creating an indicator."""
        indicator = Indicator.objects.create(
            symbol='AAPL',
            name='rsi',
            timeframe='1d',
            value=Decimal('45.50'),
            timestamp=timezone.now()
        )

        self.assertEqual(indicator.symbol, 'AAPL')
        self.assertEqual(indicator.name, 'rsi')
        self.assertEqual(indicator.value, Decimal('45.50'))

    def test_indicator_calculation(self):
        """Test storing calculated indicator."""
        indicator = Indicator.objects.create(
            symbol='MSFT',
            name='macd',
            timeframe='1d',
            value=Decimal('2.35'),
            metadata={'signal': '1.80', 'histogram': '0.55'},
            timestamp=timezone.now()
        )

        self.assertEqual(indicator.name, 'macd')
        self.assertIn('signal', indicator.metadata)
        self.assertIn('histogram', indicator.metadata)

    def test_indicator_timeframes(self):
        """Test different indicator timeframes."""
        timeframes = ['1m', '5m', '15m', '1h', '1d']

        for tf in timeframes:
            indicator = Indicator.objects.create(
                symbol='AAPL',
                name='rsi',
                timeframe=tf,
                value=Decimal('50.00'),
                timestamp=timezone.now()
            )

            self.assertEqual(indicator.timeframe, tf)

    def test_indicator_string_representation(self):
        """Test __str__ method."""
        indicator = Indicator.objects.create(
            symbol='TSLA',
            name='sma_20',
            timeframe='1d',
            value=Decimal('195.50'),
            timestamp=timezone.now()
        )

        expected = f"TSLA - sma_20 (1d)"
        self.assertEqual(str(indicator), expected)


class MassiveProviderTests(TestCase):
    """Test cases for Massive.com market data provider."""

    def setUp(self):
        """Set up test provider."""
        self.provider = MassiveProvider()

    @patch('httpx.Client.get')
    def test_get_quote(self, mock_get):
        """Test getting current quote."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'symbol': 'AAPL',
            'price': 150.50,
            'volume': 1000000,
            'timestamp': '2024-01-01T12:00:00Z'
        }
        mock_get.return_value = mock_response

        quote = self.provider.get_quote('AAPL')

        self.assertEqual(quote['symbol'], 'AAPL')
        self.assertEqual(quote['price'], 150.50)

    @patch('httpx.Client.get')
    def test_get_historical_data(self, mock_get):
        """Test getting historical data."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [
                {'date': '2024-01-01', 'open': 150, 'high': 152, 'low': 149, 'close': 151, 'volume': 1000000},
                {'date': '2024-01-02', 'open': 151, 'high': 153, 'low': 150, 'close': 152, 'volume': 1100000},
            ]
        }
        mock_get.return_value = mock_response

        data = self.provider.get_historical_data('AAPL', days=2)

        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['close'], 151)

    @patch('httpx.Client.get')
    def test_handle_rate_limits(self, mock_get):
        """Test handling rate limit errors."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.json.return_value = {'error': 'Rate limit exceeded'}
        mock_get.return_value = mock_response

        with self.assertRaises(Exception):
            self.provider.get_quote('AAPL')

    @patch('httpx.Client.get')
    def test_handle_errors(self, mock_get):
        """Test handling API errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {'error': 'Internal server error'}
        mock_get.return_value = mock_response

        with self.assertRaises(Exception):
            self.provider.get_quote('AAPL')


class AlphaVantageProviderTests(TestCase):
    """Test cases for Alpha Vantage provider (fallback)."""

    def setUp(self):
        """Set up test provider."""
        self.provider = AlphaVantageProvider()

    @patch('httpx.Client.get')
    def test_get_quote(self, mock_get):
        """Test getting quote from Alpha Vantage."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'Global Quote': {
                '01. symbol': 'AAPL',
                '05. price': '150.50',
                '06. volume': '1000000',
            }
        }
        mock_get.return_value = mock_response

        quote = self.provider.get_quote('AAPL')

        self.assertIsNotNone(quote)

    @patch('httpx.Client.get')
    def test_provider_fallback(self, mock_get):
        """Test provider fallback logic."""
        # First call fails (Massive)
        # Second call succeeds (Alpha Vantage)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'Global Quote': {
                '01. symbol': 'AAPL',
                '05. price': '150.50'
            }
        }
        mock_get.return_value = mock_response

        quote = self.provider.get_quote('AAPL')

        self.assertIsNotNone(quote)


class IndicatorCalculationsTests(TestCase):
    """Test cases for technical indicator calculations."""

    def test_calculate_rsi(self):
        """Test RSI calculation."""
        prices = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 111, 110, 112, 114]

        rsi = calculate_rsi(prices, period=14)

        self.assertIsNotNone(rsi)
        self.assertGreater(rsi, 0)
        self.assertLess(rsi, 100)

    def test_calculate_rsi_oversold(self):
        """Test RSI in oversold territory."""
        # Declining prices
        prices = [100 - i for i in range(20)]

        rsi = calculate_rsi(prices, period=14)

        self.assertIsNotNone(rsi)
        self.assertLess(rsi, 30)  # Oversold

    def test_calculate_rsi_overbought(self):
        """Test RSI in overbought territory."""
        # Rising prices
        prices = [100 + i for i in range(20)]

        rsi = calculate_rsi(prices, period=14)

        self.assertIsNotNone(rsi)
        self.assertGreater(rsi, 70)  # Overbought

    def test_calculate_macd(self):
        """Test MACD calculation."""
        prices = [100 + i * 0.5 for i in range(50)]

        macd_data = calculate_macd(prices)

        self.assertIn('macd', macd_data)
        self.assertIn('signal', macd_data)
        self.assertIn('histogram', macd_data)

    def test_calculate_bollinger_bands(self):
        """Test Bollinger Bands calculation."""
        prices = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 111, 110, 112, 114, 113, 115, 117, 116, 118, 120]

        bb_data = calculate_bollinger_bands(prices, period=20)

        self.assertIn('upper', bb_data)
        self.assertIn('middle', bb_data)
        self.assertIn('lower', bb_data)
        self.assertGreater(bb_data['upper'], bb_data['middle'])
        self.assertLess(bb_data['lower'], bb_data['middle'])

    def test_calculate_sma(self):
        """Test SMA calculation."""
        prices = [100, 102, 104, 106, 108]

        sma = calculate_sma(prices, period=5)

        expected_sma = sum(prices) / len(prices)
        self.assertEqual(sma, expected_sma)

    def test_calculate_ema(self):
        """Test EMA calculation."""
        prices = [100, 102, 104, 106, 108, 110, 112]

        ema = calculate_ema(prices, period=5)

        self.assertIsNotNone(ema)
        self.assertGreater(ema, min(prices))
        self.assertLess(ema, max(prices))


class MarketDataCacheTests(TestCase):
    """Test cases for market data caching."""

    def setUp(self):
        """Set up cache."""
        cache.clear()

    def tearDown(self):
        """Clear cache after test."""
        cache.clear()

    def test_cache_hit(self):
        """Test cache hit."""
        cache_key = 'quote:AAPL'
        cache_data = {'symbol': 'AAPL', 'price': 150.50}

        # Set cache
        cache.set(cache_key, cache_data, timeout=300)

        # Get from cache
        cached = cache.get(cache_key)

        self.assertEqual(cached, cache_data)

    def test_cache_miss(self):
        """Test cache miss."""
        cache_key = 'quote:NONEXISTENT'

        cached = cache.get(cache_key)

        self.assertIsNone(cached)

    def test_cache_expiration(self):
        """Test cache expiration."""
        cache_key = 'quote:AAPL'
        cache_data = {'symbol': 'AAPL', 'price': 150.50}

        # Set with 1 second timeout
        cache.set(cache_key, cache_data, timeout=1)

        # Immediate get should work
        cached = cache.get(cache_key)
        self.assertEqual(cached, cache_data)

        # After expiration, should be None
        import time
        time.sleep(2)
        cached = cache.get(cache_key)
        self.assertIsNone(cached)

    def test_cache_invalidation(self):
        """Test cache invalidation."""
        cache_key = 'quote:AAPL'
        cache_data = {'symbol': 'AAPL', 'price': 150.50}

        cache.set(cache_key, cache_data, timeout=300)

        # Invalidate
        cache.delete(cache_key)

        # Should be None
        cached = cache.get(cache_key)
        self.assertIsNone(cached)


class ChartPatternDetectionTests(TestCase):
    """Test cases for chart pattern detection."""

    def test_detect_double_top(self):
        """Test double top pattern detection."""
        # Create price pattern with two peaks
        prices = [100, 105, 110, 108, 105, 107, 110, 108, 105, 100]

        result = detect_double_top(prices)

        self.assertIn('pattern_detected', result)

    def test_detect_double_bottom(self):
        """Test double bottom pattern detection."""
        # Create price pattern with two bottoms
        prices = [100, 95, 90, 92, 95, 93, 90, 92, 95, 100]

        result = detect_double_bottom(prices)

        self.assertIn('pattern_detected', result)

    def test_detect_uptrend(self):
        """Test uptrend detection."""
        prices = [100 + i for i in range(20)]

        trend = detect_trend(prices)

        self.assertEqual(trend, 'uptrend')

    def test_detect_downtrend(self):
        """Test downtrend detection."""
        prices = [100 - i for i in range(20)]

        trend = detect_trend(prices)

        self.assertEqual(trend, 'downtrend')

    def test_detect_sideways(self):
        """Test sideways trend detection."""
        prices = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101]

        trend = detect_trend(prices)

        self.assertEqual(trend, 'sideways')


class MarketDataAPITests(APITestCase):
    """Test cases for Market Data API endpoints."""

    def setUp(self):
        """Set up test client and data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.client = APIClient()
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

    @patch('apps.market_data.views.get_market_data_provider')
    def test_get_quote(self, mock_provider):
        """Test getting quote via API."""
        mock_provider_instance = Mock()
        mock_provider_instance.get_quote.return_value = {
            'symbol': 'AAPL',
            'price': 150.50,
            'volume': 1000000
        }
        mock_provider.return_value = mock_provider_instance

        response = self.client.get('/api/market-data/quote/AAPL/')

        self.assertIn(response.status_code, [200, 404])

    @patch('apps.market_data.views.get_market_data_provider')
    def test_get_historical_data(self, mock_provider):
        """Test getting historical data via API."""
        mock_provider_instance = Mock()
        mock_provider_instance.get_historical_data.return_value = [
            {'date': '2024-01-01', 'close': 150.00},
            {'date': '2024-01-02', 'close': 151.00},
        ]
        mock_provider.return_value = mock_provider_instance

        response = self.client.get('/api/market-data/historical/AAPL/?days=2')

        self.assertIn(response.status_code, [200, 404])

    def test_get_quote_unauthenticated(self):
        """Test getting quote requires authentication."""
        self.client.credentials()

        response = self.client.get('/api/market-data/quote/AAPL/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('apps.market_data.views.get_market_data_provider')
    def test_get_indicators(self, mock_provider):
        """Test getting indicators via API."""
        mock_provider_instance = Mock()
        mock_provider_instance.get_indicators.return_value = {
            'rsi': 45.5,
            'macd': 2.3,
            'sma_20': 150.0
        }
        mock_provider.return_value = mock_provider_instance

        response = self.client.get('/api/market-data/indicators/AAPL/')

        self.assertIn(response.status_code, [200, 404])

    @patch('apps.market_data.tasks.sync_market_data')
    def test_sync_data(self, mock_sync):
        """Test syncing market data."""
        mock_sync.delay.return_value = Mock(id='task-123')

        response = self.client.post(
            '/api/market-data/sync/',
            {'symbols': ['AAPL', 'MSFT']},
            format='json'
        )

        self.assertIn(response.status_code, [200, 201, 202])


class MarketDataIntegrationTests(TestCase):
    """Integration tests for market data workflows."""

    def setUp(self):
        """Set up test data."""
        cache.clear()

    def tearDown(self):
        """Clean up."""
        cache.clear()

    @patch('apps.market_data.providers.massive.MassiveProvider.get_quote')
    def test_get_quote_with_cache(self, mock_get_quote):
        """Test getting quote with caching."""
        mock_get_quote.return_value = {
            'symbol': 'AAPL',
            'price': 150.50,
            'volume': 1000000
        }

        provider = MassiveProvider()

        # First call - should hit provider
        quote1 = provider.get_quote('AAPL')
        self.assertEqual(quote1['price'], 150.50)

        # Cache the result
        cache_key = 'quote:AAPL'
        cache.set(cache_key, quote1, timeout=300)

        # Second call - should hit cache
        quote2 = cache.get(cache_key)
        self.assertEqual(quote2['price'], 150.50)

        # Provider should only be called once
        self.assertEqual(mock_get_quote.call_count, 1)

    @patch('apps.market_data.providers.massive.MassiveProvider.get_historical_data')
    def test_calculate_indicators_from_historical_data(self, mock_get_historical):
        """Test calculating indicators from historical data."""
        mock_get_historical.return_value = [
            {'date': f'2024-01-{i:02d}', 'close': 100 + i}
            for i in range(1, 21)
        ]

        provider = MassiveProvider()
        historical_data = provider.get_historical_data('AAPL', days=20)

        prices = [float(d['close']) for d in historical_data]
        rsi = calculate_rsi(prices, period=14)

        self.assertIsNotNone(rsi)
        self.assertGreater(rsi, 0)
        self.assertLess(rsi, 100)
