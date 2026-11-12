"""Comprehensive Unit and Integration Test Suite for Milestone 2:
Quantitative & Stock Analysis Integration.

Coverage:
1. Pure-Python Indicator Math and Edge Cases (Stochastic, ADX, MA Slope, Trend Strength, Linear Regression).
2. Quant Risk Analytics & Benchmark Regression (QuantMetrics, compute_metrics, VaR/CVaR, Beta/Alpha/R2).
3. StockAnalyzer Service (Full analysis, dual access, 5-tier signals, multi-stock ranking).
4. CLI Subcommand Invocations (sktui analyze, sktui compare).
5. QuantAnalysisModal UI Lifecycle & MainScreen Action Routing.
"""
from __future__ import annotations

import asyncio
import math
import random
from typing import Any

import pytest
from textual.app import App
from textual.widgets import Label

from sktui.app import build_parser, main
from sktui.screens.modals import QuantAnalysisModal, StockAnalysisModal
from sktui.services.indicators import (
    adx,
    linear_regression_slope,
    ma_slope,
    stochastic,
    trend_strength,
)
from sktui.services.quant_analyst import QuantMetrics, compute_metrics
from sktui.services.stock_analyzer import StockAnalysisResult, StockAnalyzer


# ============================================================================
# 1. Pure-Python Technical Indicators
# ============================================================================

def test_stochastic_standard_series():
    """Verify stochastic oscillator computes %K and %D within [0, 100]."""
    high = [10.0 + i for i in range(30)]
    low = [5.0 + i for i in range(30)]
    close = [10.0 + i for i in range(30)]

    k, d = stochastic(high, low, close, k_period=14, d_period=3)
    assert len(k) == 30
    assert len(d) == 30

    # Initial 13 elements should be None
    for i in range(13):
        assert k[i] is None

    # Uptrend should produce high %K and %D
    valid_k = [x for x in k if x is not None]
    valid_d = [x for x in d if x is not None]
    assert len(valid_k) > 0
    assert len(valid_d) > 0
    assert all(0.0 <= x <= 100.0 for x in valid_k)
    assert all(0.0 <= x <= 100.0 for x in valid_d)
    assert k[-1] == 100.0
    assert d[-1] > 90.0


def test_stochastic_downtrend_series():
    """Verify stochastic oscillator properly registers oversold on falling series."""
    high = [50.0 - i for i in range(30)]
    low = [45.0 - i for i in range(30)]
    close = [45.0 - i for i in range(30)]

    k, d = stochastic(high, low, close, k_period=14, d_period=3)
    assert k[-1] == 0.0
    assert d[-1] < 10.0


def test_stochastic_flat_and_edge_cases():
    """Verify stochastic avoids ZeroDivisionError and handles short/empty series."""
    flat = [100.0] * 30
    k, d = stochastic(flat, flat, flat, k_period=14, d_period=3)
    assert len(k) == 30
    for v in k[13:]:
        assert v == 50.0
    for v in d[15:]:
        assert v == 50.0

    # Empty and short series
    assert stochastic([], [], []) == ([], [])
    k_short, d_short = stochastic([100.0] * 5, [90.0] * 5, [95.0] * 5, k_period=14)
    assert k_short == [None] * 5
    assert d_short == [None] * 5

    # Keyword resolution (highs, lows, closes)
    k_kw, d_kw = stochastic(highs=flat, lows=flat, closes=flat, k_period=14)
    assert len(k_kw) == 30

    # Invalid lookbacks
    k_inv, d_inv = stochastic(flat, flat, flat, k_period=-5, d_period=0)
    assert all(x is None for x in k_inv)


def test_adx_standard_series():
    """Verify ADX computes directional movement and index values correctly."""
    # Strong uptrend: higher highs and higher lows
    high = [100.0 + i * 2.0 for i in range(50)]
    low = [95.0 + i * 2.0 for i in range(50)]
    close = [98.0 + i * 2.0 for i in range(50)]

    adx_vals, plus_di, minus_di = adx(high, low, close, period=14)
    assert len(adx_vals) == 50
    assert len(plus_di) == 50
    assert len(minus_di) == 50

    # Latency: first valid ADX at index 27 (2 * period - 1)
    for i in range(27):
        assert adx_vals[i] is None
    assert adx_vals[27] is not None
    assert 0.0 <= adx_vals[-1] <= 100.0

    # In a strong uptrend, +DI must dominate -DI
    assert plus_di[-1] > minus_di[-1]
    assert minus_di[-1] == 0.0


