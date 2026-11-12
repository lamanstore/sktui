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

import math
from typing import Any, Sequence


def _clean_float(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


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
    n = len(values)
    result: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return result

    cleaned = [_clean_float(v) for v in values]
    # Find the first window of `period` contiguous valid values
    seed_end = -1
    valid_run = 0
    for i, val in enumerate(cleaned):
        if val is not None:
            valid_run += 1
            if valid_run == period:
                seed_end = i
                break
        else:
            valid_run = 0

    if seed_end < 0:
        return result

    seed_slice = [cleaned[j] for j in range(seed_end - period + 1, seed_end + 1)]
    first_sma = sum(x for x in seed_slice if x is not None) / period
    result[seed_end] = first_sma
    k = 2.0 / (period + 1.0)
    prev = first_sma
    for i in range(seed_end + 1, n):
        cur = cleaned[i]
        if cur is not None:
            prev = (cur - prev) * k + prev
            result[i] = prev
        else:
            result[i] = None
    return result


def sma(values: Sequence[float], period: int) -> list[float | None]:
    """Simple Moving Average (SMA).

    Args:
        values: Sequence of closing prices.
        period: Lookback window.

    Returns:
        List of SMA values, None-padded for insufficient history.
    """
    if not values:
        return []
    if period <= 0:
        return [None] * len(values)
    cleaned = [_clean_float(v) for v in values]
    result: list[float | None] = []
    for i in range(len(cleaned)):
        if i + 1 < period:
            result.append(None)
        else:
            window = cleaned[i + 1 - period: i + 1]
            if any(x is None for x in window):
                result.append(None)
            else:
                result.append(sum(x for x in window if x is not None) / period)
    return result


def rsi(values: Sequence[float], period: int = 14) -> list[float | None]:
    """Relative Strength Index (RSI).

    Args:
        values: Sequence of closing prices.
        period: Lookback window (default 14).

    Returns:
        List of RSI values (0–100), None-padded for insufficient history.
    """
    if not values:
        return []
    if period <= 0 or len(values) <= period:
        return [None] * len(values)
    result: list[float | None] = [None] * len(values)
    cleaned = [_clean_float(v) for v in values]
    if any(x is None for x in cleaned[:period + 1]):
        return result
    gains: list[float] = []
    losses: list[float] = []
    last_valid = cleaned[0]
    assert last_valid is not None
    for i in range(1, len(cleaned)):
        cur = cleaned[i]
        if cur is None:
            gains.append(0.0)
            losses.append(0.0)
        else:
            diff = cur - last_valid
            last_valid = cur
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))
    if len(gains) < period:
        return result
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        result[period] = 50.0 if avg_gain == 0 else 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(period + 1, len(values)):
        if cleaned[i] is None:
            result[i] = None
            continue
        g = gains[i - 1]
        l = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        if avg_loss == 0:
            result[i] = 50.0 if avg_gain == 0 else 100.0
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
        fc = _clean_float(c)
        fh = _clean_float(h)
        fl = _clean_float(l)
        fv = _clean_float(v)
        if fc is None or fh is None or fl is None:
            result.append(cum_tp_vol / cum_vol if cum_vol > 0 else None)
            continue
        tp = (fh + fl + fc) / 3.0
        vol = max(0.0, fv if fv is not None else 0.0)
        cum_tp_vol += tp * vol
        cum_vol += vol
        result.append(cum_tp_vol / cum_vol if cum_vol > 0 else tp)
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
    n = min(len(closes), len(highs), len(lows))
    if period <= 0 or n < 2:
        return [None] * len(closes)
    true_ranges: list[float] = []
    for i in range(1, n):
        hi = _clean_float(highs[i])
        lo = _clean_float(lows[i])
        prev_c = _clean_float(closes[i - 1])
        if hi is None or lo is None or prev_c is None:
            true_ranges.append(0.0)
        else:
            tr = max(
                hi - lo,
                abs(hi - prev_c),
                abs(lo - prev_c),
            )
            true_ranges.append(tr)
    result: list[float | None] = [None] * len(closes)
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
    n = len(values)
    if not values or fast <= 0 or slow <= 0 or signal <= 0:
        return [None] * n, [None] * n, [None] * n
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    macd_line: list[float | None] = []
    for f, s in zip(fast_ema, slow_ema):
        if f is not None and s is not None:
            macd_line.append(f - s)
        else:
            macd_line.append(None)

    valid_indices = [i for i, v in enumerate(macd_line) if v is not None]
    valid_macd: list[float] = [macd_line[i] for i in valid_indices]  # type: ignore[misc]
    raw_signal = ema(valid_macd, signal)
    signal_line: list[float | None] = [None] * n
    for idx, sig_val in zip(valid_indices, raw_signal):
        signal_line[idx] = sig_val

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
    if not values or period <= 0:
        n = len(values)
        return [None] * n, [None] * n, [None] * n
    middle = sma(values, period)
    cleaned = [_clean_float(v) for v in values]
    upper: list[float | None] = []
    lower: list[float | None] = []
    for i, mid in enumerate(middle):
        if mid is None or i + 1 < period:
            upper.append(None)
            lower.append(None)
        else:
            window = [x for x in cleaned[i + 1 - period: i + 1] if x is not None]
            if len(window) < period:
                upper.append(None)
                lower.append(None)
            else:
                variance = sum((x - mid) ** 2 for x in window) / period
                sigma = math.sqrt(max(0.0, variance))
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
    if window <= 0:
        return [], []
    n = min(len(highs), len(lows))
    c_highs = [_clean_float(h) for h in highs[:n]]
    c_lows = [_clean_float(l) for l in lows[:n]]
    for i in range(window, n - window):
        local_high = c_highs[i]
        local_low = c_lows[i]
        if local_high is not None:
            neighbors_h = [c_highs[j] for j in range(i - window, i + window + 1) if j != i]
            if all(nh is not None and local_high >= nh for nh in neighbors_h):
                resistance_levels.append(local_high)
        if local_low is not None:
            neighbors_l = [c_lows[j] for j in range(i - window, i + window + 1) if j != i]
            if all(nl is not None and local_low <= nl for nl in neighbors_l):
                support_levels.append(local_low)
    return sorted(set(resistance_levels)), sorted(set(support_levels))


