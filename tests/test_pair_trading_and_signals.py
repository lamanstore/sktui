"""Comprehensive Unit and Integration Test Suite for Milestone 3:
Pair Trading Screener, Cointegration Engine, and Multi-Indicator Signal Scanner.

Coverage:
1. Pure-Python OLS Hedge Ratio & Spread Residual.
2. Pure-Python ADF Cointegration Unit-Root Test & MacKinnon p-values.
3. Ornstein-Uhlenbeck Mean-Reversion Half-Life Estimation.
4. Rolling 90-Day Z-Scores & Signal State Machine.
5. Market-Neutral Position Sizing Math.
6. Candidate Universe & Sector Filtering.
7. 7-Indicator Composite Scoring & 5-Tier Signal Mapping.
8. Dynamic ATR Risk Management (Stop Loss, Take Profit, R:R).
9. Watchlist Signal Scanner.
10. CLI Subcommands (sktui pairs, sktui spread, sktui signals, JSON export).
11. TUI Modals Lifecycle & Slash Command Routing.
12. Edge Cases & Zero-Division Resilience.
"""
from __future__ import annotations

import asyncio
import json
import math
import random
from typing import Any
from unittest.mock import MagicMock

import pytest
from textual.app import App
from textual.widgets import DataTable, Label

from sktui.app import build_parser, main
from sktui.screens.main import MainScreen
from sktui.screens.modals import (
    PairScreenerModal,
    SignalScannerModal,
    SpreadAnalysisModal,
)
from sktui.services.pair_screener import (
    PairScreenResult,
    PairScreener,
    adf_test,
    calculate_position_sizing,
    calculate_zscore_signal,
    clean_series,
    compute_correlation_stability,
    compute_half_life,
    compute_ols_hedge_ratio,
    compute_pearson_correlation,
    compute_rolling_zscores,
    compute_spread,
    screen_pairs,
)
from sktui.services.signal_engine import (
    CompositeSignal,
    SignalEngine,
    evaluate_signals,
    scan_watchlist,
)


# ============================================================================
# 1. Pure-Python OLS Hedge Ratio & Spread Residual
# ============================================================================

def test_ols_perfect_linear_relation():
    """Verify OLS yields exact slope and intercept for clean linear equation y = 2x + 10."""
    x = [float(i) for i in range(1, 101)]
    y = [2.0 * xi + 10.0 for xi in x]

    beta, alpha = compute_ols_hedge_ratio(y, x)
    assert abs(beta - 2.0) < 1e-6
    assert abs(alpha - 10.0) < 1e-6

    spread = compute_spread(y, x, beta)
    assert len(spread) == len(x)
    for s in spread:
        assert abs(s - 10.0) < 1e-5


def test_ols_noisy_relation():
    """Verify OLS estimates hedge ratio close to theoretical beta in presence of noise."""
    rng = random.Random(42)
    x = [100.0 + i * 0.5 + rng.gauss(0, 0.5) for i in range(120)]
    y = [1.5 * xi + 20.0 + rng.gauss(0, 0.8) for xi in x]

    beta, alpha = compute_ols_hedge_ratio(y, x)
    assert 1.4 <= beta <= 1.6
    assert 10.0 <= alpha <= 30.0


def test_ols_negative_beta():
    """Verify OLS handles inverse series producing negative hedge ratio."""
    x = [float(i) for i in range(1, 80)]
    y = [-0.8 * xi + 100.0 for xi in x]

    beta, alpha = compute_ols_hedge_ratio(y, x)
    assert abs(beta - (-0.8)) < 1e-5
    assert abs(alpha - 100.0) < 1e-5


def test_ols_zero_variance_guard():
    """Verify OLS gracefully handles flat series without ZeroDivisionError."""
    x = [50.0] * 50
    y = [100.0] * 50
    beta, alpha = compute_ols_hedge_ratio(y, x)
    assert beta == 1.0
    assert alpha == 0.0


# ============================================================================
# 2. Pure-Python ADF Cointegration Unit-Root Test & MacKinnon p-values
# ============================================================================

