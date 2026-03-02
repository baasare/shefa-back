"""
Celery tasks for market data synchronization.
"""
import logging
import asyncio
from celery import shared_task
from django.utils import timezone
from datetime import datetime, timedelta, date

from apps.market_data.models import Quote, Indicator
from apps.market_data.provider_manager import get_provider_manager
from apps.market_data.indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_sma,
    calculate_ema,
    calculate_atr,
    detect_crossover,
    detect_support_resistance,
    calculate_volume_profile
)

logger = logging.getLogger(__name__)


def get_all_watched_symbols():
    """
    Get all symbols being watched by active strategies.

    Returns:
        Set of unique symbols
    """
    from apps.strategies.models import Strategy

    symbols = set()
    active_strategies = Strategy.objects.filter(status='active')

    for strategy in active_strategies:
        watchlist = strategy.watchlist or []
        symbols.update(watchlist)

    return list(symbols)


def _save_indicators(symbol, timestamps, values, indicator_type, parameters):
    """Save indicator values to database."""
    for timestamp, value in zip(timestamps, values):
        if value is None or (isinstance(value, float) and not value):
            continue

        try:
            Indicator.objects.update_or_create(
                symbol=symbol,
                indicator_type=indicator_type,
                timestamp=timestamp,
                parameters=parameters,
                defaults={'value': value}
            )
        except Exception as e:
            logger.error(f"Error saving indicator: {e}")
            continue


def _save_quote_data(quote_data):
    """
    Save quote data to database.

    Args:
        quote_data: Dictionary containing quote information

    Returns:
        True if saved successfully, False otherwise
    """
    if not quote_data:
        return False

    try:
        Quote.objects.update_or_create(
            symbol=quote_data.get('symbol'),
            timestamp=quote_data.get('timestamp'),
            source=quote_data.get('source'),
            defaults={
                'open': quote_data.get('open', 0),
                'high': quote_data.get('high', 0),
                'low': quote_data.get('low', 0),
                'close': quote_data.get('close', 0),
                'volume': quote_data.get('volume', 0),
            }
        )
        return True
    except Exception as e:
        logger.error(f"Error saving quote for {quote_data.get('symbol')}: {e}", exc_info=True)
        return False


@shared_task(bind=True, max_retries=3)
def sync_latest_quotes(self, symbols: list = None, use_cache: bool = True):
    """
    Sync latest quotes for symbols with automatic fallback.

    This task runs every 30 seconds via Celery Beat to keep quotes fresh.

    Args:
        symbols: List of symbols to sync (if None, syncs all watched symbols)
        use_cache: Whether to use cached data (default True)
    """
    try:
        # Get symbols to sync
        if symbols is None:
            symbols = get_all_watched_symbols()

        if not symbols:
            logger.info("No symbols to sync")
            return {"status": "skipped", "reason": "no_symbols"}

        logger.info(f"Syncing latest quotes for {len(symbols)} symbols (cache: {use_cache})")

        # Get a provider manager with fallback
        manager = get_provider_manager()

        # Fetch quotes (async with fallback)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        quotes = loop.run_until_complete(
            manager.get_quotes_batch(symbols, use_cache=use_cache)
        )
        loop.close()

        # Save to the database
        saved_count = 0
        for quote_data in quotes:
            if _save_quote_data(quote_data):
                saved_count += 1
                logger.debug(f"Saved quote for {quote_data['symbol']}")

        logger.info(f"Successfully synced {saved_count}/{len(symbols)} quotes")

        return {
            "status": "success",
            "symbols_requested": len(symbols),
            "quotes_saved": saved_count
        }

    except Exception as exc:
        logger.error(f"Error syncing quotes: {exc}", exc_info=True)
        # Retry with exponential backoff
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=2)
def sync_historical_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe: str = '1D',
        use_cache: bool = True
):
    """
    Sync historical bars for a symbol with automatic fallback.

    Args:
        symbol: Stock symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        timeframe: Timeframe ('1Min', '5Min', '1H', '1D', etc.)
        use_cache: Whether to use cached data (default True)
    """
    try:
        logger.info(f"Syncing historical bars for {symbol} from {start_date} to {end_date} (cache: {use_cache})")

        # Parse dates
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

        # Get the provider manager with fallback
        manager = get_provider_manager()

        # Fetch historical bars (async with fallback)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bars = loop.run_until_complete(
            manager.get_historical_bars(symbol, start, end, timeframe, use_cache=use_cache)
        )
        loop.close()

        # Save to a database
        saved_count = 0
        for bar_data in bars:
            if _save_quote_data(bar_data):
                saved_count += 1

        logger.info(f"Successfully synced {saved_count} bars for {symbol}")

        # Trigger indicator calculation
        if saved_count > 0:
            calculate_indicators_for_symbol.delay(symbol)

        return {
            "status": "success",
            "symbol": symbol,
            "bars_saved": saved_count
        }

    except Exception as exc:
        logger.error(f"Error syncing historical bars for {symbol}: {exc}", exc_info=True)
        self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))