def test_adx_flat_and_edge_cases():
    """Verify ADX avoids zero division on flat markets and handles empty inputs."""
    flat = [100.0] * 50
    adx_vals, plus_di, minus_di = adx(flat, flat, flat, period=14)
    assert len(adx_vals) == 50
    for v in adx_vals:
        if v is not None:
            assert v == 0.0
    for v in plus_di:
        if v is not None:
            assert v == 0.0
    for v in minus_di:
        if v is not None:
            assert v == 0.0

    # Empty inputs
    assert adx([], [], []) == ([], [], [])

    # Insufficient length
    a_short, p_short, m_short = adx([10.0] * 5, [5.0] * 5, [8.0] * 5, period=14)
    assert all(x is None for x in a_short)

    # Keyword resolution (highs, lows, closes)
    a_kw, p_kw, m_kw = adx(highs=flat, lows=flat, closes=flat, period=14)
    assert len(a_kw) == 50


def test_moving_average_slope_and_trend_indicators():
    """Verify ma_slope, trend_strength, and linear_regression_slope."""
    rising = [float(100 + i * 2) for i in range(40)]
    falling = [float(200 - i * 2) for i in range(40)]
    flat = [100.0] * 40

    # MA Slope
    s_up = ma_slope(rising, period=10, lookback=5)
    assert s_up[-1] is not None and s_up[-1] > 0.0
    s_down = ma_slope(falling, period=10, lookback=5)
    assert s_down[-1] is not None and s_down[-1] < 0.0
    s_flat = ma_slope(flat, period=10, lookback=5)
    assert s_flat[-1] is not None and abs(s_flat[-1]) < 1e-9

    # Normalized slope
    s_norm = ma_slope(rising, period=10, lookback=5, normalized=True)
    assert s_norm[-1] is not None and s_norm[-1] > 0.0

    # Trend Strength
    t_up = trend_strength(rising, fast_period=10, slow_period=20)
    assert t_up[-1] is not None and t_up[-1] > 0.0
    t_down = trend_strength(falling, fast_period=10, slow_period=20)
    assert t_down[-1] is not None and t_down[-1] < 0.0

    # Linear Regression Slope: y = 50 + 2.5 * x
    line_series = [50.0 + 2.5 * i for i in range(30)]
    lr_slope = linear_regression_slope(line_series, period=14)
    assert lr_slope[-1] is not None
    assert abs(lr_slope[-1] - 2.5) < 1e-6


# ============================================================================
# 2. Quant Risk Analytics & Regression
# ============================================================================

def test_quant_metrics_dataclass():
    """Verify QuantMetrics dataclass has all 12 attributes and default values."""
    m = QuantMetrics()
    assert hasattr(m, "mean_return")
    assert hasattr(m, "annual_volatility")
    assert hasattr(m, "sharpe_ratio")
    assert hasattr(m, "sortino_ratio")
    assert hasattr(m, "max_drawdown")
    assert hasattr(m, "drawdown_duration")
    assert hasattr(m, "var_95")
    assert hasattr(m, "var_99")
    assert hasattr(m, "cvar_95")
    assert hasattr(m, "beta")
    assert hasattr(m, "alpha")
    assert hasattr(m, "r_squared")
    assert m.sharpe_ratio == 0.0


def test_compute_metrics_standard():
    """Verify compute_metrics calculates risk metrics accurately for normal series."""
    rng = random.Random(7)
    bench = [25000.0]
    for _ in range(119):
        bench.append(bench[-1] * (1.0 + rng.gauss(0.0005, 0.008)))
    prices = [100.0]
    for i in range(1, 120):
        b_ret = (bench[i] - bench[i - 1]) / bench[i - 1]
        p_ret = 1.2 * b_ret + rng.gauss(0.0002, 0.004)
        prices.append(prices[-1] * (1.0 + p_ret))

    m = compute_metrics(prices, benchmark_prices=bench, risk_free_rate=0.05)
    assert m.mean_return > 0.0
    assert m.annual_volatility >= 0.0
    assert math.isfinite(m.sharpe_ratio)
    assert math.isfinite(m.sortino_ratio)
    assert 0.0 <= m.max_drawdown <= 1.0
    assert m.var_95 >= 0.0
    assert m.var_99 >= 0.0
    assert m.cvar_95 >= m.var_95 * 0.95
    assert m.beta > 0.0
    assert 0.0 <= m.r_squared <= 1.0