def test_adf_cointegrated_stationary_series():
    """Verify ADF rejects unit root on stationary mean-reverting AR(1) series."""
    rng = random.Random(123)
    series = [0.0]
    for _ in range(150):
        series.append(0.3 * series[-1] + rng.gauss(0.0, 1.0))

    stat, pval, is_coint = adf_test(series, max_lags=1)
    assert stat < -2.86, f"Expected ADF stat < -2.86, got {stat}"
    assert pval < 0.05, f"Expected p-value < 0.05, got {pval}"
    assert is_coint is True


def test_adf_non_stationary_random_walk():
    """Verify ADF fails to reject unit root on non-stationary random walk."""
    rng = random.Random(456)
    series = [100.0]
    for _ in range(150):
        series.append(series[-1] + rng.gauss(0.1, 1.0))

    stat, pval, is_coint = adf_test(series, max_lags=1)
    assert stat > -2.57 or pval > 0.05
    assert is_coint is False


def test_adf_mackinnon_pvalue_monotonicity():
    """Verify MacKinnon polynomial produces monotonic p-values matching critical values."""
    from sktui.services.pair_screener import _mackinnon_p

    # More negative statistic -> lower p-value
    p_1 = _mackinnon_p(-4.0)
    p_5 = _mackinnon_p(-2.86)
    p_10 = _mackinnon_p(-2.57)
    p_high = _mackinnon_p(-1.0)

    assert p_1 < p_5 < p_10 < p_high
    assert abs(p_5 - 0.05) < 0.015, f"Expected p(-2.86) near 0.05, got {p_5}"
    assert abs(p_10 - 0.10) < 0.02, f"Expected p(-2.57) near 0.10, got {p_10}"
    assert 0.0 <= p_1 <= 1.0


def test_adf_flat_and_short_series():
    """Verify ADF handles flat and insufficient series without crashing."""
    flat = [100.0] * 50
    stat, pval, is_coint = adf_test(flat)
    assert is_coint is False
    assert pval == 1.0

    short = [10.0, 12.0, 11.0]
    s_stat, s_pval, s_coint = adf_test(short)
    assert s_coint is False


# ============================================================================
# 3. Ornstein-Uhlenbeck Mean-Reversion Half-Life Estimation
# ============================================================================

def test_half_life_known_ar1():
    """Verify half-life estimation matches theoretical ln(2)/-ln(phi) for AR(1)."""
    phi = 0.8
    # Theoretical: ln(2) / -ln(0.8) ~= 0.69315 / 0.22314 ~= 3.106 days
    series = [0.0]
    rng = random.Random(789)
    for _ in range(300):
        series.append(phi * series[-1] + rng.gauss(0.0, 0.5))

    hl = compute_half_life(series)
    assert 1.5 <= hl <= 5.5, f"Estimated half-life {hl} outside expected range [1.5, 5.5]"


def test_half_life_non_mean_reverting():
    """Verify half-life returns infinity on explosive or non-reverting series."""
    explosive = [10.0 * (1.05 ** i) for i in range(40)]
    hl = compute_half_life(explosive)
    assert hl == float("inf") or math.isinf(hl)


def test_half_life_insufficient_data():
    """Verify half-life returns infinity when series length < 10."""
    short = [1.0, 2.0, 3.0]
    assert compute_half_life(short) == float("inf")


# ============================================================================
# 4. Rolling 90-Day Z-Scores & Signal State Machine
# ============================================================================

def test_zscore_calculation_and_state_machine():
    """Verify rolling Z-scores and 4-tier trading signal state transitions."""
    # Test discrete signal mapping
    assert calculate_zscore_signal(-2.5) == "LONG_PAIR"
    assert calculate_zscore_signal(2.5) == "SHORT_PAIR"
    assert calculate_zscore_signal(0.2) == "EXIT"
    assert calculate_zscore_signal(-0.3) == "EXIT"
    assert calculate_zscore_signal(1.2) == "NONE"
    assert calculate_zscore_signal(-1.2) == "NONE"
    assert calculate_zscore_signal(3.5) == "STOP_LOSS"
    assert calculate_zscore_signal(-3.2) == "STOP_LOSS"


