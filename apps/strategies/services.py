"""
Strategy evaluation and management services.

Provides strategy rule evaluation, signal generation, and performance tracking.
"""
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Avg, Sum
import logging

from .models import Strategy
from apps.market_data.indicators import (
    calculate_rsi, calculate_macd, calculate_bollinger_bands,
    calculate_sma, calculate_ema, calculate_atr, calculate_stochastic,
    detect_crossover, detect_support_resistance, calculate_volume_profile
)
from apps.market_data.cache import MarketDataCache
from apps.market_data.provider_manager import get_provider_manager
from apps.portfolios.models import Position

logger = logging.getLogger(__name__)


class StrategyEvaluationError(Exception):
    """Raised when strategy evaluation fails."""
    pass


class StrategyEvaluator:
    """
    Evaluates strategy rules against market data and generates trade signals.
    """

    def __init__(self, strategy: Strategy):
        """
        Initialize evaluator with strategy.

        Args:
            strategy: Strategy instance to evaluate
        """
        self.strategy = strategy
        logger.info(f"Initialized StrategyEvaluator for strategy {strategy.id} ({strategy.name})")

    async def evaluate_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Evaluate strategy rules for a specific symbol.

        Args:
            symbol: Stock symbol to evaluate

        Returns:
            Dictionary with evaluation results:
            - signal: 'buy', 'sell', 'hold'
            - confidence: float (0-1)
            - reasons: list of reasons for signal
            - indicators: dict of calculated indicators
            - current_price: current market price
            - should_execute: bool

        Raises:
            StrategyEvaluationError: If evaluation fails
        """
        try:
            # Get market data
            bars = await self._get_historical_bars(symbol, days=30)
            current_price = await self._get_current_price(symbol)

            if not bars:
                raise StrategyEvaluationError(f"No market data available for {symbol}")

            # Calculate indicators
            indicators = await self._calculate_indicators(bars)

            # Evaluate entry rules
            entry_signal, entry_reasons = self._evaluate_entry_rules(indicators, current_price)

            # Evaluate exit rules (if position exists)
            exit_signal, exit_reasons = await self._evaluate_exit_rules(symbol, indicators, current_price)

            # Determine final signal
            signal, confidence, reasons = self._determine_final_signal(
                entry_signal, entry_reasons,
                exit_signal, exit_reasons
            )

            # Check risk limits
            should_execute = await self._check_risk_limits(signal)

            result = {
                'symbol': symbol,
                'signal': signal,
                'confidence': confidence,
                'reasons': reasons,
                'indicators': indicators,
                'current_price': float(current_price),
                'should_execute': should_execute,
                'timestamp': timezone.now().isoformat()
            }

            logger.info(f"Evaluated {symbol}: {signal} signal (confidence: {confidence})")
            return result

        except Exception as e:
            logger.error(f"Error evaluating {symbol}: {e}")
            raise StrategyEvaluationError(f"Failed to evaluate {symbol}: {e}")

    async def evaluate_watchlist(self) -> List[Dict[str, Any]]:
        """
        Evaluate all symbols in strategy watchlist.

        Returns:
            List of evaluation results for each symbol
        """
        results = []

        for symbol in self.strategy.watchlist:
            try:
                result = await self.evaluate_symbol(symbol)
                results.append(result)
            except Exception as e:
                logger.error(f"Error evaluating {symbol}: {e}")
                results.append({
                    'symbol': symbol,
                    'signal': 'error',
                    'error': str(e)
                })

        return results

    async def _get_historical_bars(self, symbol: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get historical price bars for symbol."""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)

        provider_manager = get_provider_manager()
        bars = await provider_manager.get_historical_bars(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe='1d',
            use_cache=True
        )

        return bars

    async def _get_current_price(self, symbol: str) -> Decimal:
        """Get current market price."""
        # Try cache first
        cached = MarketDataCache.get_quote(symbol)
        if cached:
            return Decimal(str(cached.get('last', cached.get('close', 0))))

        # Fetch from provider
        provider_manager = get_provider_manager()
        quote = await provider_manager.get_quote(symbol, use_cache=True)

        return Decimal(str(quote.get('last', quote.get('close', 0))))

    async def _calculate_indicators(self, bars: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate technical indicators from price bars."""
        if not bars:
            return {}

        # Extract price arrays
        closes = [bar['close'] for bar in bars]
        highs = [bar['high'] for bar in bars]
        lows = [bar['low'] for bar in bars]
        volumes = [bar['volume'] for bar in bars]

        indicators = {}

        # Calculate based on strategy config
        config = self.strategy.config

        # RSI
        if config.get('use_rsi', True):
            period = config.get('rsi_period', 14)
            rsi_values = calculate_rsi(closes, period)
            indicators['rsi'] = rsi_values[-1] if rsi_values else None

        # MACD
        if config.get('use_macd', True):
            macd_data = calculate_macd(closes)
            indicators['macd'] = macd_data['macd'][-1] if macd_data['macd'] else None
            indicators['macd_signal'] = macd_data['signal'][-1] if macd_data['signal'] else None
            indicators['macd_histogram'] = macd_data['histogram'][-1] if macd_data['histogram'] else None

        # Bollinger Bands
        if config.get('use_bollinger', True):
            period = config.get('bb_period', 20)
            bb_data = calculate_bollinger_bands(closes, period)
            indicators['bb_upper'] = bb_data['upper'][-1] if bb_data['upper'] else None
            indicators['bb_middle'] = bb_data['middle'][-1] if bb_data['middle'] else None
            indicators['bb_lower'] = bb_data['lower'][-1] if bb_data['lower'] else None

        # Moving Averages
        if config.get('use_sma', True):
            sma_20 = calculate_sma(closes, 20)
            sma_50 = calculate_sma(closes, 50)
            indicators['sma_20'] = sma_20[-1] if sma_20 else None
            indicators['sma_50'] = sma_50[-1] if sma_50 else None

        if config.get('use_ema', True):
            ema_12 = calculate_ema(closes, 12)
            ema_26 = calculate_ema(closes, 26)
            indicators['ema_12'] = ema_12[-1] if ema_12 else None
            indicators['ema_26'] = ema_26[-1] if ema_26 else None

        # ATR
        if config.get('use_atr', True):
            atr_values = calculate_atr(highs, lows, closes)
            indicators['atr'] = atr_values[-1] if atr_values else None

        # Stochastic
        if config.get('use_stochastic', True):
            stoch_data = calculate_stochastic(highs, lows, closes)
            indicators['stoch_k'] = stoch_data['%K'][-1] if stoch_data['%K'] else None
            indicators['stoch_d'] = stoch_data['%D'][-1] if stoch_data['%D'] else None

        # Crossover Detection (MA crossovers)
        if config.get('use_crossover', True):
            if indicators.get('ema_12') and indicators.get('ema_26'):
                ema_12_series = calculate_ema(closes, 12)
                ema_26_series = calculate_ema(closes, 26)
                crossover_signals = detect_crossover(ema_12_series, ema_26_series)
                indicators['ma_crossover'] = crossover_signals[-1] if crossover_signals else 0
                indicators['ma_crossover_history'] = crossover_signals[-5:] if len(crossover_signals) >= 5 else crossover_signals

        # Support/Resistance Levels
        if config.get('use_support_resistance', True):
            window = config.get('sr_window', 20)
            sr_levels = detect_support_resistance(highs, lows, closes, window=window)
            indicators['support_levels'] = sr_levels.get('support', [])
            indicators['resistance_levels'] = sr_levels.get('resistance', [])

            # Determine if current price is near support/resistance
            current_price = closes[-1]
            if sr_levels.get('support'):
                nearest_support = max([s for s in sr_levels['support'] if s < current_price], default=None)
                if nearest_support:
                    support_distance_pct = ((current_price - nearest_support) / current_price) * 100
                    indicators['nearest_support'] = nearest_support
                    indicators['support_distance_pct'] = support_distance_pct

            if sr_levels.get('resistance'):
                nearest_resistance = min([r for r in sr_levels['resistance'] if r > current_price], default=None)
                if nearest_resistance:
                    resistance_distance_pct = ((nearest_resistance - current_price) / current_price) * 100
                    indicators['nearest_resistance'] = nearest_resistance
                    indicators['resistance_distance_pct'] = resistance_distance_pct

        # Volume Profile
        if config.get('use_volume_profile', True):
            num_bins = config.get('vp_bins', 20)
            volume_profile = calculate_volume_profile(closes, volumes, num_bins=num_bins)
            indicators['volume_profile'] = volume_profile
            indicators['poc'] = volume_profile.get('poc')  # Point of Control

            # Determine if current price is near POC
            if volume_profile.get('poc'):
                poc_distance_pct = ((closes[-1] - volume_profile['poc']) / closes[-1]) * 100
                indicators['poc_distance_pct'] = poc_distance_pct

        # Volume
        indicators['volume'] = volumes[-1] if volumes else None
        indicators['avg_volume'] = sum(volumes[-20:]) / min(20, len(volumes)) if volumes else None

        # Price
        indicators['current_price'] = closes[-1] if closes else None

        return indicators

    def _evaluate_entry_rules(
        self,
        indicators: Dict[str, Any],
        current_price: Decimal
    ) -> Tuple[bool, List[str]]:
        """
        Evaluate entry rules from strategy configuration.

        Returns:
            Tuple of (signal_triggered, reasons)
        """
        entry_rules = self.strategy.entry_rules
        if not entry_rules:
            return False, ["No entry rules configured"]

        reasons = []
        conditions_met = 0
        total_conditions = 0

        # Evaluate each rule
        for rule_name, rule_config in entry_rules.items():
            total_conditions += 1

            if rule_name == 'rsi_oversold':
                threshold = rule_config.get('threshold', 30)
                rsi = indicators.get('rsi')
                if rsi and rsi < threshold:
                    conditions_met += 1
                    reasons.append(f"RSI oversold ({rsi:.2f} < {threshold})")

            elif rule_name == 'rsi_overbought':
                threshold = rule_config.get('threshold', 70)
                rsi = indicators.get('rsi')
                if rsi and rsi > threshold:
                    conditions_met += 1
                    reasons.append(f"RSI overbought ({rsi:.2f} > {threshold})")

            elif rule_name == 'macd_crossover':
                macd = indicators.get('macd')
                signal = indicators.get('macd_signal')
                if macd and signal and macd > signal:
                    conditions_met += 1
                    reasons.append("MACD bullish crossover")

            elif rule_name == 'price_above_sma':
                period = rule_config.get('period', 20)
                sma = indicators.get(f'sma_{period}')
                if sma and float(current_price) > sma:
                    conditions_met += 1
                    reasons.append(f"Price above SMA{period}")

            elif rule_name == 'price_below_sma':
                period = rule_config.get('period', 20)
                sma = indicators.get(f'sma_{period}')
                if sma and float(current_price) < sma:
                    conditions_met += 1
                    reasons.append(f"Price below SMA{period}")

            elif rule_name == 'volume_surge':
                multiplier = rule_config.get('multiplier', 1.5)
                volume = indicators.get('volume')
                avg_volume = indicators.get('avg_volume')
                if volume and avg_volume and volume > avg_volume * multiplier:
                    conditions_met += 1
                    reasons.append(f"Volume surge ({volume / avg_volume:.2f}x average)")

            elif rule_name == 'bb_lower_touch':
                price = float(current_price)
                bb_lower = indicators.get('bb_lower')
                if bb_lower and price <= bb_lower * 1.01:  # Within 1% of lower band
                    conditions_met += 1
                    reasons.append("Price near Bollinger lower band")

            elif rule_name == 'bb_upper_touch':
                price = float(current_price)
                bb_upper = indicators.get('bb_upper')
                if bb_upper and price >= bb_upper * 0.99:  # Within 1% of upper band
                    conditions_met += 1
                    reasons.append("Price near Bollinger upper band")

            elif rule_name == 'ma_bullish_crossover':
                # EMA12 crosses above EMA26
                crossover = indicators.get('ma_crossover')
                if crossover == 1:
                    conditions_met += 1
                    reasons.append("Bullish MA crossover detected")

            elif rule_name == 'ma_bearish_crossover':
                # EMA12 crosses below EMA26
                crossover = indicators.get('ma_crossover')
                if crossover == -1:
                    conditions_met += 1
                    reasons.append("Bearish MA crossover detected")

            elif rule_name == 'price_near_support':
                # Price is within threshold % of nearest support
                threshold_pct = rule_config.get('threshold_pct', 2.0)
                support_distance = indicators.get('support_distance_pct')
                if support_distance and support_distance <= threshold_pct:
                    conditions_met += 1
                    reasons.append(f"Price near support ({support_distance:.2f}% away)")

            elif rule_name == 'price_near_resistance':
                # Price is within threshold % of nearest resistance
                threshold_pct = rule_config.get('threshold_pct', 2.0)
                resistance_distance = indicators.get('resistance_distance_pct')
                if resistance_distance and resistance_distance <= threshold_pct:
                    conditions_met += 1
                    reasons.append(f"Price near resistance ({resistance_distance:.2f}% away)")

            elif rule_name == 'price_at_poc':
                # Price is near Point of Control (high volume area)
                threshold_pct = rule_config.get('threshold_pct', 1.5)
                poc_distance = indicators.get('poc_distance_pct')
                if poc_distance and abs(poc_distance) <= threshold_pct:
                    conditions_met += 1
                    reasons.append(f"Price near POC ({abs(poc_distance):.2f}% away)")

            elif rule_name == 'breakout_above_resistance':
                # Price breaks above resistance level
                nearest_resistance = indicators.get('nearest_resistance')
                if nearest_resistance and float(current_price) > nearest_resistance:
                    conditions_met += 1
                    reasons.append(f"Breakout above resistance (${nearest_resistance:.2f})")

            elif rule_name == 'breakdown_below_support':
                # Price breaks below support level
                nearest_support = indicators.get('nearest_support')
                if nearest_support and float(current_price) < nearest_support:
                    conditions_met += 1
                    reasons.append(f"Breakdown below support (${nearest_support:.2f})")

        # Check if required conditions met
        required_conditions = entry_rules.get('_required_conditions', total_conditions)
        signal_triggered = conditions_met >= required_conditions

        if not signal_triggered:
            reasons.append(f"Only {conditions_met}/{required_conditions} conditions met")

        return signal_triggered, reasons

    async def _evaluate_exit_rules(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        current_price: Decimal
    ) -> Tuple[bool, List[str]]:
        """
        Evaluate exit rules for existing position.

        Returns:
            Tuple of (should_exit, reasons)
        """
        # Check if position exists
        if not self.strategy.portfolio:
            return False, []

        position = Position.objects.filter(
            portfolio=self.strategy.portfolio,
            symbol=symbol,
            quantity__gt=0
        ).first()

        if not position:
            return False, []

        exit_rules = self.strategy.exit_rules
        if not exit_rules:
            return False, []

        reasons = []
        should_exit = False

        # Evaluate exit conditions
        for rule_name, rule_config in exit_rules.items():
            if rule_name == 'profit_target':
                target_pct = rule_config.get('percentage', 5.0)
                profit_pct = ((current_price - position.avg_price) / position.avg_price) * 100
                if profit_pct >= target_pct:
                    should_exit = True
                    reasons.append(f"Profit target reached ({profit_pct:.2f}% >= {target_pct}%)")

            elif rule_name == 'stop_loss':
                stop_pct = rule_config.get('percentage', 2.0)
                loss_pct = ((position.avg_price - current_price) / position.avg_price) * 100
                if loss_pct >= stop_pct:
                    should_exit = True
                    reasons.append(f"Stop loss triggered ({loss_pct:.2f}% >= {stop_pct}%)")

            elif rule_name == 'trailing_stop':
                trail_pct = rule_config.get('percentage', 3.0)
                # Simplified - would need to track highest price since entry
                # For now, use static stop
                loss_pct = ((position.avg_price - current_price) / position.avg_price) * 100
                if loss_pct >= trail_pct:
                    should_exit = True
                    reasons.append(f"Trailing stop triggered ({loss_pct:.2f}%)")

            elif rule_name == 'rsi_exit':
                threshold = rule_config.get('threshold', 70)
                rsi = indicators.get('rsi')
                if rsi and rsi > threshold:
                    should_exit = True
                    reasons.append(f"RSI exit signal ({rsi:.2f} > {threshold})")

        return should_exit, reasons

    def _determine_final_signal(
        self,
        entry_signal: bool,
        entry_reasons: List[str],
        exit_signal: bool,
        exit_reasons: List[str]
    ) -> Tuple[str, float, List[str]]:
        """
        Determine final trading signal from entry/exit evaluations.

        Returns:
            Tuple of (signal, confidence, reasons)
        """
        if exit_signal:
            # Exit signals take priority
            confidence = min(1.0, len(exit_reasons) * 0.3)
            return 'sell', confidence, exit_reasons

        elif entry_signal:
            confidence = min(1.0, len(entry_reasons) * 0.25)
            return 'buy', confidence, entry_reasons

        else:
            return 'hold', 0.0, ['No signal conditions met']

    async def _check_risk_limits(self, signal: str) -> bool:
        """
        Check if trade would violate risk limits.

        Returns:
            True if trade should be executed
        """
        if signal == 'hold':
            return False

        if not self.strategy.portfolio:
            return True  # No portfolio to check

        # Check max positions
        current_positions = Position.objects.filter(
            portfolio=self.strategy.portfolio,
            quantity__gt=0
        ).count()

        if signal == 'buy' and current_positions >= self.strategy.max_positions:
            logger.warning(f"Max positions limit reached ({current_positions}/{self.strategy.max_positions})")
            return False

        # Check daily loss limit
        # TODO: Implement daily loss tracking

        return True


def calculate_strategy_performance(strategy: Strategy) -> Dict[str, Any]:
    """
    Calculate performance metrics for a strategy.

    Args:
        strategy: Strategy instance

    Returns:
        Dictionary with performance metrics
    """
    metrics = {
        'total_trades': strategy.total_trades,
        'winning_trades': strategy.winning_trades,
        'losing_trades': strategy.total_trades - strategy.winning_trades,
        'win_rate': float(strategy.win_rate),
        'total_pnl': float(strategy.total_pnl),
        'sharpe_ratio': float(strategy.sharpe_ratio) if strategy.sharpe_ratio else None,
        'avg_pnl_per_trade': float(strategy.total_pnl / strategy.total_trades) if strategy.total_trades > 0 else 0
    }

    return metrics


def update_strategy_performance(strategy: Strategy, trade_pnl: Decimal, is_winning: bool):
    """
    Update strategy performance metrics after a trade.

    Args:
        strategy: Strategy instance
        trade_pnl: Trade profit/loss
        is_winning: Whether trade was profitable
    """
    strategy.total_trades += 1
    if is_winning:
        strategy.winning_trades += 1

    strategy.total_pnl += trade_pnl
    strategy.win_rate = (Decimal(strategy.winning_trades) / Decimal(strategy.total_trades)) * 100

    strategy.save()

    logger.info(f"Updated strategy {strategy.id} performance: {strategy.total_trades} trades, {strategy.win_rate}% win rate")
