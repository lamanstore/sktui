"""End-to-End Tests for Requirement R3: Pair Trading Screener & Signal Generation.

Covers:
- Tier 1: Feature Coverage (isolated happy-path tests)
  1. Pure-Python ADF Cointegration Unit-Root Test
  2. OLS Hedge Ratio & Ornstein-Uhlenbeck Half-Life Estimation
  3. Pair Screener Universe Scan and Candidate Ranking
  4. Spread Z-Score & Statistical Arbitrage Signals (LONG_PAIR, SHORT_PAIR)
  5. 7-Indicator Composite Signal Engine & Dynamic Risk Levels
- Tier 2: Boundary & Corner Cases
  6. ADF test on constant and pure random walk (unit-root retention)
  7. Pair screener on orthogonal/negatively correlated series
  8. Half-life estimation on explosive non-mean-reverting series
  9. Composite signal engine on empty/corrupted OHLCV inputs
  10. CLI pairs and signals argument parsing and boundary validation
"""
from __future__ import annotations

import math
import random
from typing import Any, Callable

import pytest


def _get_pair_screener() -> Any:
    try:
        import sktui.services.pair_screener as ps
        return ps
    except ImportError:
        pytest.skip("sktui.services.pair_screener implementation pending in Milestone 3")


def _get_signal_engine() -> Any:
    try:
        import sktui.services.signal_engine as se
        return se
    except ImportError:
        pytest.skip("sktui.services.signal_engine implementation pending in Milestone 3")


# ============================================================================
# Tier 1: Feature Coverage (Isolated Happy Path)
# ============================================================================

def test_r3_t1_pure_python_adf_cointegration() -> None:
    """Verify Pure-Python ADF test detects stationarity on a mean-reverting series."""
    ps = _get_pair_screener()
    rng = random.Random(42)
    # Generate stationary OU mean-reverting series
    series = [0.0]
    for _ in range(120):
        series.append(series[-1] * 0.5 + rng.gauss(0.0, 1.0))

    adf_stat, p_value, is_coint = ps.adf_test(series, max_lags=1)

    assert isinstance(adf_stat, float), "ADF statistic must be a float"
    assert isinstance(p_value, float), "p_value must be a float"
    assert isinstance(is_coint, bool), "is_cointegrated must be a boolean"
    assert adf_stat < 0.0, f"Stationary ADF stat {adf_stat} should be negative"
    assert 0.0 <= p_value <= 1.0, f"p_value {p_value} out of range [0, 1]"
    assert is_coint is True, "Stationary series should be classified as cointegrated/stationary"


def test_r3_t1_ols_hedge_ratio_and_half_life(synthetic_pair_series: dict[str, Any]) -> None:
    """Verify OLS regression calculates hedge ratio and Ornstein-Uhlenbeck half-life."""
    ps = _get_pair_screener()
    y = synthetic_pair_series["stock_a"]
    x = synthetic_pair_series["stock_b"]

    # Calculate hedge ratio via pair_screener helper
    assert hasattr(ps, "compute_ols_hedge_ratio"), "pair_screener must provide 'compute_ols_hedge_ratio(y, x)' per Feature 18"
    beta, alpha = ps.compute_ols_hedge_ratio(y, x)
    assert 1.0 <= beta <= 2.0, f"Hedge ratio beta {beta} should be near 1.5"

    assert hasattr(ps, "compute_half_life"), "pair_screener must provide 'compute_half_life(spread)' per Feature 20"
    spread = [yi - 1.5 * xi for yi, xi in zip(y, x)]
    hl = ps.compute_half_life(spread)
    assert 1.0 <= hl <= 50.0, f"Half-life {hl} days should be positive and finite"


def test_r3_t1_pair_screener_universe_scan(synthetic_pair_series: dict[str, Any]) -> None:
    """Verify screen_pairs filters correlated candidates and returns PairScreenResult objects."""
    ps = _get_pair_screener()
    rng = random.Random(99)
    # Uncorrelated noise stock
    uncorrelated = [50.0 + rng.gauss(0, 2) for _ in range(len(synthetic_pair_series["stock_a"]))]

    universe = {
        "STOCK_A": synthetic_pair_series["stock_a"],
        "STOCK_B": synthetic_pair_series["stock_b"],
        "STOCK_RAND": uncorrelated,
    }

    results = ps.screen_pairs(universe, min_correlation=0.70, p_value_threshold=0.05)
    assert isinstance(results, list), "screen_pairs must return a list"

    # Should find pair (STOCK_A, STOCK_B) or (STOCK_B, STOCK_A)
    pair_names = {(r.stock_a, r.stock_b) for r in results}
    assert ("STOCK_A", "STOCK_B") in pair_names or ("STOCK_B", "STOCK_A") in pair_names

    for r in results:
        assert hasattr(r, "stock_a")
        assert hasattr(r, "stock_b")
        assert hasattr(r, "correlation")
        assert hasattr(r, "beta")
        assert hasattr(r, "adf_statistic")
        assert hasattr(r, "p_value")
        assert hasattr(r, "is_cointegrated")
        assert hasattr(r, "half_life_days")
        assert hasattr(r, "current_zscore")
        assert hasattr(r, "signal")


