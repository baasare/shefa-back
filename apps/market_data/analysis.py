"""
Chart analysis and pattern detection.

Provides technical chart pattern recognition and trend analysis.
"""
from typing import Dict, Any, List
import numpy as np
import logging

logger = logging.getLogger(__name__)


class ChartAnalyzer:
    """Analyzes price charts for patterns and trends."""

    def __init__(self, bars: List[Dict[str, Any]]):
        """
        Initialize with price bars.

        Args:
            bars: List of OHLCV bars
        """
        self.bars = bars
        self.closes = np.array([bar['close'] for bar in bars])
        self.highs = np.array([bar['high'] for bar in bars])
        self.lows = np.array([bar['low'] for bar in bars])
        self.opens = np.array([bar['open'] for bar in bars])
        self.volumes = np.array([bar['volume'] for bar in bars])

    def analyze(self) -> Dict[str, Any]:
        """
        Perform complete chart analysis.

        Returns:
            Dictionary with analysis results
        """
        return {
            'trend': self.identify_trend(),
            'support_resistance': self.find_support_resistance(),
            'patterns': self.detect_patterns(),
            'volatility': self.calculate_volatility(),
            'volume_analysis': self.analyze_volume()
        }

    def identify_trend(self) -> Dict[str, Any]:
        """Identify current trend direction."""
        if len(self.closes) < 50:
            return {'direction': 'unknown', 'strength': 0}

        # Use SMA crossover
        sma_20 = np.convolve(self.closes, np.ones(20)/20, mode='valid')
        sma_50 = np.convolve(self.closes, np.ones(50)/50, mode='valid')

        if len(sma_20) == 0 or len(sma_50) == 0:
            return {'direction': 'unknown', 'strength': 0}

        current_20 = sma_20[-1]
        current_50 = sma_50[-1]
        current_price = self.closes[-1]

        if current_price > current_20 > current_50:
            direction = 'bullish'
            strength = min(100, ((current_price - current_50) / current_50) * 100 * 10)
        elif current_price < current_20 < current_50:
            direction = 'bearish'
            strength = min(100, ((current_50 - current_price) / current_50) * 100 * 10)
        else:
            direction = 'neutral'
            strength = 0

        return {
            'direction': direction,
            'strength': float(strength),
            'sma_20': float(current_20),
            'sma_50': float(current_50)
        }

    def find_support_resistance(self, window: int = 20) -> Dict[str, List[float]]:
        """Find support and resistance levels."""
        if len(self.bars) < window:
            return {'support': [], 'resistance': []}

        support_levels = []
        resistance_levels = []

        # Find local minima (support)
        for i in range(window, len(self.lows) - window):
            if self.lows[i] == min(self.lows[i-window:i+window+1]):
                support_levels.append(float(self.lows[i]))

        # Find local maxima (resistance)
        for i in range(window, len(self.highs) - window):
            if self.highs[i] == max(self.highs[i-window:i+window+1]):
                resistance_levels.append(float(self.highs[i]))

        # Cluster nearby levels
        support_levels = self._cluster_levels(support_levels)
        resistance_levels = self._cluster_levels(resistance_levels)

        return {
            'support': sorted(support_levels)[-3:],  # Top 3
            'resistance': sorted(resistance_levels, reverse=True)[:3]  # Top 3
        }

    def detect_patterns(self) -> List[Dict[str, Any]]:
        """Detect chart patterns."""
        patterns = []

        # Double bottom
        if self._detect_double_bottom():
            patterns.append({'pattern': 'double_bottom', 'signal': 'bullish'})

        # Double top
        if self._detect_double_top():
            patterns.append({'pattern': 'double_top', 'signal': 'bearish'})

        # Head and shoulders
        if self._detect_head_shoulders():
            patterns.append({'pattern': 'head_and_shoulders', 'signal': 'bearish'})

        # Bull flag
        if self._detect_bull_flag():
            patterns.append({'pattern': 'bull_flag', 'signal': 'bullish'})

        return patterns

    def calculate_volatility(self) -> Dict[str, float]:
        """Calculate volatility metrics."""
        if len(self.closes) < 20:
            return {'std_dev': 0, 'average_range': 0}

        returns = np.diff(self.closes) / self.closes[:-1]
        std_dev = float(np.std(returns) * 100)

        ranges = self.highs - self.lows
        avg_range = float(np.mean(ranges[-20:]))

        return {
            'std_dev': std_dev,
            'average_range': avg_range,
            'is_high': std_dev > 2.0
        }

    def analyze_volume(self) -> Dict[str, Any]:
        """Analyze volume patterns."""
        if len(self.volumes) < 20:
            return {'trend': 'unknown', 'surge': False}

        avg_volume = np.mean(self.volumes[-20:])
        current_volume = self.volumes[-1]

        volume_trend = 'increasing' if current_volume > avg_volume else 'decreasing'
        surge = current_volume > avg_volume * 2

        return {
            'current': float(current_volume),
            'average': float(avg_volume),
            'trend': volume_trend,
            'surge': surge
        }

    def _detect_double_bottom(self) -> bool:
        """Detect double bottom pattern."""
        if len(self.lows) < 50:
            return False

        recent_lows = self.lows[-50:]
        min_idx = np.argmin(recent_lows)

        # Look for another low nearby
        for i in range(max(0, min_idx-20), min(len(recent_lows), min_idx+20)):
            if i != min_idx and abs(recent_lows[i] - recent_lows[min_idx]) < recent_lows[min_idx] * 0.02:
                return True

        return False

    def _detect_double_top(self) -> bool:
        """Detect double top pattern."""
        if len(self.highs) < 50:
            return False

        recent_highs = self.highs[-50:]
        max_idx = np.argmax(recent_highs)

        for i in range(max(0, max_idx-20), min(len(recent_highs), max_idx+20)):
            if i != max_idx and abs(recent_highs[i] - recent_highs[max_idx]) < recent_highs[max_idx] * 0.02:
                return True

        return False

    def _detect_head_shoulders(self) -> bool:
        """Detect head and shoulders pattern (simplified)."""
        if len(self.highs) < 60:
            return False

        # Look for three peaks with middle one highest
        recent_highs = self.highs[-60:]

        # Find peaks
        peaks = []
        for i in range(10, len(recent_highs)-10):
            if recent_highs[i] > max(recent_highs[i-10:i]) and recent_highs[i] > max(recent_highs[i+1:i+11]):
                peaks.append((i, recent_highs[i]))

        if len(peaks) >= 3:
            # Check if middle peak is highest
            if peaks[1][1] > peaks[0][1] and peaks[1][1] > peaks[2][1]:
                return True

        return False

    def _detect_bull_flag(self) -> bool:
        """Detect bull flag pattern."""
        if len(self.closes) < 30:
            return False

        # Strong uptrend followed by consolidation
        first_half = self.closes[-30:-15]
        second_half = self.closes[-15:]

        # Check for uptrend in first half
        uptrend = first_half[-1] > first_half[0] * 1.05

        # Check for consolidation in second half
        consolidation = np.std(second_half) < np.std(first_half) * 0.5

        return uptrend and consolidation

    def _cluster_levels(self, levels: List[float], threshold: float = 0.02) -> List[float]:
        """Cluster nearby price levels."""
        if not levels:
            return []

        levels = sorted(levels)
        clustered = [levels[0]]

        for level in levels[1:]:
            if abs(level - clustered[-1]) / clustered[-1] > threshold:
                clustered.append(level)

        return clustered