def test_compute_metrics_flat_prices():
    """Verify flat prices produce zero volatility and finite Sharpe without error."""
    flat = [200.0] * 50
    m = compute_metrics(flat, risk_free_rate=0.05)
    assert m.annual_volatility == 0.0
    assert m.sharpe_ratio == 0.0
    assert m.sortino_ratio == 0.0
    assert m.max_drawdown == 0.0
    assert m.drawdown_duration == 0


def test_compute_metrics_empty_and_short():
    """Verify compute_metrics handles empty and single-element inputs gracefully."""
    m_empty = compute_metrics([])
    assert isinstance(m_empty, QuantMetrics)
    assert m_empty.mean_return == 0.0

    m_single = compute_metrics([150.0])
    assert isinstance(m_single, QuantMetrics)
    assert m_single.annual_volatility == 0.0


def test_compute_metrics_benchmark_regression():
    """Verify beta, alpha, and r_squared calculation against benchmark series."""
    rng = random.Random(42)
    n = 200
    bench = [1000.0]
    for _ in range(n - 1):
        bench.append(bench[-1] * (1.0 + rng.gauss(0.0004, 0.01)))

    # Asset with beta ~ 1.5
    asset = [100.0]
    for i in range(1, n):
        b_ret = (bench[i] - bench[i - 1]) / bench[i - 1]
        a_ret = 1.5 * b_ret + rng.gauss(0.0001, 0.004)
        asset.append(asset[-1] * (1.0 + a_ret))

    m = compute_metrics(asset, benchmark_prices=bench, risk_free_rate=0.05)
    assert 1.0 <= m.beta <= 2.0
    assert 0.0 <= m.r_squared <= 1.0
    assert math.isfinite(m.alpha)

    # Flat benchmark produces zero variance -> beta/alpha/r2 = 0.0
    flat_bench = [25000.0] * n
    m_flat_b = compute_metrics(asset, benchmark_prices=flat_bench)
    assert m_flat_b.beta == 0.0
    assert m_flat_b.alpha == 0.0
    assert m_flat_b.r_squared == 0.0

    # No benchmark
    m_no_b = compute_metrics(asset, benchmark_prices=None)
    assert m_no_b.beta == 0.0
    assert m_no_b.alpha == 0.0
    assert m_no_b.r_squared == 0.0


def test_compute_metrics_severe_drop_and_var_ordering():
    """Verify fat-tail crash series preserves CVaR >= VaR ordering invariant."""
    prices = [100.0 * (0.95 ** i) for i in range(50)]
    m = compute_metrics(prices, risk_free_rate=0.05)
    assert math.isfinite(m.var_95)
    assert math.isfinite(m.var_99)
    assert math.isfinite(m.cvar_95)
    assert abs(m.cvar_95) >= abs(m.var_95) * 0.95


# ============================================================================
# 3. StockAnalyzer Service & Signals
# ============================================================================

def test_stock_analyzer_full_analysis():
    """Verify StockAnalyzer produces a comprehensive report with dual access."""
    analyzer = StockAnalyzer()
    rows = {
        "open": [100.0 + i for i in range(60)],
        "high": [102.0 + i for i in range(60)],
        "low": [99.0 + i for i in range(60)],
        "close": [101.0 + i for i in range(60)],
        "volume": [1000.0] * 60,
    }
    report = analyzer.analyze_stock("RELIANCE", rows)

    # Verify StockAnalysisResult supports both key and attribute access
    assert isinstance(report, StockAnalysisResult)
    assert report.symbol == "RELIANCE"
    assert report["symbol"] == "RELIANCE"

    assert report.current_price == 160.0
    assert report["current_price"] == 160.0

    # Technical indicators
    assert hasattr(report, "rsi")
    assert hasattr(report, "macd_line")
    assert hasattr(report, "stoch_k")
    assert hasattr(report, "adx")
    assert "rsi" in report.indicators

    # Signal & Metrics
    assert report.signal.action in ("STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL")
    assert isinstance(report.metrics, QuantMetrics)
    assert hasattr(report.metrics, "sharpe_ratio")


