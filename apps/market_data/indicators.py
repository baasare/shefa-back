"""
Technical indicator calculations for market data.

This module provides functions to calculate common technical indicators
like RSI, MACD, Bollinger Bands, etc.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """
    Calculate Relative Strength Index (RSI).

    Args:
        prices: List of closing prices
        period: RSI period (default 14)

    Returns:
        List of RSI values
    """
    if len(prices) < period + 1:
        return [None] * len(prices)

    df = pd.DataFrame(prices, columns=['close'])
    delta = df['close'].diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi.fillna(0).tolist()


def calculate_macd(
    prices: List[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Tuple[List[float], List[float], List[float]]:
    """
    Calculate MACD (Moving Average Convergence Divergence).

    Args:
        prices: List of closing prices
        fast_period: Fast EMA period (default 12)
        slow_period: Slow EMA period (default 26)
        signal_period: Signal line period (default 9)

    Returns:
        Tuple of (macd_line, signal_line, histogram)
    """
    if len(prices) < slow_period:
        none_list = [None] * len(prices)
        return none_list, none_list, none_list

    df = pd.DataFrame(prices, columns=['close'])

    # Calculate EMAs
    ema_fast = df['close'].ewm(span=fast_period, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow_period, adjust=False).mean()

    # MACD line
    macd_line = ema_fast - ema_slow

    # Signal line
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

    # Histogram
    histogram = macd_line - signal_line

    return (
        macd_line.fillna(0).tolist(),
        signal_line.fillna(0).tolist(),
        histogram.fillna(0).tolist()
    )


def calculate_bollinger_bands(
    prices: List[float],
    period: int = 20,
    std_dev: float = 2.0
) -> Tuple[List[float], List[float], List[float]]:
    """
    Calculate Bollinger Bands.

    Args:
        prices: List of closing prices
        period: Period for moving average (default 20)
        std_dev: Number of standard deviations (default 2.0)

    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    if len(prices) < period:
        none_list = [None] * len(prices)
        return none_list, none_list, none_list

    df = pd.DataFrame(prices, columns=['close'])

    # Middle band (SMA)
    middle_band = df['close'].rolling(window=period).mean()

    # Standard deviation
    std = df['close'].rolling(window=period).std()

    # Upper and lower bands
    upper_band = middle_band + (std * std_dev)
    lower_band = middle_band - (std * std_dev)

    return (
        upper_band.fillna(0).tolist(),
        middle_band.fillna(0).tolist(),
        lower_band.fillna(0).tolist()
    )


def calculate_sma(prices: List[float], period: int = 20) -> List[float]:
    """
    Calculate Simple Moving Average (SMA).

    Args:
        prices: List of closing prices
        period: Period for moving average

    Returns:
        List of SMA values
    """
    if len(prices) < period:
        return [None] * len(prices)

    df = pd.DataFrame(prices, columns=['close'])
    sma = df['close'].rolling(window=period).mean()

    return sma.fillna(0).tolist()


def calculate_ema(prices: List[float], period: int = 20) -> List[float]:
    """
    Calculate Exponential Moving Average (EMA).

    Args:
        prices: List of closing prices
        period: Period for EMA

    Returns:
        List of EMA values
    """
    if len(prices) < period:
        return [None] * len(prices)

    df = pd.DataFrame(prices, columns=['close'])
    ema = df['close'].ewm(span=period, adjust=False).mean()

    return ema.fillna(0).tolist()


def calculate_atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14
) -> List[float]:
    """
    Calculate Average True Range (ATR).

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        period: ATR period (default 14)

    Returns:
        List of ATR values
    """
    if len(highs) < period or len(lows) < period or len(closes) < period:
        return [None] * len(closes)

    df = pd.DataFrame({
        'high': highs,
        'low': lows,
        'close': closes
    })

    # True Range calculation
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['close'].shift())
    df['tr3'] = abs(df['low'] - df['close'].shift())

    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)

    # ATR is the EMA of True Range
    atr = df['tr'].ewm(span=period, adjust=False).mean()

    return atr.fillna(0).tolist()


def calculate_stochastic(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
    smooth_k: int = 3,
    smooth_d: int = 3
) -> Tuple[List[float], List[float]]:
    """
    Calculate Stochastic Oscillator (%K and %D).

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        period: Lookback period (default 14)
        smooth_k: K line smoothing (default 3)
        smooth_d: D line smoothing (default 3)

    Returns:
        Tuple of (%K, %D)
    """
    if len(highs) < period or len(lows) < period or len(closes) < period:
        none_list = [None] * len(closes)
        return none_list, none_list

    df = pd.DataFrame({
        'high': highs,
        'low': lows,
        'close': closes
    })

    # Lowest low and highest high over period
    df['lowest_low'] = df['low'].rolling(window=period).min()
    df['highest_high'] = df['high'].rolling(window=period).max()

    # %K calculation
    df['k'] = 100 * ((df['close'] - df['lowest_low']) / (df['highest_high'] - df['lowest_low']))

    # Smooth %K
    df['k_smooth'] = df['k'].rolling(window=smooth_k).mean()

    # %D is SMA of %K
    df['d'] = df['k_smooth'].rolling(window=smooth_d).mean()

    return (
        df['k_smooth'].fillna(0).tolist(),
        df['d'].fillna(0).tolist()
    )