def analyze_symbol(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convenience function to analyze a symbol's chart.

    Args:
        bars: Historical price bars

    Returns:
        Complete analysis results
    """
    analyzer = ChartAnalyzer(bars)
    return analyzer.analyze()


def detect_trend(prices: List[float]) -> str:
    """
    Detect trend direction from price data.

    Args:
        prices: List of closing prices

    Returns:
        Trend direction: 'bullish', 'bearish', or 'neutral'
    """
    if len(prices) < 50:
        return 'neutral'

    prices_array = np.array(prices)

    # Use SMA crossover
    sma_20 = np.convolve(prices_array, np.ones(20)/20, mode='valid')
    sma_50 = np.convolve(prices_array, np.ones(50)/50, mode='valid')

    if len(sma_20) == 0 or len(sma_50) == 0:
        return 'neutral'

    current_20 = sma_20[-1]
    current_50 = sma_50[-1]
    current_price = prices_array[-1]

    if current_price > current_20 > current_50:
        return 'bullish'
    elif current_price < current_20 < current_50:
        return 'bearish'
    else:
        return 'neutral'


def detect_double_top(prices: List[float]) -> bool:
    """
    Detect double top pattern in price data.

    Args:
        prices: List of closing prices

    Returns:
        True if double top pattern detected
    """
    if len(prices) < 50:
        return False

    prices_array = np.array(prices)
    recent_prices = prices_array[-50:]

    max_idx = np.argmax(recent_prices)

    # Look for another high nearby
    for i in range(max(0, max_idx-20), min(len(recent_prices), max_idx+20)):
        if i != max_idx and abs(recent_prices[i] - recent_prices[max_idx]) < recent_prices[max_idx] * 0.02:
            return True

    return False


def detect_double_bottom(prices: List[float]) -> bool:
    """
    Detect double bottom pattern in price data.

    Args:
        prices: List of closing prices

    Returns:
        True if double bottom pattern detected
    """
    if len(prices) < 50:
        return False

    prices_array = np.array(prices)
    recent_prices = prices_array[-50:]

    min_idx = np.argmin(recent_prices)

    # Look for another low nearby
    for i in range(max(0, min_idx-20), min(len(recent_prices), min_idx+20)):
        if i != min_idx and abs(recent_prices[i] - recent_prices[min_idx]) < recent_prices[min_idx] * 0.02:
            return True

    return False