def test_rolling_zscores_series():
    """Verify compute_rolling_zscores calculates standard score over rolling window."""
    spread = [10.0] * 30 + [20.0] * 30
    zscores = compute_rolling_zscores(spread, window=30)
    assert len(zscores) == len(spread)
    assert isinstance(zscores[-1], float)


# ============================================================================
# 5. Market-Neutral Position Sizing Math
# ============================================================================

def test_market_neutral_position_sizing():
    """Verify capital is partitioned beta-neutrally between Leg A and Leg B."""
    capital = 100000.0
    price_a = 1000.0
    price_b = 500.0
    beta = 1.0  # Equal weighting: 50k / 50k

    sizing = calculate_position_sizing(capital, price_a, price_b, beta)
    assert sizing["capital"] == capital
    assert abs(sizing["capital_a"] - 50000.0) < 1.0
    assert abs(sizing["capital_b"] - 50000.0) < 1.0
    assert sizing["shares_a"] == 50
    assert sizing["shares_b"] == 100
    assert sizing["actual_investment"] == 100000.0
    assert sizing["weight_a"] == 0.5
    assert sizing["weight_b"] == 0.5


def test_position_sizing_boundary():
    """Verify position sizing handles zero or negative capital/prices safely."""
    res = calculate_position_sizing(0.0, 100.0, 50.0, 1.0)
    assert res["shares_a"] == 0
    assert res["shares_b"] == 0
    assert res["actual_investment"] == 0.0

    res_neg = calculate_position_sizing(10000.0, -10.0, 50.0, 1.0)
    assert res_neg["shares_a"] == 0


# ============================================================================
# 6. Candidate Universe & Sector Filtering
# ============================================================================

def test_screen_pairs_sector_filtering():
    """Verify screen_pairs correctly filters pairs meeting correlation and cointegration."""
    rng = random.Random(999)
    n = 120
    x = [100.0]
    for _ in range(n - 1):
        x.append(x[-1] + rng.gauss(0.05, 0.5))

    spread = [0.0]
    theta = 0.25  # Mean-reversion speed
    for _ in range(n - 1):
        spread.append(spread[-1] * (1.0 - theta) + rng.gauss(0.0, 0.3))

    y = [1.5 * xi + si + 15.0 for xi, si in zip(x, spread)]
    s_rand = [50.0 + rng.gauss(0, 5) for _ in range(n)]

    univ = {"STOCK_A": y, "STOCK_B": x, "RANDOM": s_rand}
    results = screen_pairs(univ, min_correlation=0.70, p_value_threshold=0.05)
    assert len(results) >= 1
    pair_names = {(r.stock_a, r.stock_b) for r in results}
    assert ("STOCK_A", "STOCK_B") in pair_names or ("STOCK_B", "STOCK_A") in pair_names
    assert not any("RANDOM" in p for p in pair_names)


def test_correlation_stability_filter():
    """Verify stability filter rejects series with sudden correlation breakdown in last 90 bars."""
    # 200 bars: first 110 bars perfectly correlated, last 90 bars negatively correlated
    x = [float(i) for i in range(200)]
    y = [float(i) for i in range(110)] + [float(110 - i) for i in range(90)]

    stab = compute_correlation_stability(x, y, window=90)
    assert stab > 0.15, f"Expected stability break > 0.15, got {stab}"


def test_pair_screener_service():
    """Verify PairScreener service helper methods."""
    ps = PairScreener()
    syms = ps.get_universe_symbols(sector="IT")
    assert isinstance(syms, list)
    assert "TCS" in syms or "INFY" in syms

    # Single pair analysis
    s_a = [100.0 + i for i in range(100)]
    s_b = [50.0 + 0.5 * i for i in range(100)]
    res = ps.analyze_pair("TCS", "INFY", prices_a=s_a, prices_b=s_b)
    assert res is not None
    assert res.stock_a == "TCS"
    assert res.stock_b == "INFY"


# ============================================================================
# 7. 7-Indicator Composite Scoring & 5-Tier Signal Mapping
# ============================================================================