def test_stock_analyzer_signal_generation_tiers():
    """Verify 5-tier signal generator rules and confidence scoring."""
    analyzer = StockAnalyzer()

    # Oversold RSI (<35) + Bullish crossover
    rsi_oversold = [50.0] * 10 + [25.0]
    macd_bull = ([-2.0, 1.0], [0.0, 0.0], [0.0, 1.0])
    sig_sb = analyzer.generate_signal(rsi_oversold, macd_bull)
    assert sig_sb.action == "STRONG_BUY"
    assert sig_sb.confidence >= 85.0
    assert sig_sb.score == 2.0

    # Overbought RSI (>65) + Bearish crossover
    rsi_overbought = [50.0] * 10 + [75.0]
    macd_bear = ([2.0, -1.0], [0.0, 0.0], [0.0, -1.0])
    sig_ss = analyzer.generate_signal(rsi_overbought, macd_bear)
    assert sig_ss.action == "STRONG_SELL"
    assert sig_ss.confidence >= 85.0
    assert sig_ss.score == -2.0

    # Neutral
    rsi_neutral = [50.0] * 10
    macd_neutral = ([0.0, 0.0], [0.0, 0.0], [0.0, 0.0])
    sig_n = analyzer.generate_signal(rsi_neutral, macd_neutral)
    assert sig_n.action == "NEUTRAL"
    assert sig_n.score == 0.0


def test_stock_analyzer_compare_multi_stock():
    """Verify multi-stock comparison and ranking across various criteria."""
    analyzer = StockAnalyzer()
    symbols = ["RELIANCE", "TCS", "INFY"]

    # Rank by Sharpe
    ranked_sharpe = analyzer.compare(symbols, rank_by="sharpe")
    assert len(ranked_sharpe) == 3
    assert [item["rank"] for item in ranked_sharpe] == [1, 2, 3]
    assert ranked_sharpe[0]["sharpe"] >= ranked_sharpe[1]["sharpe"] >= ranked_sharpe[2]["sharpe"]

    # Rank by Return
    ranked_return = analyzer.compare(symbols, rank_by="return")
    assert len(ranked_return) == 3
    assert ranked_return[0]["mean_return"] >= ranked_return[1]["mean_return"] >= ranked_return[2]["mean_return"]

    # Rank by Volatility (lower volatility ranks higher)
    ranked_vol = analyzer.compare(symbols, rank_by="volatility")
    assert len(ranked_vol) == 3
    assert ranked_vol[0]["volatility"] <= ranked_vol[1]["volatility"] <= ranked_vol[2]["volatility"]


# ============================================================================
# 4. CLI analyze and compare Subcommands
# ============================================================================

def test_cli_parser_analyze_and_compare():
    """Verify build_parser registers analyze and compare subparsers properly."""
    parser = build_parser()

    # Analyze arguments
    args_a = parser.parse_args(["analyze", "RELIANCE", "--period", "6m", "--compare", "TCS,INFY"])
    assert args_a.subcommand == "analyze"
    assert args_a.symbol == "RELIANCE"
    assert args_a.period == "6m"
    assert args_a.compare == "TCS,INFY"

    # Compare arguments
    args_c = parser.parse_args(["compare", "RELIANCE", "TCS", "--rank-by", "sharpe", "--period", "1y"])
    assert args_c.subcommand == "compare"
    assert args_c.symbols == ["RELIANCE", "TCS"]
    assert args_c.rank_by == "sharpe"


def test_cli_analyze_execution(capsys):
    """Verify headless CLI analyze outputs Rich panels, indicators, and metrics."""
    code = main(["analyze", "RELIANCE"])
    assert code == 0
    out = capsys.readouterr().out
    assert "RELIANCE" in out
    assert "Technical Indicators Summary" in out
    assert "Quantitative Risk & Performance Analytics" in out
    assert "Sharpe Ratio" in out