def stochastic(
    high: Sequence[float] | None = None,
    low: Sequence[float] | None = None,
    close: Sequence[float] | None = None,
    k_period: int = 14,
    d_period: int = 3,
    slowing_period: int = 1,
    **kwargs: Any,
) -> tuple[list[float | None], list[float | None]]:
    """Stochastic Oscillator (%K and %D).

    Computes the Fast Stochastic Oscillator (%K) and its moving average (%D).
    Supports optional %K smoothing via slowing_period (default 1 for Fast Stochastic).

    Args:
        high: High prices sequence (or keyword highs).
        low: Low prices sequence (or keyword lows).
        close: Closing prices sequence (or keyword closes).
        k_period: Lookback window for %K (default 14).
        d_period: Moving average period for %D (default 3).
        slowing_period: Smoothing period for %K (default 1 = Fast Stochastic).

    Returns:
        Tuple of (k_line, d_line) — aligned 1-to-1 with close, None-padded.
    """
    h_in = high if high is not None else kwargs.get("highs")
    l_in = low if low is not None else kwargs.get("lows")
    c_in = close if close is not None else kwargs.get("closes")

    if c_in is None or h_in is None or l_in is None or len(c_in) == 0:
        n_empty = len(c_in) if c_in is not None else 0
        return [None] * n_empty, [None] * n_empty

    n_out = len(c_in)
    n = min(len(h_in), len(l_in), len(c_in))
    k_line: list[float | None] = [None] * n_out
    d_line: list[float | None] = [None] * n_out

    if k_period <= 0 or d_period <= 0 or slowing_period <= 0 or n < k_period:
        return k_line, d_line

    c_h = [_clean_float(v) for v in h_in[:n]]
    c_l = [_clean_float(v) for v in l_in[:n]]
    c_c = [_clean_float(v) for v in c_in[:n]]

    raw_k: list[float | None] = [None] * n
    for i in range(k_period - 1, n):
        w_h = c_h[i - k_period + 1 : i + 1]
        w_l = c_l[i - k_period + 1 : i + 1]
        cur_c = c_c[i]
        if cur_c is None or any(v is None for v in w_h) or any(v is None for v in w_l):
            raw_k[i] = None
            continue

        hh = max(v for v in w_h if v is not None)
        ll = min(v for v in w_l if v is not None)
        denom = hh - ll
        if abs(denom) < 1e-12:
            raw_k[i] = 50.0  # Neutral reading on constant flat prices
        else:
            val = 100.0 * (cur_c - ll) / denom
            raw_k[i] = max(0.0, min(100.0, val))

    # Apply slowing period if requested (slowing_period > 1 produces Slow Stochastic %K)
    if slowing_period > 1:
        smooth_k: list[float | None] = [None] * n
        for i in range(n):
            if i + 1 < k_period + slowing_period - 1:
                smooth_k[i] = None
            else:
                window = raw_k[i - slowing_period + 1 : i + 1]
                if any(v is None for v in window):
                    smooth_k[i] = None
                else:
                    smooth_k[i] = sum(v for v in window if v is not None) / slowing_period
        k_source = smooth_k
    else:
        k_source = raw_k

    for i in range(n):
        k_line[i] = k_source[i]

    # Calculate %D as SMA of %K over d_period
    for i in range(n):
        if i + 1 < (k_period + (slowing_period - 1) + d_period - 1):
            d_line[i] = None
        else:
            window = k_source[i - d_period + 1 : i + 1]
            if any(v is None for v in window):
                d_line[i] = None
            else:
                d_val = sum(v for v in window if v is not None) / d_period
                d_line[i] = max(0.0, min(100.0, d_val))

    return k_line, d_line