def detect_crossover(series1: List[float], series2: List[float]) -> List[int]:
    """
    Detect crossover between two series.

    Args:
        series1: First series (e.g., fast MA)
        series2: Second series (e.g., slow MA)

    Returns:
        List of crossover signals:
        - 1: series1 crosses above series2 (bullish)
        - -1: series1 crosses below series2 (bearish)
        - 0: no crossover
    """
    if len(series1) != len(series2) or len(series1) < 2:
        return [0] * len(series1)

    df = pd.DataFrame({
        's1': series1,
        's2': series2
    })

    # Difference between series
    df['diff'] = df['s1'] - df['s2']

    # Detect crossovers
    signals = []
    for i in range(len(df)):
        if i == 0:
            signals.append(0)
        else:
            prev_diff = df['diff'].iloc[i - 1]
            curr_diff = df['diff'].iloc[i]

            if pd.notna(prev_diff) and pd.notna(curr_diff):
                # Bullish crossover
                if prev_diff <= 0 and curr_diff > 0:
                    signals.append(1)
                # Bearish crossover
                elif prev_diff >= 0 and curr_diff < 0:
                    signals.append(-1)
                else:
                    signals.append(0)
            else:
                signals.append(0)

    return signals


def detect_support_resistance(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    window: int = 20,
    tolerance: float = 0.02
) -> Dict[str, List[float]]:
    """
    Detect support and resistance levels.

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        window: Window for local extrema (default 20)
        tolerance: Price tolerance for clustering (default 2%)

    Returns:
        Dictionary with 'support' and 'resistance' levels
    """
    if len(highs) < window or len(lows) < window:
        return {'support': [], 'resistance': []}

    df = pd.DataFrame({
        'high': highs,
        'low': lows,
        'close': closes
    })

    # Find local maxima (resistance)
    df['is_resistance'] = (
        (df['high'] >= df['high'].shift(1)) &
        (df['high'] >= df['high'].shift(-1)) &
        (df['high'] >= df['high'].rolling(window=window, center=True).max() * 0.98)
    )

    # Find local minima (support)
    df['is_support'] = (
        (df['low'] <= df['low'].shift(1)) &
        (df['low'] <= df['low'].shift(-1)) &
        (df['low'] <= df['low'].rolling(window=window, center=True).min() * 1.02)
    )

    resistance_levels = df[df['is_resistance']]['high'].tolist()
    support_levels = df[df['is_support']]['low'].tolist()

    # Cluster nearby levels
    resistance_levels = _cluster_levels(resistance_levels, tolerance)
    support_levels = _cluster_levels(support_levels, tolerance)

    return {
        'support': support_levels,
        'resistance': resistance_levels
    }


def _cluster_levels(levels: List[float], tolerance: float) -> List[float]:
    """
    Cluster nearby price levels.

    Args:
        levels: List of price levels
        tolerance: Clustering tolerance (percentage)

    Returns:
        Clustered levels
    """
    if not levels:
        return []

    levels = sorted(levels)
    clustered = []
    current_cluster = [levels[0]]

    for i in range(1, len(levels)):
        # Check if within tolerance of current cluster
        if abs(levels[i] - current_cluster[-1]) / current_cluster[-1] <= tolerance:
            current_cluster.append(levels[i])
        else:
            # Save average of current cluster
            clustered.append(sum(current_cluster) / len(current_cluster))
            current_cluster = [levels[i]]

    # Add last cluster
    if current_cluster:
        clustered.append(sum(current_cluster) / len(current_cluster))

    return clustered


def calculate_volume_profile(
    closes: List[float],
    volumes: List[int],
    num_bins: int = 20
) -> Dict[str, Any]:
    """
    Calculate volume profile (Volume by Price).

    Args:
        closes: List of closing prices
        volumes: List of volumes
        num_bins: Number of price bins (default 20)

    Returns:
        Dictionary with volume profile data
    """
    if len(closes) != len(volumes) or len(closes) < num_bins:
        return {'bins': [], 'volumes': [], 'poc': None}

    df = pd.DataFrame({
        'close': closes,
        'volume': volumes
    })

    # Create price bins
    min_price = df['close'].min()
    max_price = df['close'].max()
    bins = pd.cut(df['close'], bins=num_bins)

    # Sum volume for each bin
    volume_by_price = df.groupby(bins)['volume'].sum()

    # Point of Control (highest volume price level)
    poc_bin = volume_by_price.idxmax()
    poc_price = (poc_bin.left + poc_bin.right) / 2

    return {
        'bins': [f"{interval.left:.2f}-{interval.right:.2f}" for interval in volume_by_price.index],
        'volumes': volume_by_price.tolist(),
        'poc': float(poc_price)
    }