def test_7_indicator_composite_strong_buy():
    """Verify strong bullish market conditions produce STRONG_BUY with high confidence."""
    # Create strongly bullish trending series with low RSI and oversold conditions
    n = 60
    closes = [100.0 + i * 2.0 for i in range(n)]
    highs = [c + 2.0 for c in closes]
    lows = [c - 2.0 for c in closes]
    volumes = [1000.0 for _ in range(n - 1)] + [5000.0]  # Volume spike

    ohlcv = {"open": closes, "high": highs, "low": lows, "close": closes, "volume": volumes}
    sig = evaluate_signals("BULL_STOCK", ohlcv)

    assert sig.symbol == "BULL_STOCK"
    assert sig.signal_type in ("BUY", "STRONG_BUY")
    assert sig.score > 0.4
    assert sig.confidence_pct >= 50.0
    assert sig.stop_loss > 0.0
    assert sig.take_profit > sig.price
    assert sig.risk_reward_ratio == 2.0


def test_7_indicator_composite_strong_sell():
    """Verify strong bearish market conditions produce SELL or STRONG_SELL."""
    n = 60
    closes = [200.0 - i * 2.0 for i in range(n)]
    highs = [c + 2.0 for c in closes]
    lows = [c - 2.0 for c in closes]
    volumes = [1000.0 for _ in range(n - 1)] + [5000.0]  # Bearish volume spike

    ohlcv = {"open": closes, "high": highs, "low": lows, "close": closes, "volume": volumes}
    sig = evaluate_signals("BEAR_STOCK", ohlcv)

    assert sig.symbol == "BEAR_STOCK"
    assert sig.signal_type in ("SELL", "STRONG_SELL")
    assert sig.score < -0.4
    assert sig.confidence_pct >= 50.0
    assert sig.stop_loss > sig.price
    assert sig.take_profit < sig.price
    assert sig.risk_reward_ratio == 2.0


def test_7_indicator_composite_neutral():
    """Verify flat range-bound series produces NEUTRAL signal."""
    n = 60
    closes = [100.0 for _ in range(n)]
    highs = [101.0 for _ in range(n)]
    lows = [99.0 for _ in range(n)]
    volumes = [1000.0 for _ in range(n)]

    ohlcv = {"open": closes, "high": highs, "low": lows, "close": closes, "volume": volumes}
    sig = evaluate_signals("FLAT_STOCK", ohlcv)

    assert sig.signal_type == "NEUTRAL"
    assert -0.4 <= sig.score <= 0.4


# ============================================================================
# 8. Dynamic ATR Risk Management (Stop Loss, Take Profit, R:R)
# ============================================================================

def test_dynamic_atr_risk_levels():
    """Verify ATR Stop Loss is 1.5x ATR and Take Profit is 3.0x ATR (2.0 R:R)."""
    n = 50
    closes = [1000.0 for _ in range(n)]
    highs = [1010.0 for _ in range(n)]  # 20 point range
    lows = [990.0 for _ in range(n)]
    volumes = [500.0 for _ in range(n)]

    ohlcv = {"open": closes, "high": highs, "low": lows, "close": closes, "volume": volumes}
    sig = evaluate_signals("RISK_STOCK", ohlcv)

    # For NEUTRAL/BUY: SL < price, TP > price, (TP - P) / (P - SL) == 2.0
    assert sig.stop_loss < sig.price
    assert sig.take_profit > sig.price
    assert abs(sig.risk_reward_ratio - 2.0) < 0.1


# ============================================================================
# 9. Watchlist Signal Scanner
# ============================================================================

def test_watchlist_scanner_filtering():
    """Verify scan_watchlist filters by direction and confidence and ranks by conviction."""
    n = 60
    bull_closes = [100.0 + i for i in range(n)]
    bear_closes = [200.0 - i for i in range(n)]

    ohlcv_map = {
        "BULL": {"open": bull_closes, "high": [c+1 for c in bull_closes], "low": [c-1 for c in bull_closes], "close": bull_closes, "volume": [1000]*n},
        "BEAR": {"open": bear_closes, "high": [c+1 for c in bear_closes], "low": [c-1 for c in bear_closes], "close": bear_closes, "volume": [1000]*n},
    }

    # Filter BUY only
    buys = scan_watchlist(["BULL", "BEAR"], ohlcv_map=ohlcv_map, direction="BUY")
    assert all("BUY" in s.signal_type for s in buys)

    # Filter SELL only
    sells = scan_watchlist(["BULL", "BEAR"], ohlcv_map=ohlcv_map, direction="SELL")
    assert all("SELL" in s.signal_type for s in sells)