def adx(
    high: Sequence[float] | None = None,
    low: Sequence[float] | None = None,
    close: Sequence[float] | None = None,
    period: int = 14,
    **kwargs: Any,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Average Directional Index (ADX), +DI, and -DI with Wilder smoothing.

    Args:
        high: High prices sequence (or keyword highs).
        low: Low prices sequence (or keyword lows).
        close: Closing prices sequence (or keyword closes).
        period: Lookback window (default 14).

    Returns:
        Tuple of (adx, plus_di, minus_di) — aligned 1-to-1 with close, None-padded.
    """
    h_in = high if high is not None else kwargs.get("highs")
    l_in = low if low is not None else kwargs.get("lows")
    c_in = close if close is not None else kwargs.get("closes")

    if c_in is None or h_in is None or l_in is None or len(c_in) == 0:
        n_empty = len(c_in) if c_in is not None else 0
        return [None] * n_empty, [None] * n_empty, [None] * n_empty

    n_out = len(c_in)
    n = min(len(h_in), len(l_in), len(c_in))
    adx_line: list[float | None] = [None] * n_out
    plus_di: list[float | None] = [None] * n_out
    minus_di: list[float | None] = [None] * n_out

    if period <= 0 or n < period + 1:
        return adx_line, plus_di, minus_di

    c_h = [_clean_float(v) for v in h_in[:n]]
    c_l = [_clean_float(v) for v in l_in[:n]]
    c_c = [_clean_float(v) for v in c_in[:n]]

    tr_list: list[float] = []
    dm_plus_list: list[float] = []
    dm_minus_list: list[float] = []

    for i in range(1, n):
        hi = c_h[i]
        lo = c_l[i]
        prev_h = c_h[i - 1]
        prev_l = c_l[i - 1]
        prev_c = c_c[i - 1]

        if hi is None or lo is None or prev_h is None or prev_l is None or prev_c is None:
            tr_list.append(0.0)
            dm_plus_list.append(0.0)
            dm_minus_list.append(0.0)
        else:
            tr = max(hi - lo, abs(hi - prev_c), abs(lo - prev_c))
            up_move = hi - prev_h
            down_move = prev_l - lo

            p_dm = up_move if (up_move > down_move and up_move > 0.0) else 0.0
            m_dm = down_move if (down_move > up_move and down_move > 0.0) else 0.0

            tr_list.append(tr)
            dm_plus_list.append(p_dm)
            dm_minus_list.append(m_dm)

    if len(tr_list) < period:
        return adx_line, plus_di, minus_di

    # Initial Wilder smoothed sums over the first `period` bars (indices 0..period-1)
    sm_tr = sum(tr_list[:period])
    sm_p_dm = sum(dm_plus_list[:period])
    sm_m_dm = sum(dm_minus_list[:period])

    dx_list: list[float | None] = [None] * n

    # First +DI and -DI at bar index `period`
    if sm_tr <= 1e-12:
        p_di = 0.0
        m_di = 0.0
    else:
        p_di = 100.0 * sm_p_dm / sm_tr
        m_di = 100.0 * sm_m_dm / sm_tr

    plus_di[period] = max(0.0, p_di)
    minus_di[period] = max(0.0, m_di)
    di_sum = p_di + m_di
    dx_list[period] = 0.0 if di_sum <= 1e-12 else 100.0 * abs(p_di - m_di) / di_sum

    # Running Wilder smoothing for subsequent bars
    for i in range(period + 1, n):
        tr = tr_list[i - 1]
        p_dm = dm_plus_list[i - 1]
        m_dm = dm_minus_list[i - 1]

        sm_tr = sm_tr - (sm_tr / period) + tr
        sm_p_dm = sm_p_dm - (sm_p_dm / period) + p_dm
        sm_m_dm = sm_m_dm - (sm_m_dm / period) + m_dm

        if sm_tr <= 1e-12:
            p_di = 0.0
            m_di = 0.0
        else:
            p_di = 100.0 * sm_p_dm / sm_tr
            m_di = 100.0 * sm_m_dm / sm_tr

        plus_di[i] = max(0.0, p_di)
        minus_di[i] = max(0.0, m_di)
        di_sum = p_di + m_di
        dx_list[i] = 0.0 if di_sum <= 1e-12 else 100.0 * abs(p_di - m_di) / di_sum

    # Calculate ADX (Wilder smoothing of DX)
    # The first ADX occurs at bar index 2 * period - 1 (requires `period` DX values: period .. 2*period - 1)
    if n >= 2 * period:
        first_adx_idx = 2 * period - 1
        dx_window = [dx_list[j] for j in range(period, first_adx_idx + 1) if dx_list[j] is not None]
        if len(dx_window) == period:
            cur_adx = sum(dx_window) / period
            adx_line[first_adx_idx] = max(0.0, min(100.0, cur_adx))
            for i in range(first_adx_idx + 1, n):
                cur_dx = dx_list[i]
                if cur_dx is not None:
                    cur_adx = (cur_adx * (period - 1) + cur_dx) / period
                    adx_line[i] = max(0.0, min(100.0, cur_adx))
                else:
                    adx_line[i] = None

    return adx_line, plus_di, minus_di


def ma_slope(
    values: Sequence[float],
    period: int = 20,
    lookback: int = 5,
    normalized: bool = False,
) -> list[float | None]:
    """Calculate the slope of a Simple Moving Average.

    Args:
        values: Sequence of closing prices.
        period: Moving average period (default 20).
        lookback: Number of bars over which slope is computed (default 5).
        normalized: If True, returns percentage slope per bar relative to MA base.
                    If False, returns absolute price change per bar.

    Returns:
        List of slope values, None-padded.
    """
    if not values:
        return []
    n = len(values)
    result: list[float | None] = [None] * n
    if period <= 0 or lookback <= 0 or n < period + lookback:
        return result

    ma = sma(values, period)
    for i in range(period + lookback - 1, n):
        cur_ma = ma[i]
        prev_ma = ma[i - lookback]
        if cur_ma is not None and prev_ma is not None:
            diff = cur_ma - prev_ma
            if not normalized:
                result[i] = diff / lookback
            else:
                if abs(prev_ma) < 1e-12:
                    result[i] = 0.0
                else:
                    result[i] = (diff / (prev_ma * lookback)) * 100.0
    return result


def trend_strength(
    values: Sequence[float],
    fast_period: int = 20,
    slow_period: int = 50,
) -> list[float | None]:
    """Measure trend direction and magnitude via moving average spread percentage.

    Calculates: trend_strength = ((SMA_fast - SMA_slow) / SMA_slow) * 100.0

    Args:
        values: Sequence of closing prices.
        fast_period: Lookback window for fast SMA (default 20).
        slow_period: Lookback window for slow SMA (default 50).

    Returns:
        List of trend strength percentages, None-padded.
    """
    if not values:
        return []
    n = len(values)
    result: list[float | None] = [None] * n
    if fast_period <= 0 or slow_period <= 0 or n < max(fast_period, slow_period):
        return result

    fast_ma = sma(values, fast_period)
    slow_ma = sma(values, slow_period)

    for i in range(n):
        f = fast_ma[i]
        s = slow_ma[i]
        if f is not None and s is not None:
            if abs(s) < 1e-12:
                result[i] = 0.0
            else:
                result[i] = ((f - s) / s) * 100.0
    return result


def linear_regression_slope(
    values: Sequence[float],
    period: int = 14,
) -> list[float | None]:
    """Calculate rolling OLS linear regression slope of price over time.

    Args:
        values: Sequence of prices.
        period: Lookback window for regression (default 14).

    Returns:
        List of slope values (unit: price delta per bar), None-padded.
    """
    if not values:
        return []
    n = len(values)
    result: list[float | None] = [None] * n
    if period <= 1 or n < period:
        return result

    cleaned = [_clean_float(v) for v in values]
    sum_x = period * (period - 1) / 2.0
    sum_xx = (period - 1) * period * (2 * period - 1) / 6.0
    denom = period * sum_xx - (sum_x ** 2)

    for i in range(period - 1, n):
        window = cleaned[i - period + 1 : i + 1]
        if any(v is None for v in window):
            result[i] = None
            continue
        sum_y = sum(v for v in window if v is not None)
        sum_xy = sum(idx * val for idx, val in enumerate(window) if val is not None)
        result[i] = (period * sum_xy - sum_x * sum_y) / denom

    return result