@shared_task(bind=True)
def calculate_indicators_for_symbol(self, symbol: str, period_days: int = 100):
    """
    Calculate technical indicators for a symbol.

    Args:
        symbol: Stock symbol
        period_days: Number of days of data to use (default 100)
    """
    try:
        logger.info(f"Calculating indicators for {symbol}")

        # Get recent quotes
        cutoff_date = timezone.now() - timedelta(days=period_days)
        quotes = Quote.objects.filter(
            symbol=symbol,
            timestamp__gte=cutoff_date
        ).order_by('timestamp')

        if quotes.count() < 30:
            logger.warning(f"Not enough data for {symbol} (need at least 30 bars)")
            return {"status": "skipped", "reason": "insufficient_data"}

        # Extract price data
        closes = [float(q.close) for q in quotes]
        highs = [float(q.high) for q in quotes]
        lows = [float(q.low) for q in quotes]
        volumes = [int(q.volume) for q in quotes]
        timestamps = [q.timestamp for q in quotes]

        # Calculate RSI
        rsi_values = calculate_rsi(closes, period=14)
        _save_indicators(symbol, timestamps, rsi_values, 'rsi', {'period': 14})

        # Calculate MACD
        macd_data = calculate_macd(closes)
        _save_indicators(symbol, timestamps, macd_data['macd'], 'macd', {'type': 'macd_line'})
        _save_indicators(symbol, timestamps, macd_data['signal'], 'macd', {'type': 'signal_line'})
        _save_indicators(symbol, timestamps, macd_data['histogram'], 'macd', {'type': 'histogram'})

        # Calculate Bollinger Bands
        bb_data = calculate_bollinger_bands(closes)
        _save_indicators(symbol, timestamps, bb_data['upper'], 'bollinger', {'type': 'upper', 'period': 20})
        _save_indicators(symbol, timestamps, bb_data['middle'], 'bollinger', {'type': 'middle', 'period': 20})
        _save_indicators(symbol, timestamps, bb_data['lower'], 'bollinger', {'type': 'lower', 'period': 20})

        # Calculate moving averages
        sma_20 = calculate_sma(closes, period=20)
        sma_50 = calculate_sma(closes, period=50)
        ema_12 = calculate_ema(closes, period=12)
        ema_26 = calculate_ema(closes, period=26)

        _save_indicators(symbol, timestamps, sma_20, 'sma', {'period': 20})
        _save_indicators(symbol, timestamps, sma_50, 'sma', {'period': 50})
        _save_indicators(symbol, timestamps, ema_12, 'ema', {'period': 12})
        _save_indicators(symbol, timestamps, ema_26, 'ema', {'period': 26})

        # Calculate ATR
        atr_values = calculate_atr(highs, lows, closes, period=14)
        _save_indicators(symbol, timestamps, atr_values, 'atr', {'period': 14})

        # Detect MA Crossovers (EMA12 vs EMA26)
        crossover_signals = detect_crossover(ema_12, ema_26)
        _save_indicators(symbol, timestamps, crossover_signals, 'crossover', {'type': 'ema_12_26'})

        # Detect Support/Resistance Levels (calculate once for latest data)
        sr_levels = detect_support_resistance(highs, lows, closes, window=20)
        if sr_levels.get('support') or sr_levels.get('resistance'):
            # Store as JSON in the last timestamp
            import json
            sr_data = {
                'support': sr_levels.get('support', []),
                'resistance': sr_levels.get('resistance', [])
            }
            _save_indicators(
                symbol=symbol,
                indicator_type='support_resistance',
                timestamps=timestamps,
                parameters={'window': 20},
                values=json.dumps(sr_data)
            )
        # Calculate Volume Profile (for latest data)
        volume_profile = calculate_volume_profile(closes, volumes, num_bins=20)
        if volume_profile.get('poc'):
            try:
                _save_indicators(
                    symbol=symbol,
                    indicator_type='volume_profile',
                    timestamps=timestamps,
                    parameters={'num_bins': 20},
                    values= volume_profile.get('poc')
                )
            except Exception as e:
                logger.error(f"Error saving volume profile for {symbol}: {e}")

        logger.info(f"Successfully calculated indicators for {symbol}")

        return {
            "status": "success",
            "symbol": symbol,
            "bars_processed": len(closes)
        }

    except Exception as exc:
        logger.error(f"Error calculating indicators for {symbol}: {exc}")
        raise


@shared_task
def backfill_historical_data(symbol: str, days: int = 365):
    """
    Backfill historical data for a symbol.

    Args:
        symbol: Stock symbol
        days: Number of days to backfill (default 365)
    """
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        logger.info(f"Backfilling {days} days of data for {symbol}")

        sync_historical_bars.delay(
            symbol=symbol,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            timeframe='1D',
        )

        return {"status": "queued", "symbol": symbol, "days": days}

    except Exception as e:
        logger.error(f"Error queuing backfill for {symbol}: {e}")
        raise


@shared_task
def cleanup_old_quotes(days_to_keep: int = 365):
    """
    Clean up old quote data.

    Args:
        days_to_keep: Number of days of data to retain (default 365)
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days_to_keep)

        deleted_count, _ = Quote.objects.filter(
            timestamp__lt=cutoff_date
        ).delete()

        logger.info(f"Cleaned up {deleted_count} old quotes")

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "cutoff_date": cutoff_date.isoformat()
        }

    except Exception as e:
        logger.error(f"Error cleaning up old quotes: {e}")
        raise