def test_cli_analyze_with_compare(capsys):
    """Verify sktui analyze with --compare appends ranking table."""
    code = main(["analyze", "RELIANCE", "--compare", "TCS,INFY"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Multi-Stock Technical & Quant Ranking" in out
    assert "TCS" in out


def test_cli_compare_execution(capsys):
    """Verify headless CLI compare ranks and outputs comparison table."""
    code = main(["compare", "RELIANCE", "TCS", "INFY", "--rank-by", "sharpe"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Multi-Stock Technical & Quant Ranking" in out
    assert "RELIANCE" in out
    assert "TCS" in out
    assert "INFY" in out


def test_cli_errors(capsys):
    """Verify empty symbols fail cleanly with non-zero exit codes."""
    code_a = main(["analyze", "   "])
    assert code_a != 0

    code_c = main(["compare", ""])
    assert code_c != 0


# ============================================================================
# 5. QuantAnalysisModal UI Lifecycle & Main Screen Routing
# ============================================================================

def test_quant_modal_instantiation():
    """Verify QuantAnalysisModal instantiates cleanly and alias matches."""
    modal = QuantAnalysisModal(item={"tradingSymbol": "RELIANCE", "exchange": "NC"})
    assert modal.symbol == "RELIANCE"
    assert modal.exchange == "NC"
    assert StockAnalysisModal is QuantAnalysisModal

    # Symbol precedence
    modal_sym = QuantAnalysisModal(symbol="TCS")
    assert modal_sym.symbol == "TCS"


def test_quant_modal_interactive_lifecycle():
    """Verify QuantAnalysisModal mounts, populates tables, and dismisses on Escape."""
    class DummyApp(App):
        def compose(self):
            yield Label("Root Screen")

    async def run():
        app = DummyApp()
        async with app.run_test(size=(120, 36)) as pilot:
            modal = QuantAnalysisModal(item={"tradingSymbol": "RELIANCE", "exchange": "NC"})
            app.push_screen(modal)
            await pilot.pause(0.1)

            assert isinstance(app.screen, QuantAnalysisModal)
            assert app.screen.symbol == "RELIANCE"

            # Check DataTable columns were initialized
            dt = app.screen.query_one("#t-quant-metrics")
            assert len(dt.columns) >= 4

            # Check dismissal via escape key
            await pilot.press("escape")
            await pilot.pause(0.1)
            assert not isinstance(app.screen, QuantAnalysisModal)

    asyncio.run(run())


def test_main_screen_action_quant_and_analyze(monkeypatch):
    """Verify MainScreen resolves symbols and routes /quant and /analyze actions."""
    from unittest.mock import MagicMock
    from sktui.screens.main import MainScreen

    mock_app = MagicMock()
    monkeypatch.setattr(MainScreen, "app", property(lambda self: mock_app))

    screen = object.__new__(MainScreen)
    screen.watch = [{"tradingSymbol": "RELIANCE", "exchange": "NC"}, {"tradingSymbol": "TCS", "exchange": "NC"}]
    screen.selected_symbol = None
    screen.status = MagicMock()

    # 1. Resolve explicit symbol in watch
    item, sym = screen._resolve_target_item("TCS")
    assert sym == "TCS"
    assert item["tradingSymbol"] == "TCS"

    # 2. Resolve explicit symbol not in watch
    item_new, sym_new = screen._resolve_target_item("INFY")
    assert sym_new == "INFY"
    assert item_new["tradingSymbol"] == "INFY"

    # 3. Resolve default from watch[0] when symbol is None
    item_def, sym_def = screen._resolve_target_item(None)
    assert sym_def == "RELIANCE"
    assert item_def["tradingSymbol"] == "RELIANCE"

    # 4. Action quant invokes push_screen with QuantAnalysisModal
    screen.action_quant("TCS")
    assert mock_app.push_screen.called
    pushed = mock_app.push_screen.call_args[0][0]
    assert isinstance(pushed, QuantAnalysisModal)
    assert pushed.symbol == "TCS"

    # 5. Action analyze invokes push_screen with QuantAnalysisModal
    mock_app.push_screen.reset_mock()
    screen.action_analyze("INFY")
    assert mock_app.push_screen.called
    pushed_an = mock_app.push_screen.call_args[0][0]
    assert isinstance(pushed_an, QuantAnalysisModal)
    assert pushed_an.symbol == "INFY"