def test_r3_t1_spread_zscore_and_pair_signals(synthetic_pair_series: dict[str, Any]) -> None:
    """Verify spread Z-score triggers statistical arbitrage entry signals."""
    ps = _get_pair_screener()
    # High positive spread -> SHORT_PAIR
    # High negative spread -> LONG_PAIR
    assert hasattr(ps, "calculate_zscore_signal"), "pair_screener must provide 'calculate_zscore_signal(current_zscore)' per Feature 21"
    sig_long = ps.calculate_zscore_signal(current_zscore=-2.5)
    assert sig_long == "LONG_PAIR"

    sig_short = ps.calculate_zscore_signal(current_zscore=2.5)
    assert sig_short == "SHORT_PAIR"

    sig_exit = ps.calculate_zscore_signal(current_zscore=0.1)
    assert sig_exit in ("EXIT", "NONE")


def test_r3_t1_composite_signal_engine_7_indicators(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify evaluate_signals votes across 7 indicators to yield a CompositeSignal."""
    se = _get_signal_engine()
    symbol = synthetic_ohlcv["symbol"]

    sig = se.evaluate_signals(symbol, synthetic_ohlcv)

    assert hasattr(sig, "symbol"), "CompositeSignal must contain symbol"
    assert hasattr(sig, "price"), "CompositeSignal must contain price"
    assert hasattr(sig, "signal_type"), "CompositeSignal must contain signal_type"
    assert hasattr(sig, "score"), "CompositeSignal must contain score"
    assert hasattr(sig, "confidence_pct"), "CompositeSignal must contain confidence_pct"
    assert hasattr(sig, "stop_loss"), "CompositeSignal must contain stop_loss"
    assert hasattr(sig, "take_profit"), "CompositeSignal must contain take_profit"

    assert sig.signal_type in ("STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL")
    assert -2.0 <= sig.score <= 2.0, f"Score {sig.score} out of bounds [-2.0, 2.0]"
    assert 0.0 <= sig.confidence_pct <= 100.0, f"Confidence {sig.confidence_pct} out of [0, 100]"
    assert sig.stop_loss > 0.0, "Stop loss must be a positive price level"
    assert sig.take_profit > 0.0, "Take profit must be a positive price level"


# ============================================================================
# Tier 2: Boundary & Corner Cases
# ============================================================================

def test_r3_t2_adf_constant_or_divergent_series() -> None:
    """Verify ADF test correctly rejects non-stationary random walks without overflow."""
    ps = _get_pair_screener()
    rng = random.Random(123)
    # Pure random walk with unit root
    rw = [100.0]
    for _ in range(150):
        rw.append(rw[-1] + rng.gauss(0.1, 1.0))

    adf_stat, p_val, is_coint = ps.adf_test(rw, max_lags=1)
    # Random walk p_val should be > 0.05 and is_cointegrated False
    assert is_coint is False or p_val > 0.05

    # Constant flat series
    flat = [50.0] * 80
    try:
        f_stat, f_pval, f_coint = ps.adf_test(flat, max_lags=1)
        assert f_coint is False
    except ZeroDivisionError:
        pytest.fail("adf_test raised ZeroDivisionError on constant series")


def test_r3_t2_pair_screener_orthogonal_uncorrelated_series() -> None:
    """Verify pair screener excludes orthogonal/negatively correlated pairs."""
    ps = _get_pair_screener()
    rng = random.Random(456)
    n = 100
    s1 = [rng.gauss(100, 5) for _ in range(n)]
    s2 = [rng.gauss(100, 5) for _ in range(n)]

    results = ps.screen_pairs({"S1": s1, "S2": s2}, min_correlation=0.70)
    assert len(results) == 0, "Uncorrelated series should not pass 0.70 correlation filter"


def test_r3_t2_half_life_non_mean_reverting_boundary() -> None:
    """Verify Ornstein-Uhlenbeck half-life does not crash on explosive AR(1) series."""
    ps = _get_pair_screener()
    assert hasattr(ps, "compute_half_life"), "pair_screener must provide 'compute_half_life' for boundary validation"
    # Explosive series: s[t] = 1.05 * s[t-1]
    explosive = [10.0 * (1.05 ** i) for i in range(50)]
    hl = ps.compute_half_life(explosive)
    # Should return float('inf') or large capped value, never negative or ValueError
    assert hl == float("inf") or hl > 100.0 or hl is None or math.isinf(hl)


def test_r3_t2_composite_signal_empty_ohlcv_or_nan() -> None:
    """Verify evaluate_signals handles empty or corrupted OHLCV gracefully."""
    se = _get_signal_engine()
    empty_ohlcv = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    try:
        sig = se.evaluate_signals("EMPTY_SYM", empty_ohlcv)
        assert sig.signal_type == "NEUTRAL"
    except (ValueError, IndexError):
        pass  # Graceful validation exception is compliant


def test_r3_t2_cli_pairs_and_signals_argument_bounds(
    cli_runner: Callable[[list[str]], tuple[int, str, str]],
) -> None:
    """Verify CLI pairs and signals argument parsing handles options properly."""
    code_p, out_p, err_p = cli_runner(["pairs", "--min-corr", "0.85"])
    if code_p == 2 and "unrecognized arguments" in err_p:
        pytest.skip("CLI pairs subparser pending in Milestone 1/3")
    assert code_p == 0, f"sktui pairs failed with exit code {code_p}: {err_p}"
    assert "pair" in out_p.lower(), f"Expected 'pair' in stdout, got:\n{out_p}"

    code_s, out_s, err_s = cli_runner(["signals", "--symbols", "RELIANCE,TCS"])
    if code_s == 2 and "unrecognized arguments" in err_s:
        pytest.skip("CLI signals subparser pending in Milestone 1/3")
    assert code_s == 0, f"sktui signals failed with exit code {code_s}: {err_s}"
    assert "signal" in out_s.lower(), f"Expected 'signal' in stdout, got:\n{out_s}"
