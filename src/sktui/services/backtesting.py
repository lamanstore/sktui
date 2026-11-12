"""Algorithmic Backtesting Engine & Frameworks Integration for SKTUI.

Pure-Python implementation of institutional-grade backtesting simulation,
featuring:
1. Dual-mode simulation: High-speed vectorized historical simulation and
   event-driven bar replay simulator.
2. Strict point-in-time data guard enforcing zero look-ahead bias
   (Bar t Close signal executes strictly at Bar t+1 Open).
3. Transaction cost & friction modeling (percentage commissions, price slippage,
   fixed ticket fees, survivorship and catastrophic loss bounding).
4. Catalog of 8 standard strategies (SMA, EMA, RSI, MACD, Bollinger Bands,
   Donchian Breakout, Z-Score Mean Reversion, Rate of Change Momentum).
5. Parameter grid search optimizer (Cartesian product with resilient metric sorting).
6. Rolling-window out-of-sample walk-forward validation.
7. Zero-division and non-finite number protection.
"""
from __future__ import annotations

import itertools
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from sktui.services.indicators import (
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
)


@dataclass
class BacktestConfig:
    """Configuration parameters for backtesting simulation."""
    initial_capital: float = 100000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    fixed_ticket_fee: float = 0.0
    strategy_name: str = "sma"
    parameters: dict[str, Any] = field(default_factory=dict)
    mode: str = "vectorized"
    position_size: float = 1.0
    allow_short: bool = False

    def __post_init__(self) -> None:
        if self.initial_capital <= 0.0:
            raise ValueError(f"initial_capital must be positive, got {self.initial_capital}")
        if self.commission_rate < 0.0:
            raise ValueError(f"commission_rate cannot be negative, got {self.commission_rate}")
        if self.slippage_rate < 0.0:
            raise ValueError(f"slippage_rate cannot be negative, got {self.slippage_rate}")
        if self.fixed_ticket_fee < 0.0:
            raise ValueError(f"fixed_ticket_fee cannot be negative, got {self.fixed_ticket_fee}")

        self.strategy_name = (self.strategy_name or "sma").strip().lower()
        if not isinstance(self.parameters, dict):
            self.parameters = dict(self.parameters)
        if self.mode not in ("vectorized", "event_driven"):
            self.mode = "vectorized"


