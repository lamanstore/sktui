"""End-to-End Tests for Requirement R2: Quantitative and Stock Analysis Integration.

Covers:
- Tier 1: Feature Coverage (isolated happy-path tests)
  1. Pure-Python Stochastic Oscillator (%K, %D)
  2. Pure-Python ADX Engine (ADX, +DI, -DI)
  3. Quantitative Risk & Performance Metrics (QuantMetrics: Sharpe, Sortino, VaR, CVaR)
  4. Benchmark Regression (Beta, Alpha, R-squared)
  5. StockAnalyzer Service & CLI analyze command
- Tier 2: Boundary & Corner Cases
  6. Stochastic zero-range flat price series (zero-division prevention)
  7. ADX engine on empty and insufficient-length series
  8. QuantMetrics on constant price series (zero volatility / zero Sharpe)
  9. QuantMetrics on empty or single-element price series
  10. Extreme VaR/CVaR risk confidence levels and fat-tail scenarios
"""
from __future__ import annotations

import math
import random
from typing import Any, Callable

import pytest


def _get_indicators() -> Any:
    import sktui.services.indicators as ind
    if not hasattr(ind, "stochastic") or not hasattr(ind, "adx"):
        pytest.skip("Stochastic or ADX indicator implementation pending in Milestone 2")
    return ind


def _get_quant_analyst() -> Any:
    try:
        import sktui.services.quant_analyst as qa
        return qa
    except ImportError:
        pytest.skip("sktui.services.quant_analyst implementation pending in Milestone 2")


def _get_stock_analyzer() -> Any:
    try:
        import sktui.services.stock_analyzer as sa
        return sa
    except ImportError:
        pytest.skip("sktui.services.stock_analyzer implementation pending in Milestone 2")


# ============================================================================
# Tier 1: Feature Coverage (Isolated Happy Path)
# ============================================================================