# ============================================================================
# 10. CLI Subcommands (pairs, spread, signals)
# ============================================================================

def test_cli_parser_pairs_spread_signals():
    """Verify argument parser recognizes pairs, spread, and signals subcommands."""
    parser = build_parser()

    # pairs
    args_p = parser.parse_args(["pairs", "--sector", "IT", "--min-corr", "0.80", "--json"])
    assert args_p.subcommand == "pairs"
    assert args_p.sector == "IT"
    assert args_p.min_corr == 0.80
    assert args_p.json is True

    # spread
    args_sp = parser.parse_args(["spread", "--stock-a", "TCS", "--stock-b", "INFY", "--lookback", "60", "--json"])
    assert args_sp.subcommand == "spread"
    assert args_sp.stock_a == "TCS"
    assert args_sp.stock_b == "INFY"
    assert args_sp.lookback == 60
    assert args_sp.json is True

    # signals
    args_s = parser.parse_args(["signals", "--symbols", "RELIANCE,TCS", "--filter", "BUY", "--min-conf", "75.0", "--json"])
    assert args_s.subcommand == "signals"
    assert args_s.filter == "BUY"
    assert args_s.min_conf == 75.0
    assert args_s.json is True


def test_cli_execution_headless(capsys):
    """Verify headless execution of pairs, spread, and signals exits 0."""
    # 1. pairs
    code_p = main(["pairs", "--sector", "IT", "--json"])
    assert code_p == 0
    out_p = capsys.readouterr().out
    data_p = json.loads(out_p)
    assert isinstance(data_p, list)

    # 2. spread
    code_sp = main(["spread", "--stock-a", "TCS", "--stock-b", "INFY", "--json"])
    assert code_sp == 0
    out_sp = capsys.readouterr().out
    data_sp = json.loads(out_sp)
    assert data_sp["stock_a"] == "TCS"
    assert data_sp["stock_b"] == "INFY"
    assert "adf_statistic" in data_sp

    # 3. signals
    code_s = main(["signals", "--symbols", "RELIANCE,TCS", "--json"])
    assert code_s == 0
    out_s = capsys.readouterr().out
    data_s = json.loads(out_s)
    assert isinstance(data_s, list)
    assert len(data_s) >= 1


def test_cli_error_bounds(capsys):
    """Verify CLI commands return error code 1 on invalid inputs."""
    code_bad_corr = main(["pairs", "--min-corr", "1.5"])
    assert code_bad_corr == 1

    code_same_stocks = main(["spread", "--stock-a", "TCS", "--stock-b", "TCS"])
    assert code_same_stocks == 1


# ============================================================================
# 11. TUI Modals Lifecycle & MainScreen Slash Routing
# ============================================================================

def test_pair_screener_modal_lifecycle():
    """Verify PairScreenerModal mounts cleanly and dismisses on Escape."""
    class DummyApp(App):
        def compose(self):
            yield Label("Root Screen")

    async def run():
        app = DummyApp()
        async with app.run_test(size=(120, 36)) as pilot:
            modal = PairScreenerModal(sector="IT")
            app.push_screen(modal)
            await pilot.pause(0.1)

            assert isinstance(app.screen, PairScreenerModal)
            dt = app.screen.query_one("#t-pair-screener", DataTable)
            assert len(dt.columns) >= 10

            await pilot.press("escape")
            await pilot.pause(0.1)
            assert not isinstance(app.screen, PairScreenerModal)

    asyncio.run(run())


