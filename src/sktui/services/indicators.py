"""Technical Indicators Engine for SKTUI.

Pure-Python implementations of common trading indicators.
All functions return lists aligned 1-to-1 with input prices,
with None padding where insufficient data exists for computation.

Indicators:
  - EMA (Exponential Moving Average)
  - SMA (Simple Moving Average)
  - VWAP (Volume-Weighted Average Price)
  - RSI (Relative Strength Index)
  - ATR (Average True Range)
  - MACD (Moving Average Convergence/Divergence)
  - Bollinger Bands
"""
from __future__ import annotations

from typing import Sequence


def ema(values: Sequence[float], period: int) -> list[float | None]:
    """Exponential Moving Average (EMA).

    Args:
        values: Sequence of closing prices.
        period: Lookback window.

    Returns:
        List of EMA values, None-padded for insufficient history.
    """
    if not values:
        return []
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    first_sma = sum(values[:period]) / period
    result[period - 1] = first_sma
    k = 2.0 / (period + 1.0)
    for i in range(period, len(values)):
        prev = result[i - 1]
        if prev is not None:
            result[i] = (values[i] - prev) * k + prev
    return result


def sma(values: Sequence[float], period: int) -> list[float | None]:
    """Simple Moving Average (SMA).

    Args:
        values: Sequence of closing prices.
        period: Lookback window.

    Returns:
        List of SMA values, None-padded for insufficient history.
    """
    result: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < period:
            result.append(None)
        else:
            window = values[i + 1 - period: i + 1]
            result.append(sum(window) / period)
    return result


def rsi(values: Sequence[float], period: int = 14) -> list[float | None]:
    """Relative Strength Index (RSI).

    Args:
        values: Sequence of closing prices.
        period: Lookback window (default 14).

    Returns:
        List of RSI values (0–100), None-padded for insufficient history.
    """
    if len(values) <= period:
        return [None] * len(values)
    result: list[float | None] = [None] * len(values)
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    if len(gains) < period:
        return result
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(period + 1, len(values)):
        g = gains[i - 1]
        l = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - (100.0 / (1.0 + rs))
    return result


def vwap(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
) -> list[float | None]:
    """Volume-Weighted Average Price (VWAP).

    Args:
        closes: Closing prices.
        highs:  High prices.
        lows:   Low prices.
        volumes: Trade volumes.

    Returns:
        Cumulative VWAP series.
    """
    result: list[float | None] = []
    cum_tp_vol = 0.0
    cum_vol = 0.0
    for c, h, l, v in zip(closes, highs, lows, volumes):
        tp = (h + l + c) / 3.0
        vol = float(v or 0.0)
        cum_tp_vol += tp * vol
        cum_vol += vol
        result.append(cum_tp_vol / cum_vol if cum_vol > 0 else None)
    return result


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float | None]:
    """Average True Range (ATR).

    Args:
        highs:  High prices.
        lows:   Low prices.
        closes: Closing prices.
        period: Lookback window (default 14).

    Returns:
        List of ATR values, None-padded for insufficient history.
    """
    n = len(closes)
    if n < 2:
        return [None] * n
    true_ranges: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)
    result: list[float | None] = [None] * n
    if len(true_ranges) < period:
        return result
    first_atr = sum(true_ranges[:period]) / period
    result[period] = first_atr
    k = 1.0 / period
    for i in range(period + 1, n):
        prev = result[i - 1]
        if prev is not None:
            result[i] = true_ranges[i - 1] * k + prev * (1.0 - k)
    return result


def macd(
    values: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Moving Average Convergence/Divergence (MACD).

    Args:
        values: Closing prices.
        fast:   Fast EMA period (default 12).
        slow:   Slow EMA period (default 26).
        signal: Signal EMA period (default 9).

    Returns:
        Tuple of (macd_line, signal_line, histogram) — all None-padded.
    """
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    macd_line: list[float | None] = []
    for f, s in zip(fast_ema, slow_ema):
        if f is not None and s is not None:
            macd_line.append(f - s)
        else:
            macd_line.append(None)
    filled_macd = [v if v is not None else 0.0 for v in macd_line]
    raw_signal = ema(filled_macd, signal)
    signal_line: list[float | None] = [
        raw_signal[i] if macd_line[i] is not None else None
        for i in range(len(raw_signal))
    ]
    histogram: list[float | None] = []
    for m, s in zip(macd_line, signal_line):
        if m is not None and s is not None:
            histogram.append(m - s)
        else:
            histogram.append(None)
    return macd_line, signal_line, histogram


def bollinger_bands(
    values: Sequence[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Bollinger Bands (upper, middle/SMA, lower).

    Args:
        values:  Closing prices.
        period:  SMA window (default 20).
        std_dev: Standard deviation multiplier (default 2.0).

    Returns:
        Tuple of (upper_band, middle_band, lower_band).
    """
    import math
    middle = sma(values, period)
    upper: list[float | None] = []
    lower: list[float | None] = []
    for i, mid in enumerate(middle):
        if mid is None or i + 1 < period:
            upper.append(None)
            lower.append(None)
        else:
            window = list(values[i + 1 - period: i + 1])
            variance = sum((x - mid) ** 2 for x in window) / period
            sigma = math.sqrt(variance)
            upper.append(mid + std_dev * sigma)
            lower.append(mid - std_dev * sigma)
    return upper, middle, lower


def support_resistance(
    highs: Sequence[float],
    lows: Sequence[float],
    window: int = 5,
) -> tuple[list[float], list[float]]:
    """Identify local support and resistance price levels.

    Args:
        highs:  High prices.
        lows:   Low prices.
        window: Local extrema window half-size (default 5).

    Returns:
        Tuple of (resistance_levels, support_levels) — unique, sorted.
    """
    resistance_levels: list[float] = []
    support_levels: list[float] = []
    n = len(highs)
    for i in range(window, n - window):
        local_high = highs[i]
        local_low = lows[i]
        if all(local_high >= highs[j] for j in range(i - window, i + window + 1) if j != i):
            resistance_levels.append(local_high)
        if all(local_low <= lows[j] for j in range(i - window, i + window + 1) if j != i):
            support_levels.append(local_low)
    return sorted(set(resistance_levels)), sorted(set(support_levels))