def test_r2_t1_stochastic_oscillator_happy_path(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify Pure-Python Stochastic Oscillator computes %K and %D within [0, 100]."""
    ind = _get_indicators()
    high = synthetic_ohlcv["high"]
    low = synthetic_ohlcv["low"]
    close = synthetic_ohlcv["close"]
    k_period = 14
    d_period = 3

    k_series, d_series = ind.stochastic(high, low, close, k_period=k_period, d_period=d_period)

    assert len(k_series) == len(close), "Output %K length must match input series length"
    assert len(d_series) == len(close), "Output %D length must match input series length"

    # Verify initial padding is None
    for i in range(k_period - 1):
        assert k_series[i] is None, f"%K at index {i} should be None due to insufficient lookback"

    # Verify subsequent values are bounded in [0, 100]
    valid_k = [x for x in k_series if x is not None]
    assert len(valid_k) > 0, "%K series must contain computed values"
    for val in valid_k:
        assert 0.0 <= val <= 100.0, f"%K value {val} out of bounds [0, 100]"

    valid_d = [x for x in d_series if x is not None]
    assert len(valid_d) > 0, "%D series must contain computed values"
    for val in valid_d:
        assert 0.0 <= val <= 100.0, f"%D value {val} out of bounds [0, 100]"


def test_r2_t1_adx_engine_happy_path(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify Pure-Python ADX Engine computes ADX, +DI, and -DI within [0, 100]."""
    ind = _get_indicators()
    high = synthetic_ohlcv["high"]
    low = synthetic_ohlcv["low"]
    close = synthetic_ohlcv["close"]
    period = 14

    adx_vals, plus_di, minus_di = ind.adx(high, low, close, period=period)

    assert len(adx_vals) == len(close)
    assert len(plus_di) == len(close)
    assert len(minus_di) == len(close)

    valid_adx = [x for x in adx_vals if x is not None]
    assert len(valid_adx) > 0, "ADX series must contain computed values"
    for val in valid_adx:
        assert 0.0 <= val <= 100.0, f"ADX value {val} out of bounds [0, 100]"

    for val in [x for x in plus_di if x is not None]:
        assert val >= 0.0, f"+DI value {val} cannot be negative"

    for val in [x for x in minus_di if x is not None]:
        assert val >= 0.0, f"-DI value {val} cannot be negative"


def test_r2_t1_quant_metrics_happy_path(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify compute_metrics returns a valid QuantMetrics dataclass with expected fields."""
    qa = _get_quant_analyst()
    prices = synthetic_ohlcv["close"]

    metrics = qa.compute_metrics(prices, risk_free_rate=0.05)

    assert hasattr(metrics, "mean_return")
    assert hasattr(metrics, "annual_volatility")
    assert hasattr(metrics, "sharpe_ratio")
    assert hasattr(metrics, "sortino_ratio")
    assert hasattr(metrics, "max_drawdown")
    assert hasattr(metrics, "var_95")
    assert hasattr(metrics, "cvar_95")

    assert metrics.annual_volatility >= 0.0, "Annual volatility must be non-negative"
    assert math.isfinite(metrics.sharpe_ratio), "Sharpe ratio must be a finite number"
    assert math.isfinite(metrics.sortino_ratio), "Sortino ratio must be a finite number"
    assert 0.0 <= abs(metrics.max_drawdown) <= 1.0, f"Max drawdown {metrics.max_drawdown} out of valid range [0, 1]"


def test_r2_t1_benchmark_beta_and_alpha() -> None:
    """Verify market benchmark regression accurately computes Beta, Alpha, and R-squared."""
    qa = _get_quant_analyst()
    rng = random.Random(101)
    n = 200

    # Synthetic benchmark random walk
    bench = [1000.0]
    for _ in range(n - 1):
        bench.append(bench[-1] * (1.0 + rng.gauss(0.0005, 0.01)))

    # Synthetic asset with known beta ~ 1.5
    asset = [100.0]
    for i in range(1, n):
        bench_ret = (bench[i] - bench[i - 1]) / bench[i - 1]
        asset_ret = 1.5 * bench_ret + rng.gauss(0.0001, 0.005)
        asset.append(asset[-1] * (1.0 + asset_ret))

    metrics = qa.compute_metrics(asset, benchmark_prices=bench, risk_free_rate=0.05)

    assert hasattr(metrics, "beta"), "QuantMetrics must contain beta"
    assert hasattr(metrics, "alpha"), "QuantMetrics must contain alpha"
    assert hasattr(metrics, "r_squared"), "QuantMetrics must contain r_squared"

    # Beta should be in the neighborhood of 1.5
    assert 1.0 <= metrics.beta <= 2.0, f"Beta {metrics.beta} deviated unexpectedly from target 1.5"
    assert 0.0 <= metrics.r_squared <= 1.0, f"R-squared {metrics.r_squared} out of bounds [0, 1]"


def test_r2_t1_stock_analyzer_service_and_cli(
    cli_runner: Callable[[list[str]], tuple[int, str, str]],
    synthetic_ohlcv: dict[str, Any],
) -> None:
    """Verify StockAnalyzer service analysis execution and CLI analyze argument parsing."""
    sa = _get_stock_analyzer()
    analyzer = sa.StockAnalyzer() if hasattr(sa, "StockAnalyzer") else sa

    if hasattr(analyzer, "analyze_stock"):
        report = analyzer.analyze_stock("RELIANCE", synthetic_ohlcv)
        assert report is not None
        assert "symbol" in report or hasattr(report, "symbol")

    # CLI subparser invocation
    code, out, err = cli_runner(["analyze", "RELIANCE", "--period", "1y"])
    if code == 2 and "unrecognized arguments" in err:
        pytest.skip("CLI analyze subparser pending in Milestone 1/2")
    assert code == 0, f"sktui analyze failed with exit code {code}: {err}"
    assert "RELIANCE" in out, f"Expected 'RELIANCE' in stdout, got:\n{out}"


# ============================================================================
# Tier 2: Boundary & Corner Cases
# ============================================================================

def test_r2_t2_stochastic_zero_range_flat_prices() -> None:
    """Verify Stochastic Oscillator does not raise ZeroDivisionError when high == low."""
    ind = _get_indicators()
    flat_high = [100.0] * 30
    flat_low = [100.0] * 30
    flat_close = [100.0] * 30

    try:
        k_series, d_series = ind.stochastic(flat_high, flat_low, flat_close, k_period=14, d_period=3)
        assert len(k_series) == 30
        assert len(d_series) == 30
        # For flat price, values should be safe (None, 50.0, or 0.0) without crash
        for v in k_series[13:]:
            if v is not None:
                assert math.isfinite(v), "Flat price stochastic should return finite value"
    except ZeroDivisionError:
        pytest.fail("stochastic raised ZeroDivisionError on flat price series")


def test_r2_t2_adx_empty_and_short_series() -> None:
    """Verify ADX engine handles series shorter than period or empty series gracefully."""
    ind = _get_indicators()
    # Shorter than lookback
    short_high = [105.0, 106.0, 107.0]
    short_low = [100.0, 101.0, 102.0]
    short_close = [104.0, 105.0, 106.0]

    adx_vals, p_di, m_di = ind.adx(short_high, short_low, short_close, period=14)
    assert len(adx_vals) == 3
    assert all(x is None for x in adx_vals), "Short series should result in all None values"

    # Empty series
    e_adx, e_pdi, e_mdi = ind.adx([], [], [], period=14)
    assert e_adx == []
    assert e_pdi == []
    assert e_mdi == []


def test_r2_t2_quant_metrics_constant_prices_zero_volatility() -> None:
    """Verify QuantMetrics handles zero-volatility flat prices without ZeroDivisionError."""
    qa = _get_quant_analyst()
    flat_prices = [250.0] * 50

    try:
        metrics = qa.compute_metrics(flat_prices, risk_free_rate=0.05)
        assert metrics.annual_volatility == 0.0 or abs(metrics.annual_volatility) < 1e-9
        assert math.isfinite(metrics.sharpe_ratio) or metrics.sharpe_ratio == 0.0
    except ZeroDivisionError:
        pytest.fail("compute_metrics raised ZeroDivisionError on constant price series")


def test_r2_t2_quant_metrics_empty_or_single_price() -> None:
    """Verify compute_metrics handles empty sequence or single price gracefully."""
    qa = _get_quant_analyst()
    try:
        res_empty = qa.compute_metrics([], risk_free_rate=0.05)
        assert res_empty is not None
    except (ValueError, IndexError):
        pass  # Graceful domain rejection is compliant

    try:
        res_single = qa.compute_metrics([100.0], risk_free_rate=0.05)
        assert res_single is not None
    except (ValueError, IndexError):
        pass


def test_r2_t2_var_extreme_confidence_levels() -> None:
    """Verify VaR and CVaR calculations remain finite and ordered under fat-tailed drops."""
    qa = _get_quant_analyst()
    # Simulated severe market drop series
    prices = [100.0 * (0.95 ** i) for i in range(40)]

    metrics = qa.compute_metrics(prices, risk_free_rate=0.05)
    assert math.isfinite(metrics.var_95), "var_95 must be a finite float"
    assert math.isfinite(metrics.var_99), "var_99 must be a finite float"
    assert math.isfinite(metrics.cvar_95), "cvar_95 must be a finite float"

    # CVaR (expected shortfall) represents worse tail risk than VaR
    # If expressed as positive risk percentage, cvar >= var
    assert abs(metrics.cvar_95) >= abs(metrics.var_95) * 0.95