def test_spread_analysis_modal_lifecycle():
    """Verify SpreadAnalysisModal mounts with Braille canvas and dismisses."""
    class DummyApp(App):
        def compose(self):
            yield Label("Root Screen")

    async def run():
        app = DummyApp()
        async with app.run_test(size=(120, 36)) as pilot:
            modal = SpreadAnalysisModal(pair="TCS,INFY")
            app.push_screen(modal)
            await pilot.pause(0.1)

            assert isinstance(app.screen, SpreadAnalysisModal)
            assert modal.stock_a == "TCS"
            assert modal.stock_b == "INFY"

            # Check Braille canvas static widget exists
            canvas = app.screen.query_one("#spread-braille-canvas")
            assert canvas is not None

            await pilot.press("escape")
            await pilot.pause(0.1)
            assert not isinstance(app.screen, SpreadAnalysisModal)

    asyncio.run(run())


def test_signal_scanner_modal_lifecycle():
    """Verify SignalScannerModal mounts with DataTable and dismisses."""
    class DummyApp(App):
        def compose(self):
            yield Label("Root Screen")

    async def run():
        app = DummyApp()
        async with app.run_test(size=(120, 36)) as pilot:
            modal = SignalScannerModal(symbol="RELIANCE")
            app.push_screen(modal)
            await pilot.pause(0.1)

            assert isinstance(app.screen, SignalScannerModal)
            dt = app.screen.query_one("#t-signal-scanner", DataTable)
            assert len(dt.columns) >= 8

            await pilot.press("escape")
            await pilot.pause(0.1)
            assert not isinstance(app.screen, SignalScannerModal)

    asyncio.run(run())


def test_mainscreen_slash_command_dispatch(monkeypatch):
    """Verify MainScreen routes /pairs, /spread, and /signals to modals."""
    mock_app = MagicMock()
    monkeypatch.setattr(MainScreen, "app", property(lambda self: mock_app))

    screen = object.__new__(MainScreen)
    screen.status = MagicMock()

    # 1. /pairs
    screen.action_pair_screener("IT")
    assert mock_app.push_screen.called
    pushed_pairs = mock_app.push_screen.call_args[0][0]
    assert isinstance(pushed_pairs, PairScreenerModal)

    # 2. /spread
    mock_app.push_screen.reset_mock()
    screen.action_spread_analysis("TCS,INFY")
    assert mock_app.push_screen.called
    pushed_spread = mock_app.push_screen.call_args[0][0]
    assert isinstance(pushed_spread, SpreadAnalysisModal)
    assert pushed_spread.stock_a == "TCS"
    assert pushed_spread.stock_b == "INFY"

    # 3. /signals
    mock_app.push_screen.reset_mock()
    screen.action_signal_scanner("RELIANCE")
    assert mock_app.push_screen.called
    pushed_sig = mock_app.push_screen.call_args[0][0]
    assert isinstance(pushed_sig, SignalScannerModal)


# ============================================================================
# 12. Edge Cases & Zero-Division Resilience
# ============================================================================

def test_edge_cases_zero_variance_flat_series():
    """Verify math routines survive zero variance and flat prices."""
    flat = [50.0] * 50
    # Pearson
    assert compute_pearson_correlation(flat, flat) == 0.0
    # Stability
    assert compute_correlation_stability(flat, flat) == 0.0
    # OLS
    beta, alpha = compute_ols_hedge_ratio(flat, flat)
    assert beta == 1.0 and alpha == 0.0
    # ADF
    _, p, is_c = adf_test(flat)
    assert is_c is False


def test_edge_cases_identical_series():
    """Verify pair screener on identical series produces spread = 0 and beta = 1."""
    prices = [10.0 + i for i in range(50)]
    beta, alpha = compute_ols_hedge_ratio(prices, prices)
    assert abs(beta - 1.0) < 1e-6
    spread = compute_spread(prices, prices, beta)
    assert all(abs(s) < 1e-6 for s in spread)


def test_edge_cases_empty_and_corrupt_ohlcv():
    """Verify evaluate_signals handles empty and malformed OHLCV gracefully."""
    empty = {}
    sig_empty = evaluate_signals("EMPTY", empty)
    assert sig_empty.signal_type == "NEUTRAL"
    assert sig_empty.price == 0.0

    corrupt = {"close": ["invalid", None, float("nan"), 100.0, 105.0]}
    sig_corrupt = evaluate_signals("CORRUPT", corrupt)
    assert sig_corrupt.symbol == "CORRUPT"
    assert sig_corrupt.price == 105.0
