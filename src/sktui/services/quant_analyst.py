"""Quantitative Analysis and Risk Performance Engine for SKTUI.

Pure-Python implementation of quantitative risk metrics, Sharpe/Sortino ratios,
Value-at-Risk (VaR/CVaR), and benchmark regression (Beta/Alpha/R-squared).
Zero external binary dependencies (math, statistics, dataclasses only).
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Sequence


@dataclass
class QuantMetrics:
    """Consolidated quantitative performance and risk metrics."""
    mean_return: float = 0.0
    annual_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    drawdown_duration: int = 0
    var_95: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0
    beta: float = 0.0
    alpha: float = 0.0
    r_squared: float = 0.0


def _clean_prices(prices: Sequence[float]) -> list[float]:
    """Clean and filter price series, removing non-finite or non-positive values."""
    cleaned: list[float] = []
    if not prices:
        return cleaned
    for p in prices:
        if p is None or isinstance(p, bool):
            continue
        try:
            v = float(p)
            if math.isfinite(v) and v > 0.0:
                cleaned.append(v)
        except (ValueError, TypeError):
            continue
    return cleaned


def _quantile(sorted_data: list[float], q: float) -> float:
    """Compute quantile q in [0, 1] using linear interpolation."""
    if not sorted_data:
        return 0.0
    n = len(sorted_data)
    if n == 1:
        return sorted_data[0]
    idx = q * (n - 1)
    i = int(idx)
    f = idx - i
    if i + 1 < n:
        return sorted_data[i] * (1.0 - f) + sorted_data[i + 1] * f
    return sorted_data[i]


def compute_metrics(
    prices: Sequence[float],
    benchmark_prices: Sequence[float] | None = None,
    risk_free_rate: float = 0.05,
) -> QuantMetrics:
    """Compute complete quantitative performance and risk metrics.

    Args:
        prices: Sequence of asset closing prices.
        benchmark_prices: Optional sequence of market benchmark prices (e.g. NIFTY50).
        risk_free_rate: Annualized risk-free rate (default: 0.05).

    Returns:
        QuantMetrics dataclass instance.
    """
    clean_p = _clean_prices(prices)
    n = len(clean_p)
    if n < 2:
        return QuantMetrics()

    # 1. Period Returns
    returns: list[float] = [
        (clean_p[i] - clean_p[i - 1]) / clean_p[i - 1]
        for i in range(1, n)
    ]
    m = len(returns)
    if m == 0:
        return QuantMetrics()

    # 2. Mean Return and Annual Volatility
    mean_ret = sum(returns) / m
    ann_mean = mean_ret * 252.0

    if m >= 2:
        try:
            daily_vol = statistics.stdev(returns)
        except statistics.StatisticsError:
            daily_vol = 0.0
    else:
        daily_vol = 0.0
    ann_vol = daily_vol * math.sqrt(252.0)

    # 3. Sharpe Ratio
    excess_ret = ann_mean - risk_free_rate
    if ann_vol > 1e-12:
        sharpe = excess_ret / ann_vol
    else:
        sharpe = 0.0

    # 4. Downside Deviation & Sortino Ratio
    downside_sq = [min(0.0, r) ** 2 for r in returns]
    downside_dev = math.sqrt(sum(downside_sq) / m) * math.sqrt(252.0)
    if downside_dev > 1e-12:
        sortino = excess_ret / downside_dev
    else:
        sortino = 0.0

    # 5. Maximum Drawdown & Drawdown Duration
    peak = clean_p[0]
    max_dd = 0.0
    cur_dur = 0
    max_dur = 0

    for p in clean_p:
        if p >= peak:
            peak = p
            cur_dur = 0
        else:
            cur_dur += 1
            if cur_dur > max_dur:
                max_dur = cur_dur
            dd = (peak - p) / peak if peak > 0.0 else 0.0
            if dd > max_dd:
                max_dd = dd

    # 6. Value at Risk (VaR) and Conditional VaR (CVaR / Expected Shortfall)
    sorted_r = sorted(returns)
    q95 = _quantile(sorted_r, 0.05)
    q99 = _quantile(sorted_r, 0.01)

    var_95 = max(0.0, -q95)
    var_99 = max(0.0, -q99)

    tail_95 = [r for r in sorted_r if r <= q95] or [q95]
    cvar_95 = max(0.0, -(sum(tail_95) / len(tail_95)))
    # Invariant guard: tail loss magnitude cannot be less than VaR * 0.95
    if cvar_95 < var_95 * 0.95:
        cvar_95 = var_95

    # 7. Benchmark Regression (Beta, Alpha, R-Squared)
    beta = 0.0
    alpha = 0.0
    r_squared = 0.0

    if benchmark_prices is not None:
        clean_bench = _clean_prices(benchmark_prices)
        k = min(len(clean_p), len(clean_bench))
        if k >= 3:
            b_rets = [
                (clean_bench[i] - clean_bench[i - 1]) / clean_bench[i - 1]
                for i in range(1, k)
            ]
            a_rets = returns[: k - 1]
            n_reg = len(b_rets)
            mean_b = sum(b_rets) / n_reg
            mean_a = sum(a_rets) / n_reg

            var_b = sum((b - mean_b) ** 2 for b in b_rets) / (n_reg - 1)
            var_a = sum((a - mean_a) ** 2 for a in a_rets) / (n_reg - 1)
            cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(a_rets, b_rets)) / (n_reg - 1)

            if var_b > 1e-12:
                beta = cov / var_b
            if var_a > 1e-12 and var_b > 1e-12:
                r2_val = (cov ** 2) / (var_a * var_b)
                r_squared = max(0.0, min(1.0, r2_val))

            if var_b > 1e-12:
                ann_a = mean_a * 252.0
                ann_b = mean_b * 252.0
                alpha = ann_a - (risk_free_rate + beta * (ann_b - risk_free_rate))

    return QuantMetrics(
        mean_return=ann_mean,
        annual_volatility=ann_vol,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=max_dd,
        drawdown_duration=max_dur,
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        beta=beta,
        alpha=alpha,
        r_squared=r_squared,
    )