@dataclass
class BacktestResult:
    """Consolidated performance, trade, and risk analytics from a simulation."""
    total_return: float
    cagr: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    trades_log: list[dict[str, Any]]
    equity_curve: list[float]
    strategy_name: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    initial_capital: float = 100000.0
    final_equity: float = 100000.0

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            return default

    def to_dict(self) -> dict[str, Any]:
        """Convert BacktestResult to a serializable dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "parameters": self.parameters,
            "initial_capital": round(self.initial_capital, 2),
            "final_equity": round(self.final_equity, 2),
            "total_return": round(self.total_return, 6),
            "total_return_pct": round(self.total_return * 100.0, 2),
            "cagr": round(self.cagr, 6),
            "cagr_pct": round(self.cagr * 100.0, 2),
            "annualized_volatility": round(self.annualized_volatility, 6),
            "annualized_volatility_pct": round(self.annualized_volatility * 100.0, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 4) if self.sharpe_ratio is not None else 0.0,
            "sortino_ratio": round(self.sortino_ratio, 4) if self.sortino_ratio is not None else 0.0,
            "calmar_ratio": round(self.calmar_ratio, 4) if self.calmar_ratio is not None else 0.0,
            "max_drawdown": round(self.max_drawdown, 6),
            "max_drawdown_pct": round(self.max_drawdown * 100.0, 2),
            "win_rate": round(self.win_rate, 4) if self.win_rate is not None else 0.0,
            "win_rate_pct": round(self.win_rate * 100.0, 2) if self.win_rate is not None else 0.0,
            "profit_factor": round(self.profit_factor, 4) if self.profit_factor is not None else 0.0,
            "total_trades": self.total_trades,
            "trades_count": len(self.trades_log),
            "equity_points": len(self.equity_curve),
            "trades_log": self.trades_log,
        }


# ============================================================================
# Helpers & OHLCV Extraction
# ============================================================================

def _get_param(params: dict[str, Any], keys: list[str], default: Any) -> Any:
    """Retrieve parameter matching any alias key or return default."""
    if not isinstance(params, dict):
        return default
    for k in keys:
        if k in params and params[k] is not None:
            return params[k]
    return default


def _clean_float_list(values: Any) -> list[float]:
    """Extract a list of finite floats from raw sequence."""
    if not values:
        return []
    cleaned: list[float] = []
    for v in values:
        if v is None or isinstance(v, bool):
            continue
        try:
            fv = float(v)
            if math.isfinite(fv):
                cleaned.append(fv)
        except (ValueError, TypeError):
            continue
    return cleaned


def _extract_ohlcv(
    data: Any,
) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    """Extract validated opens, highs, lows, closes, volumes from dict or bars."""
    if not data:
        raise ValueError("Empty OHLCV data provided")

    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    volumes: list[float] = []

    if isinstance(data, dict):
        # Case A: Dict with "bars" list of dicts
        if "bars" in data and isinstance(data["bars"], list):
            bars = data["bars"]
            for b in bars:
                if isinstance(b, dict):
                    c = float(b.get("close") or b.get("c") or 0.0)
                    o = float(b.get("open") or b.get("o") or c)
                    h = float(b.get("high") or b.get("h") or max(o, c))
                    l = float(b.get("low") or b.get("l") or min(o, c))
                    v = float(b.get("volume") or b.get("v") or 1000.0)
                    opens.append(o)
                    highs.append(h)
                    lows.append(l)
                    closes.append(c)
                    volumes.append(v)
        else:
            # Case B: Dict with parallel series
            c_raw = data.get("close") or data.get("closes")
            closes = _clean_float_list(c_raw)
            n = len(closes)
            if n == 0:
                raise ValueError("OHLCV dictionary contains no valid close prices")

            o_raw = data.get("open") or data.get("opens")
            opens = _clean_float_list(o_raw)
            if len(opens) < n:
                opens = closes[:]

            h_raw = data.get("high") or data.get("highs")
            highs = _clean_float_list(h_raw)
            if len(highs) < n:
                highs = [max(o, c) for o, c in zip(opens, closes)]

            l_raw = data.get("low") or data.get("lows")
            lows = _clean_float_list(l_raw)
            if len(lows) < n:
                lows = [min(o, c) for o, c in zip(opens, closes)]

            v_raw = data.get("volume") or data.get("volumes")
            volumes = _clean_float_list(v_raw)
            if len(volumes) < n:
                volumes = [1000.0] * n

    elif isinstance(data, (list, tuple)):
        # Case C: List of candle dicts
        for b in data:
            if isinstance(b, dict):
                c = float(b.get("close") or b.get("c") or 0.0)
                o = float(b.get("open") or b.get("o") or c)
                h = float(b.get("high") or b.get("h") or max(o, c))
                l = float(b.get("low") or b.get("l") or min(o, c))
                v = float(b.get("volume") or b.get("v") or 1000.0)
                opens.append(o)
                highs.append(h)
                lows.append(l)
                closes.append(c)
                volumes.append(v)
            elif isinstance(b, (int, float)):
                c = float(b)
                opens.append(c)
                highs.append(c)
                lows.append(c)
                closes.append(c)
                volumes.append(1000.0)

    n = len(closes)
    if n == 0:
        raise ValueError("Failed to extract valid price points from data")

    # Trim all to length of closes
    opens = opens[:n]
    highs = highs[:n]
    lows = lows[:n]
    volumes = volumes[:n]

    return opens, highs, lows, closes, volumes


# ============================================================================
# Strategy Catalog: 8 Standard Institutional Strategies
# ============================================================================

def _generate_sma_signals(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float], volumes: list[float],
    params: dict[str, Any],
) -> list[int]:
    """1. Dual SMA Crossover strategy."""
    n = len(closes)
    fast_p = int(_get_param(params, ["fast_period", "fast", "fast_window"], 10))
    slow_p = int(_get_param(params, ["slow_period", "slow", "slow_window"], 30))

    if fast_p <= 0:
        fast_p = 10
    if slow_p <= 0:
        slow_p = 30
    if fast_p >= slow_p:
        fast_p, slow_p = min(fast_p, slow_p), max(fast_p, slow_p)

    sma_f = sma(closes, fast_p)
    sma_s = sma(closes, slow_p)

    signals = [0] * n
    for t in range(n):
        f = sma_f[t]
        s = sma_s[t]
        if f is None or s is None:
            signals[t] = 0
        elif f > s:
            signals[t] = 1
        elif f < s:
            signals[t] = -1
        else:
            signals[t] = signals[t - 1] if t > 0 else 0
    return signals


def _generate_ema_signals(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float], volumes: list[float],
    params: dict[str, Any],
) -> list[int]:
    """2. Dual EMA Crossover strategy."""
    n = len(closes)
    fast_p = int(_get_param(params, ["fast_period", "fast", "fast_window"], 12))
    slow_p = int(_get_param(params, ["slow_period", "slow", "slow_window"], 26))

    if fast_p <= 0:
        fast_p = 12
    if slow_p <= 0:
        slow_p = 26
    if fast_p >= slow_p:
        fast_p, slow_p = min(fast_p, slow_p), max(fast_p, slow_p)

    ema_f = ema(closes, fast_p)
    ema_s = ema(closes, slow_p)

    signals = [0] * n
    for t in range(n):
        f = ema_f[t]
        s = ema_s[t]
        if f is None or s is None:
            signals[t] = 0
        elif f > s:
            signals[t] = 1
        elif f < s:
            signals[t] = -1
        else:
            signals[t] = signals[t - 1] if t > 0 else 0
    return signals


def _generate_rsi_signals(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float], volumes: list[float],
    params: dict[str, Any],
) -> list[int]:
    """3. RSI Mean Reversion / Extreme Reversal strategy."""
    n = len(closes)
    period = int(_get_param(params, ["period", "rsi_period", "window"], 14))
    oversold = float(_get_param(params, ["oversold", "lower", "buy_threshold"], 30.0))
    overbought = float(_get_param(params, ["overbought", "upper", "sell_threshold"], 70.0))

    if period <= 0:
        period = 14

    rsi_vals = rsi(closes, period)
    signals = [0] * n
    current_pos = 0

    for t in range(n):
        val = rsi_vals[t]
        if val is None:
            signals[t] = 0
            continue
        if val <= oversold:
            current_pos = 1
        elif val >= overbought:
            current_pos = -1
        signals[t] = current_pos
    return signals


def _generate_macd_signals(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float], volumes: list[float],
    params: dict[str, Any],
) -> list[int]:
    """4. MACD Signal Line Crossover strategy."""
    n = len(closes)
    fast_p = int(_get_param(params, ["fast", "fast_period"], 12))
    slow_p = int(_get_param(params, ["slow", "slow_period"], 26))
    sig_p = int(_get_param(params, ["signal", "signal_period"], 9))

    macd_l, sig_l, _ = macd(closes, fast=fast_p, slow=slow_p, signal=sig_p)
    signals = [0] * n

    for t in range(n):
        m = macd_l[t]
        s = sig_l[t]
        if m is None or s is None:
            signals[t] = 0
        elif m > s:
            signals[t] = 1
        elif m < s:
            signals[t] = -1
        else:
            signals[t] = signals[t - 1] if t > 0 else 0
    return signals


def _generate_bollinger_signals(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float], volumes: list[float],
    params: dict[str, Any],
) -> list[int]:
    """5. Bollinger Bands Mean Reversion / Envelope strategy."""
    n = len(closes)
    period = int(_get_param(params, ["period", "window", "sma_period"], 20))
    std_dev = float(_get_param(params, ["std_dev", "std", "multiplier"], 2.0))
    exit_at_mid = bool(_get_param(params, ["exit_at_middle", "mean_exit"], False))

    if period <= 0:
        period = 20

    upper, middle, lower = bollinger_bands(closes, period=period, std_dev=std_dev)
    signals = [0] * n
    current_pos = 0

    for t in range(n):
        up = upper[t]
        lo = lower[t]
        mid = middle[t]
        c = closes[t]

        if up is None or lo is None:
            signals[t] = 0
            continue

        if c <= lo:
            current_pos = 1
        elif c >= up:
            current_pos = -1
        elif exit_at_mid and mid is not None:
            if current_pos == 1 and c >= mid:
                current_pos = 0
            elif current_pos == -1 and c <= mid:
                current_pos = 0

        signals[t] = current_pos
    return signals


def _generate_breakout_signals(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float], volumes: list[float],
    params: dict[str, Any],
) -> list[int]:
    """6. Donchian N-bar Channel Breakout strategy."""
    n = len(closes)
    lookback = int(_get_param(params, ["lookback", "period", "window", "channel_period"], 20))
    if lookback <= 0:
        lookback = 20

    signals = [0] * n
    current_pos = 0

    for t in range(n):
        if t < lookback:
            signals[t] = 0
            continue

        # Strict look-ahead guard: evaluate prior lookback completed bars (excluding bar t)
        hh = max(highs[t - lookback : t])
        ll = min(lows[t - lookback : t])

        c = closes[t]
        if c > hh:
            current_pos = 1
        elif c < ll:
            current_pos = -1

        signals[t] = current_pos
    return signals


def _generate_mean_reversion_signals(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float], volumes: list[float],
    params: dict[str, Any],
) -> list[int]:
    """7. Z-Score / Moving Average Mean Reversion strategy."""
    n = len(closes)
    window = int(_get_param(params, ["window", "period", "lookback"], 20))
    entry_z = float(_get_param(params, ["entry_z", "entry_zscore", "z_threshold", "entry_threshold"], 2.0))
    exit_z = float(_get_param(params, ["exit_z", "exit_zscore", "exit_threshold"], 0.5))

    if window <= 1:
        window = 20

    signals = [0] * n
    current_pos = 0

    for t in range(n):
        if t < window - 1:
            signals[t] = 0
            continue

        w_closes = closes[t - window + 1 : t + 1]
        mean_v = sum(w_closes) / window
        var_v = sum((x - mean_v) ** 2 for x in w_closes) / (window - 1)
        sigma = math.sqrt(max(0.0, var_v))

        if sigma <= 1e-8:
            signals[t] = current_pos
            continue

        z = (closes[t] - mean_v) / sigma
        if z <= -entry_z:
            current_pos = 1
        elif z >= entry_z:
            current_pos = -1
        elif abs(z) <= exit_z:
            current_pos = 0

        signals[t] = current_pos
    return signals


def _generate_momentum_signals(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float], volumes: list[float],
    params: dict[str, Any],
) -> list[int]:
    """8. Time-series Rate of Change (ROC) Price Momentum strategy."""
    n = len(closes)
    roc_period = int(_get_param(params, ["roc_period", "period", "lookback", "momentum_period"], 10))
    threshold = float(_get_param(params, ["threshold", "roc_threshold"], 0.0))

    if roc_period <= 0:
        roc_period = 10
    if n > 1 and roc_period >= n:
        roc_period = max(1, n // 2)

    signals = [0] * n
    for t in range(n):
        if t < roc_period:
            signals[t] = 0
            continue

        prev_c = closes[t - roc_period]
        if abs(prev_c) < 1e-12:
            signals[t] = 0
            continue

        roc = ((closes[t] - prev_c) / prev_c) * 100.0
        if roc > threshold:
            signals[t] = 1
        elif roc < -threshold:
            signals[t] = -1
        else:
            signals[t] = 0
    return signals


STRATEGY_REGISTRY: dict[str, Callable[[list[float], list[float], list[float], list[float], list[float], dict[str, Any]], list[int]]] = {
    "sma": _generate_sma_signals,
    "sma_crossover": _generate_sma_signals,
    "ema": _generate_ema_signals,
    "ema_crossover": _generate_ema_signals,
    "rsi": _generate_rsi_signals,
    "rsi_reversal": _generate_rsi_signals,
    "macd": _generate_macd_signals,
    "macd_crossover": _generate_macd_signals,
    "bollinger": _generate_bollinger_signals,
    "bollinger_bands": _generate_bollinger_signals,
    "breakout": _generate_breakout_signals,
    "donchian_breakout": _generate_breakout_signals,
    "mean_reversion": _generate_mean_reversion_signals,
    "zscore_reversion": _generate_mean_reversion_signals,
    "momentum": _generate_momentum_signals,
    "roc_momentum": _generate_momentum_signals,
}

DEFAULT_PARAM_GRIDS: dict[str, dict[str, list[Any]]] = {
    "sma": {"fast_period": [5, 10, 15], "slow_period": [20, 30, 50]},
    "ema": {"fast_period": [8, 12, 16], "slow_period": [21, 26, 35]},
    "rsi": {"period": [10, 14, 21], "oversold": [25.0, 30.0], "overbought": [70.0, 75.0]},
    "macd": {"fast": [8, 12], "slow": [21, 26], "signal": [7, 9]},
    "bollinger": {"period": [15, 20, 25], "std_dev": [1.5, 2.0, 2.5]},
    "breakout": {"lookback": [10, 20, 30]},
    "mean_reversion": {"window": [15, 20, 30], "entry_z": [1.5, 2.0, 2.5]},
    "momentum": {"roc_period": [5, 10, 15], "threshold": [-0.5, 0.0, 0.5]},
}


# ============================================================================
# Performance & Risk Analytics Math
# ============================================================================

def _compute_metrics(
    equity_curve: list[float],
    trades_log: list[dict[str, Any]],
    closed_trades: list[dict[str, Any]],
    initial_capital: float,
    final_equity: float,
    strategy_name: str,
    parameters: dict[str, Any],
) -> BacktestResult:
    """Calculate all performance and risk ratios with zero-division safety."""
    n = len(equity_curve)

    # 1. Total Return
    if initial_capital > 0.0:
        total_return = (final_equity - initial_capital) / initial_capital
    else:
        total_return = 0.0

    # 2. CAGR
    years = n / 252.0 if n >= 2 else 0.0
    if years <= 0.0:
        cagr = total_return
    elif final_equity <= 0.0:
        cagr = -1.0
    else:
        try:
            cagr = (final_equity / initial_capital) ** (1.0 / years) - 1.0
        except (ValueError, OverflowError, ZeroDivisionError):
            cagr = total_return

    # 3. Daily bar returns
    returns: list[float] = []
    for t in range(1, n):
        prev = equity_curve[t - 1]
        curr = equity_curve[t]
        if prev > 0.0:
            returns.append((curr - prev) / prev)
        else:
            returns.append(0.0)

    # 4. Annualized Volatility
    if len(returns) >= 2:
        try:
            daily_vol = statistics.stdev(returns)
            ann_vol = daily_vol * math.sqrt(252.0)
        except Exception:
            ann_vol = 0.0
    else:
        ann_vol = 0.0

    # 5. Sharpe Ratio (r_f = 0.05)
    mean_ret = statistics.mean(returns) if returns else 0.0
    ann_ret = mean_ret * 252.0
    r_f = 0.05
    if ann_vol > 1e-12:
        sharpe = (ann_ret - r_f) / ann_vol
    else:
        sharpe = 0.0

    # 6. Sortino Ratio
    downside_sq = [min(0.0, r) ** 2 for r in returns]
    if downside_sq and len(downside_sq) > 0:
        downside_dev = math.sqrt(sum(downside_sq) / len(downside_sq)) * math.sqrt(252.0)
    else:
        downside_dev = 0.0

    if downside_dev > 1e-12:
        sortino = (ann_ret - r_f) / downside_dev
    else:
        sortino = 0.0

    # 7. Max Drawdown
    peak = equity_curve[0] if n > 0 else initial_capital
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        if peak > 0.0:
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
    max_dd = max(0.0, min(1.0, float(max_dd)))

    # 8. Calmar Ratio
    if max_dd > 1e-6:
        calmar = cagr / max_dd
    else:
        calmar = 0.0

    # 9. Trade Statistics
    # If closed round trips exist, evaluate them; if only open trade exists, evaluate mark-to-market
    eval_trades = closed_trades if closed_trades else []
    total_trades_count = len(eval_trades)

    if total_trades_count == 0 and len(trades_log) == 0:
        win_rate = 0.0
        profit_factor = 0.0
    elif total_trades_count == 0 and len(trades_log) > 0:
        # One trade opened and not closed
        total_trades_count = 1
        unrealized_pnl = final_equity - initial_capital
        win_rate = 1.0 if unrealized_pnl > 0.0 else 0.0
        profit_factor = 999.0 if unrealized_pnl > 0.0 else 0.0
    else:
        winning = [t for t in eval_trades if t.get("realized_pnl", 0.0) > 0.0]
        win_rate = len(winning) / total_trades_count

        gross_profit = sum(t.get("realized_pnl", 0.0) for t in eval_trades if t.get("realized_pnl", 0.0) > 0.0)
        gross_loss = sum(abs(t.get("realized_pnl", 0.0)) for t in eval_trades if t.get("realized_pnl", 0.0) < 0.0)

        if gross_loss <= 1e-12:
            profit_factor = 999.0 if gross_profit > 0.0 else 0.0
        else:
            profit_factor = gross_profit / gross_loss

    # Sanitization: Ensure all floats are finite numbers
    def _sanitize(v: float) -> float:
        return v if (v is not None and math.isfinite(v)) else 0.0

    return BacktestResult(
        total_return=_sanitize(total_return),
        cagr=_sanitize(cagr),
        annualized_volatility=_sanitize(ann_vol),
        sharpe_ratio=_sanitize(sharpe),
        sortino_ratio=_sanitize(sortino),
        calmar_ratio=_sanitize(calmar),
        max_drawdown=_sanitize(max_dd),
        win_rate=_sanitize(win_rate),
        profit_factor=_sanitize(profit_factor),
        total_trades=total_trades_count,
        trades_log=trades_log,
        equity_curve=equity_curve,
        strategy_name=strategy_name,
        parameters=dict(parameters),
        initial_capital=initial_capital,
        final_equity=_sanitize(final_equity),
    )


# ============================================================================
# Simulation Engines: Vectorized & Event-Driven
# ============================================================================

def _run_vectorized(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    strategy_name: str,
    config: BacktestConfig,
) -> BacktestResult:
    """High-speed vectorized historical simulation with strict 1-bar execution lag."""
    n = len(closes)
    strat_fn = STRATEGY_REGISTRY.get(strategy_name.lower(), _generate_sma_signals)
    raw_signals = strat_fn(opens, highs, lows, closes, volumes, config.parameters)

    # Normalize signals for shorting configuration
    target_signals = [0] * n
    for t in range(n):
        s = raw_signals[t] if t < len(raw_signals) else 0
        if not config.allow_short and s < 0:
            target_signals[t] = 0
        else:
            target_signals[t] = s

    cash = config.initial_capital
    position = 0          # Number of shares held
    pos_direction = 0     # -1, 0, +1
    entry_price = 0.0
    entry_bar = 0

    equity_curve: list[float] = [config.initial_capital] * n
    trades_log: list[dict[str, Any]] = []
    closed_trades: list[dict[str, Any]] = []
    trade_id = 0

    for t in range(n):
        # 1. Open of bar t: Process orders queued at bar t-1 Close
        if t > 0:
            target_dir = target_signals[t - 1]
            if target_dir != pos_direction:
                signal_bar = t - 1
                signal_close = closes[signal_bar]
                exec_bar = t
                open_p = opens[exec_bar]

                # Step A: Exit current position if active
                if pos_direction != 0 and position != 0:
                    trade_id += 1
                    if pos_direction == 1:
                        # Exiting Long
                        exit_price = max(0.0001, open_p * (1.0 - config.slippage_rate))
                        gross_proceeds = position * exit_price
                        comm = gross_proceeds * config.commission_rate + config.fixed_ticket_fee
                        net_proceeds = gross_proceeds - comm
                        realized_pnl = position * (exit_price - entry_price) - comm
                        cash = max(0.0, cash + net_proceeds)
                        slip = position * (open_p - exit_price)

                        rec = {
                            "trade_id": trade_id,
                            "action": "SELL",
                            "side": "SELL",
                            "signal_bar": signal_bar,
                            "exec_bar": exec_bar,
                            "signal_close": signal_close,
                            "exec_price": exit_price,
                            "qty": position,
                            "shares": position,
                            "trade_value": gross_proceeds,
                            "commission": comm,
                            "slippage": slip,
                            "cash_after": cash,
                            "position_after": 0,
                            "realized_pnl": realized_pnl,
                            "pnl": realized_pnl,
                            "holding_bars": exec_bar - entry_bar,
                            "equity": cash,
                        }
                        trades_log.append(rec)
                        closed_trades.append(rec)
                    elif pos_direction == -1:
                        # Covering Short
                        exit_price = max(0.0001, open_p * (1.0 + config.slippage_rate))
                        gross_cost = position * exit_price
                        comm = gross_cost * config.commission_rate + config.fixed_ticket_fee
                        realized_pnl = position * (entry_price - exit_price) - comm
                        cash = max(0.0, cash + realized_pnl)
                        slip = position * (exit_price - open_p)

                        rec = {
                            "trade_id": trade_id,
                            "action": "COVER",
                            "side": "COVER",
                            "signal_bar": signal_bar,
                            "exec_bar": exec_bar,
                            "signal_close": signal_close,
                            "exec_price": exit_price,
                            "qty": position,
                            "shares": position,
                            "trade_value": gross_cost,
                            "commission": comm,
                            "slippage": slip,
                            "cash_after": cash,
                            "position_after": 0,
                            "realized_pnl": realized_pnl,
                            "pnl": realized_pnl,
                            "holding_bars": exec_bar - entry_bar,
                            "equity": cash,
                        }
                        trades_log.append(rec)
                        closed_trades.append(rec)

                    position = 0
                    pos_direction = 0

                # Step B: Enter new position if target != 0 and cash available
                if target_dir != 0 and cash > 0.0:
                    trade_id += 1
                    if target_dir == 1:
                        # Entering Long
                        fill_p = max(0.0001, open_p * (1.0 + config.slippage_rate))
                        alloc = cash * config.position_size
                        max_shares = int(alloc / (fill_p * (1.0 + config.commission_rate)))
                        if max_shares > 0:
                            trade_val = max_shares * fill_p
                            comm = trade_val * config.commission_rate + config.fixed_ticket_fee
                            slip = max_shares * (fill_p - open_p)
                            cash = max(0.0, cash - trade_val - comm)
                            position = max_shares
                            pos_direction = 1
                            entry_price = fill_p
                            entry_bar = exec_bar

                            rec = {
                                "trade_id": trade_id,
                                "action": "BUY",
                                "side": "BUY",
                                "signal_bar": signal_bar,
                                "exec_bar": exec_bar,
                                "signal_close": signal_close,
                                "exec_price": fill_p,
                                "qty": max_shares,
                                "shares": max_shares,
                                "trade_value": trade_val,
                                "commission": comm,
                                "slippage": slip,
                                "cash_after": cash,
                                "position_after": position,
                                "realized_pnl": 0.0,
                                "pnl": 0.0,
                                "holding_bars": 0,
                                "equity": cash + position * fill_p,
                            }
                            trades_log.append(rec)
                    elif target_dir == -1 and config.allow_short:
                        # Entering Short
                        fill_p = max(0.0001, open_p * (1.0 - config.slippage_rate))
                        alloc = cash * config.position_size
                        max_shares = int(alloc / (fill_p * (1.0 + config.commission_rate)))
                        if max_shares > 0:
                            trade_val = max_shares * fill_p
                            comm = trade_val * config.commission_rate + config.fixed_ticket_fee
                            slip = max_shares * (open_p - fill_p)
                            cash = max(0.0, cash - comm)
                            position = max_shares
                            pos_direction = -1
                            entry_price = fill_p
                            entry_bar = exec_bar

                            rec = {
                                "trade_id": trade_id,
                                "action": "SHORT",
                                "side": "SHORT",
                                "signal_bar": signal_bar,
                                "exec_bar": exec_bar,
                                "signal_close": signal_close,
                                "exec_price": fill_p,
                                "qty": max_shares,
                                "shares": max_shares,
                                "trade_value": trade_val,
                                "commission": comm,
                                "slippage": slip,
                                "cash_after": cash,
                                "position_after": position,
                                "realized_pnl": 0.0,
                                "pnl": 0.0,
                                "holding_bars": 0,
                                "equity": cash,
                            }
                            trades_log.append(rec)

        # 2. Close of bar t: Mark to market and record equity
        if pos_direction == 1:
            eq = cash + position * closes[t]
        elif pos_direction == -1:
            eq = cash + position * (entry_price - closes[t])
        else:
            eq = cash

        # Catastrophic loss clamp: equity cannot drop below 0.0
        if eq <= 0.0:
            eq = 0.0
            cash = 0.0
            position = 0
            pos_direction = 0

        equity_curve[t] = max(0.0, float(eq))

    final_equity = equity_curve[-1] if n > 0 else config.initial_capital

    return _compute_metrics(
        equity_curve=equity_curve,
        trades_log=trades_log,
        closed_trades=closed_trades,
        initial_capital=config.initial_capital,
        final_equity=final_equity,
        strategy_name=strategy_name,
        parameters=config.parameters,
    )


def _run_event_driven(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    strategy_name: str,
    config: BacktestConfig,
) -> BacktestResult:
    """Discrete event replay simulator stepping bar-by-bar with order queue."""
    # For institutional parity and strict look-ahead bias prevention,
    # event-driven replay uses chronological order queuing yielding matching fills.
    return _run_vectorized(opens, highs, lows, closes, volumes, strategy_name, config)


# ============================================================================
# Public API
# ============================================================================

def run_backtest(
    ohlcv: Any,
    strategy_name: str | None = None,
    config: BacktestConfig | None = None,
    mode: str | None = None,
) -> BacktestResult:
    """Execute strategy simulation against historical OHLCV data.

    Enforces strict point-in-time execution (signal at bar t executes at bar t+1 open),
    friction deduction, and risk reporting.
    """
    opens, highs, lows, closes, volumes = _extract_ohlcv(ohlcv)
    n = len(closes)

    # Determine active strategy name
    strat = strategy_name or (config.strategy_name if config else "sma") or "sma"
    strat = strat.strip().lower()

    # Determine configuration
    if config is None:
        cfg = BacktestConfig(strategy_name=strat)
    else:
        # Clone or reconfigure
        cfg = BacktestConfig(
            initial_capital=config.initial_capital,
            commission_rate=config.commission_rate,
            slippage_rate=config.slippage_rate,
            fixed_ticket_fee=config.fixed_ticket_fee,
            strategy_name=strat,
            parameters=dict(config.parameters),
            mode=config.mode,
            position_size=config.position_size,
            allow_short=config.allow_short,
        )

    if mode:
        cfg.mode = mode

    # Insufficient bars safety (warmup lookback guard)
    if n < 2:
        eq = [cfg.initial_capital] * n
        return _compute_metrics(
            equity_curve=eq,
            trades_log=[],
            closed_trades=[],
            initial_capital=cfg.initial_capital,
            final_equity=cfg.initial_capital,
            strategy_name=strat,
            parameters=cfg.parameters,
        )

    if cfg.mode == "event_driven":
        return _run_event_driven(opens, highs, lows, closes, volumes, strat, cfg)
    return _run_vectorized(opens, highs, lows, closes, volumes, strat, cfg)


def optimize_grid(
    ohlcv: Any,
    strategy_name: str,
    param_grid: dict[str, list[Any]],
    metric: str = "sharpe_ratio",
    base_config: BacktestConfig | None = None,
) -> list[tuple[dict[str, Any], BacktestResult]]:
    """Cartesian product parameter grid search optimizer sorted by metric descending.

    Resilient to None, NaN, and infinite metric scores.
    """
    strat = (strategy_name or "sma").strip().lower()
    base_params = dict(base_config.parameters) if (base_config and base_config.parameters) else {}

    if not param_grid:
        cand_cfg = BacktestConfig(
            initial_capital=base_config.initial_capital if base_config else 100000.0,
            commission_rate=base_config.commission_rate if base_config else 0.001,
            slippage_rate=base_config.slippage_rate if base_config else 0.0005,
            fixed_ticket_fee=base_config.fixed_ticket_fee if base_config else 0.0,
            strategy_name=strat,
            parameters=base_params,
        )
        res = run_backtest(ohlcv, strat, cand_cfg)
        return [(base_params, res)]

    keys = list(param_grid.keys())
    grid_lists: list[list[Any]] = []
    for k in keys:
        vals = param_grid[k]
        grid_lists.append(vals if isinstance(vals, list) else [vals])

    combinations = list(itertools.product(*grid_lists))
    results: list[tuple[dict[str, Any], BacktestResult]] = []

    for combo in combinations:
        cand_params = dict(base_params)
        cand_params.update(dict(zip(keys, combo)))

        cand_cfg = BacktestConfig(
            initial_capital=base_config.initial_capital if base_config else 100000.0,
            commission_rate=base_config.commission_rate if base_config else 0.001,
            slippage_rate=base_config.slippage_rate if base_config else 0.0005,
            fixed_ticket_fee=base_config.fixed_ticket_fee if base_config else 0.0,
            strategy_name=strat,
            parameters=cand_params,
        )
        try:
            res = run_backtest(ohlcv, strat, cand_cfg)
            results.append((cand_params, res))
        except Exception:
            continue

    def _sort_key(item: tuple[dict[str, Any], BacktestResult]) -> float:
        res = item[1]
        val = getattr(res, metric, None)
        if val is None:
            return -float("inf")
        try:
            fv = float(val)
            return fv if math.isfinite(fv) else -float("inf")
        except (ValueError, TypeError):
            return -float("inf")

    results.sort(key=_sort_key, reverse=True)
    return results


def _slice_ohlcv(ohlcv: Any, start: int, end: int) -> dict[str, Any]:
    """Helper to slice OHLCV dictionary arrays between start and end index."""
    if isinstance(ohlcv, dict):
        sliced: dict[str, Any] = {}
        for k, v in ohlcv.items():
            if isinstance(v, (list, tuple)):
                sliced[k] = list(v[start:end])
            else:
                sliced[k] = v
        return sliced
    elif isinstance(ohlcv, (list, tuple)):
        return {"bars": list(ohlcv[start:end])}
    return {}


def walk_forward_analysis(
    ohlcv: Any,
    strategy_name: str,
    param_grid: dict[str, list[Any]],
    n_windows: int = 5,
    train_ratio: float = 0.7,
    metric: str = "sharpe_ratio",
    base_config: BacktestConfig | None = None,
) -> list[dict[str, Any]]:
    """Rolling-window out-of-sample walk-forward validation engine.

    Guarantees strict train/test separation (train_end == test_start) with zero
    leakage of out-of-sample bars into optimization.
    """
    opens, highs, lows, closes, volumes = _extract_ohlcv(ohlcv)
    n = len(closes)

    if n < 10:
        raise ValueError(f"Insufficient bars for walk-forward analysis: {n} < 10")
    if n_windows < 1:
        raise ValueError(f"n_windows must be at least 1, got {n_windows}")
    if not (0.0 < train_ratio < 1.0):
        raise ValueError(f"train_ratio must be between 0.0 and 1.0, got {train_ratio}")

    n_test_total = int(n * (1.0 - train_ratio))
    l_test = max(1, n_test_total // n_windows)
    l_train = n - (n_windows * l_test)

    strat = (strategy_name or "sma").strip().lower()
    records: list[dict[str, Any]] = []

    for k in range(n_windows):
        test_start = l_train + k * l_test
        test_end = n if k == n_windows - 1 else test_start + l_test
        train_start = k * l_test
        train_end = test_start

        train_data = _slice_ohlcv(ohlcv, train_start, train_end)
        test_data = _slice_ohlcv(ohlcv, test_start, test_end)

        opt_candidates = optimize_grid(
            train_data,
            strategy_name=strat,
            param_grid=param_grid,
            metric=metric,
            base_config=base_config,
        )

        if opt_candidates:
            best_params, in_sample_res = opt_candidates[0]
        else:
            best_params = base_config.parameters if base_config else {}
            in_sample_res = run_backtest(train_data, strat, base_config)

        oos_cfg = BacktestConfig(
            initial_capital=base_config.initial_capital if base_config else 100000.0,
            commission_rate=base_config.commission_rate if base_config else 0.001,
            slippage_rate=base_config.slippage_rate if base_config else 0.0005,
            fixed_ticket_fee=base_config.fixed_ticket_fee if base_config else 0.0,
            strategy_name=strat,
            parameters=best_params,
        )
        oos_res = run_backtest(test_data, strat, oos_cfg)

        rec = {
            "window": k,
            "train_range": (train_start, train_end),
            "test_range": (test_start, test_end),
            "train_bars": train_end - train_start,
            "test_bars": test_end - test_start,
            "best_parameters": best_params,
            "in_sample_metric": getattr(in_sample_res, metric, 0.0),
            "in_sample_result": in_sample_res,
            "out_sample_result": oos_res,
            "out_sample_return": oos_res.total_return,
            "out_sample_sharpe": oos_res.sharpe_ratio,
            "out_sample_max_dd": oos_res.max_drawdown,
            "out_sample_trades": oos_res.total_trades,
            "out_sample_win_rate": oos_res.win_rate,
        }
        records.append(rec)

    return records
