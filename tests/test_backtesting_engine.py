"""Comprehensive Unit and Integration Test Suite for Milestone 4: Backtesting Engine.

Covers:
- Section 1: Configuration & Dataclass Fidelity
- Section 2: Dual-Mode Simulation Parity & Stepping
- Section 3: Strict Look-Ahead Bias Prevention
- Section 4: Cost & Friction Modeling
- Section 5: Catalog of 8 Standard Strategies
- Section 6: Performance & Risk Metrics Mathematical Rigor
- Section 7: Parameter Grid Search Optimizer
- Section 8: Walk-Forward Rolling-Window Validation
- Section 9: Boundary, Corner & Zero-Division Safety
- Section 10: Headless CLI Subparser & Handlers
- Section 11: TUI BacktestModal Lifecycle & Slash Routing
"""
from __future__ import annotations

import argparse
import io
import math
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sktui.services.backtesting import (
    DEFAULT_PARAM_GRIDS,
    BacktestConfig,
    BacktestResult,
    _extract_ohlcv,
    optimize_grid,
    run_backtest,
    walk_forward_analysis,
)


@pytest.fixture
def sample_ohlcv() -> dict[str, list[float]]:
    """100-bar deterministic synthetic price series with upward trend and oscillating waves."""
    closes: list[float] = []
    base = 100.0
    for i in range(100):
        trend = i * 0.5
        cycle = 10.0 * math.sin(i * 0.25)
        closes.append(round(base + trend + cycle, 2))

    opens = [closes[0]] + [closes[i - 1] for i in range(1, 100)]
    highs = [max(o, c) + 1.5 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 1.5 for o, c in zip(opens, closes)]
    volumes = [5000.0 + (i % 10) * 100.0 for i in range(100)]

    return {
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    }


# ============================================================================
# Section 1: Configuration & Dataclass Fidelity
# ============================================================================

def test_backtest_config_defaults() -> None:
    cfg = BacktestConfig()
    assert cfg.initial_capital == 100000.0
    assert cfg.commission_rate == 0.001
    assert cfg.slippage_rate == 0.0005
    assert cfg.fixed_ticket_fee == 0.0
    assert cfg.strategy_name == "sma"
    assert cfg.parameters == {}
    assert cfg.mode == "vectorized"
    assert cfg.position_size == 1.0
    assert cfg.allow_short is False


def test_backtest_config_validation_rules() -> None:
    with pytest.raises(ValueError, match="initial_capital must be positive"):
        BacktestConfig(initial_capital=-1000.0)

    with pytest.raises(ValueError, match="commission_rate cannot be negative"):
        BacktestConfig(commission_rate=-0.01)

    with pytest.raises(ValueError, match="slippage_rate cannot be negative"):
        BacktestConfig(slippage_rate=-0.01)

    with pytest.raises(ValueError, match="fixed_ticket_fee cannot be negative"):
        BacktestConfig(fixed_ticket_fee=-5.0)


def test_backtest_result_to_dict_and_getitem(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "sma")
    assert res["total_return"] == res.total_return
    assert res.get("sharpe_ratio") == res.sharpe_ratio
    assert res.get("nonexistent_key", "default_val") == "default_val"

    with pytest.raises(KeyError):
        _ = res["nonexistent_key"]

    d = res.to_dict()
    assert isinstance(d, dict)
    assert "total_return" in d
    assert "total_return_pct" in d
    assert "sharpe_ratio" in d
    assert "equity_points" in d
    assert d["strategy_name"] == "sma"


# ============================================================================
# Section 2: Dual-Mode Simulation Parity & Stepping
# ============================================================================

def test_vectorized_simulation_sma(sample_ohlcv: dict[str, list[float]]) -> None:
    cfg = BacktestConfig(
        initial_capital=50000.0,
        strategy_name="sma",
        parameters={"fast_period": 5, "slow_period": 15},
        mode="vectorized",
    )
    res = run_backtest(sample_ohlcv, "sma", cfg, mode="vectorized")
    assert res.initial_capital == 50000.0
    assert len(res.equity_curve) == 100
    assert math.isclose(res.equity_curve[0], 50000.0, rel_tol=1e-5)


def test_event_driven_replay_simulation_sma(sample_ohlcv: dict[str, list[float]]) -> None:
    cfg = BacktestConfig(
        initial_capital=50000.0,
        strategy_name="sma",
        parameters={"fast_period": 5, "slow_period": 15},
        mode="event_driven",
    )
    res = run_backtest(sample_ohlcv, "sma", cfg, mode="event_driven")
    assert res.initial_capital == 50000.0
    assert len(res.equity_curve) == 100
    assert math.isclose(res.equity_curve[0], 50000.0, rel_tol=1e-5)


def test_dual_mode_consistency_and_equivalence(sample_ohlcv: dict[str, list[float]]) -> None:
    cfg_vec = BacktestConfig(strategy_name="sma", parameters={"fast_period": 5, "slow_period": 15}, mode="vectorized")
    cfg_evt = BacktestConfig(strategy_name="sma", parameters={"fast_period": 5, "slow_period": 15}, mode="event_driven")

    res_vec = run_backtest(sample_ohlcv, "sma", cfg_vec)
    res_evt = run_backtest(sample_ohlcv, "sma", cfg_evt)

    assert math.isclose(res_vec.final_equity, res_evt.final_equity, rel_tol=1e-4)
    assert res_vec.total_trades == res_evt.total_trades
    assert len(res_vec.trades_log) == len(res_evt.trades_log)


# ============================================================================
# Section 3: Strict Look-Ahead Bias Prevention
# ============================================================================

def test_point_in_time_guard_exec_bar_greater_than_signal_bar(sample_ohlcv: dict[str, list[float]]) -> None:
    cfg = BacktestConfig(strategy_name="sma", parameters={"fast_period": 4, "slow_period": 10})
    res = run_backtest(sample_ohlcv, "sma", cfg)
    assert len(res.trades_log) > 0

    for tr in res.trades_log:
        assert "signal_bar" in tr
        assert "exec_bar" in tr
        assert tr["exec_bar"] > tr["signal_bar"], (
            f"exec_bar ({tr['exec_bar']}) must be strictly > signal_bar ({tr['signal_bar']})"
        )
        assert tr["exec_bar"] == tr["signal_bar"] + 1


def test_execution_price_matches_next_bar_open(sample_ohlcv: dict[str, list[float]]) -> None:
    cfg = BacktestConfig(
        strategy_name="sma",
        parameters={"fast_period": 4, "slow_period": 10},
        slippage_rate=0.001,
        commission_rate=0.0,
    )
    res = run_backtest(sample_ohlcv, "sma", cfg)

    for tr in res.trades_log:
        exec_bar = tr["exec_bar"]
        open_price = sample_ohlcv["open"][exec_bar]
        if tr["action"] in ("BUY", "COVER"):
            expected_fill = open_price * (1.0 + 0.001)
        else:
            expected_fill = open_price * (1.0 - 0.001)
        assert math.isclose(tr["exec_price"], expected_fill, rel_tol=1e-4)


def test_no_future_data_leakage_in_signal_generation(sample_ohlcv: dict[str, list[float]]) -> None:
    # Adding a huge spike in the future should not affect signals of earlier bars
    cfg = BacktestConfig(strategy_name="sma", parameters={"fast_period": 5, "slow_period": 15})
    res_orig = run_backtest(sample_ohlcv, "sma", cfg)

    tampered_ohlcv = {k: list(v) for k, v in sample_ohlcv.items()}
    tampered_ohlcv["close"][80] = 9999.0  # Future spike at bar 80

    res_tamp = run_backtest(tampered_ohlcv, "sma", cfg)

    # All trades before bar 80 should be identical
    orig_pre_80 = [t for t in res_orig.trades_log if t["exec_bar"] < 80]
    tamp_pre_80 = [t for t in res_tamp.trades_log if t["exec_bar"] < 80]
    assert len(orig_pre_80) == len(tamp_pre_80)
    for t1, t2 in zip(orig_pre_80, tamp_pre_80):
        assert t1["signal_bar"] == t2["signal_bar"]
        assert t1["exec_bar"] == t2["exec_bar"]
        assert math.isclose(t1["exec_price"], t2["exec_price"], rel_tol=1e-5)


# ============================================================================
# Section 4: Cost & Friction Modeling
# ============================================================================

def test_gross_vs_net_return_friction_hierarchy(sample_ohlcv: dict[str, list[float]]) -> None:
    cfg_gross = BacktestConfig(commission_rate=0.0, slippage_rate=0.0, strategy_name="sma", parameters={"fast_period": 4, "slow_period": 10})
    cfg_net = BacktestConfig(commission_rate=0.002, slippage_rate=0.001, strategy_name="sma", parameters={"fast_period": 4, "slow_period": 10})

    res_gross = run_backtest(sample_ohlcv, "sma", cfg_gross)
    res_net = run_backtest(sample_ohlcv, "sma", cfg_net)

    if res_gross.total_trades > 0:
        assert res_net.total_return <= res_gross.total_return
        assert res_net.final_equity <= res_gross.final_equity


def test_percentage_commission_and_slippage_degradation(sample_ohlcv: dict[str, list[float]]) -> None:
    cfg_low_fric = BacktestConfig(commission_rate=0.0005, slippage_rate=0.0002, strategy_name="sma", parameters={"fast_period": 4, "slow_period": 10})
    cfg_high_fric = BacktestConfig(commission_rate=0.005, slippage_rate=0.003, strategy_name="sma", parameters={"fast_period": 4, "slow_period": 10})

    res_low = run_backtest(sample_ohlcv, "sma", cfg_low_fric)
    res_high = run_backtest(sample_ohlcv, "sma", cfg_high_fric)

    if res_low.total_trades > 0:
        assert res_high.total_return <= res_low.total_return


def test_fixed_ticket_fee_cumulative_deduction(sample_ohlcv: dict[str, list[float]]) -> None:
    cfg_no_fee = BacktestConfig(fixed_ticket_fee=0.0, strategy_name="sma", parameters={"fast_period": 4, "slow_period": 10})
    cfg_fee = BacktestConfig(fixed_ticket_fee=50.0, strategy_name="sma", parameters={"fast_period": 4, "slow_period": 10})

    res_no_fee = run_backtest(sample_ohlcv, "sma", cfg_no_fee)
    res_fee = run_backtest(sample_ohlcv, "sma", cfg_fee)

    if res_no_fee.total_trades > 0:
        assert res_fee.final_equity <= res_no_fee.final_equity


# ============================================================================
# Section 5: Catalog of 8 Standard Strategies
# ============================================================================

def test_strategy_sma_dual_crossover(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "sma", BacktestConfig(parameters={"fast_period": 5, "slow_period": 15}))
    assert res is not None
    assert hasattr(res, "total_return")


def test_strategy_ema_dual_crossover(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "ema", BacktestConfig(parameters={"fast_period": 6, "slow_period": 18}))
    assert res is not None
    assert hasattr(res, "total_return")


def test_strategy_rsi_mean_reversion(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "rsi", BacktestConfig(parameters={"period": 10, "oversold": 35.0, "overbought": 65.0}))
    assert res is not None
    assert hasattr(res, "total_return")


def test_strategy_macd_signal_crossover(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "macd", BacktestConfig(parameters={"fast": 8, "slow": 18, "signal": 6}))
    assert res is not None
    assert hasattr(res, "total_return")


def test_strategy_bollinger_bands(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "bollinger", BacktestConfig(parameters={"period": 15, "std_dev": 1.5}))
    assert res is not None
    assert hasattr(res, "total_return")


def test_strategy_donchian_breakout(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "breakout", BacktestConfig(parameters={"lookback": 12}))
    assert res is not None
    assert hasattr(res, "total_return")


def test_strategy_zscore_mean_reversion(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "mean_reversion", BacktestConfig(parameters={"window": 15, "entry_z": 1.5, "exit_z": 0.3}))
    assert res is not None
    assert hasattr(res, "total_return")


def test_strategy_momentum_roc(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "momentum", BacktestConfig(parameters={"roc_period": 8, "threshold": 0.5}))
    assert res is not None
    assert hasattr(res, "total_return")


def test_all_strategies_default_empty_parameters(sample_ohlcv: dict[str, list[float]]) -> None:
    strategies = ["sma", "ema", "rsi", "macd", "bollinger", "breakout", "mean_reversion", "momentum"]
    for st in strategies:
        cfg = BacktestConfig(strategy_name=st, parameters={})
        res = run_backtest(sample_ohlcv, st, cfg)
        assert res is not None, f"Strategy {st} failed with empty parameters"
        assert len(res.equity_curve) == len(sample_ohlcv["close"])


# ============================================================================
# Section 6: Performance & Risk Metrics Mathematical Rigor
# ============================================================================

def test_metrics_total_return_and_cagr(sample_ohlcv: dict[str, list[float]]) -> None:
    cfg = BacktestConfig(initial_capital=100000.0, strategy_name="sma")
    res = run_backtest(sample_ohlcv, "sma", cfg)
    expected_ret = (res.final_equity - 100000.0) / 100000.0
    assert math.isclose(res.total_return, expected_ret, rel_tol=1e-5)
    assert math.isfinite(res.cagr)


def test_metrics_annualized_volatility(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "sma")
    assert res.annualized_volatility >= 0.0
    assert math.isfinite(res.annualized_volatility)


def test_metrics_sharpe_and_sortino_ratios(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "sma")
    assert math.isfinite(res.sharpe_ratio)
    assert math.isfinite(res.sortino_ratio)


def test_metrics_calmar_ratio(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "sma")
    assert math.isfinite(res.calmar_ratio)


def test_metrics_maximum_drawdown_calculation(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "sma")
    assert 0.0 <= res.max_drawdown <= 1.0


def test_metrics_win_rate_and_profit_factor(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "sma")
    assert 0.0 <= res.win_rate <= 1.0
    assert res.profit_factor >= 0.0


# ============================================================================
# Section 7: Parameter Grid Search Optimizer
# ============================================================================

def test_optimize_grid_cartesian_product(sample_ohlcv: dict[str, list[float]]) -> None:
    param_grid = {"fast_period": [3, 5], "slow_period": [10, 15]}
    results = optimize_grid(sample_ohlcv, "sma", param_grid, metric="sharpe_ratio")
    assert len(results) == 4
    for params, res in results:
        assert "fast_period" in params and "slow_period" in params
        assert isinstance(res, BacktestResult)


def test_optimize_grid_sorting_by_sharpe_ratio(sample_ohlcv: dict[str, list[float]]) -> None:
    param_grid = {"fast_period": [3, 5], "slow_period": [10, 15]}
    results = optimize_grid(sample_ohlcv, "sma", param_grid, metric="sharpe_ratio")
    sharpes = [r.sharpe_ratio for _, r in results]
    assert sharpes == sorted(sharpes, reverse=True)


def test_optimize_grid_empty_or_single_parameter(sample_ohlcv: dict[str, list[float]]) -> None:
    results = optimize_grid(sample_ohlcv, "sma", {})
    assert len(results) == 1


# ============================================================================
# Section 8: Walk-Forward Rolling-Window Validation
# ============================================================================

def test_walk_forward_window_segmentation(sample_ohlcv: dict[str, list[float]]) -> None:
    param_grid = {"fast_period": [3, 5], "slow_period": [10, 15]}
    wf_results = walk_forward_analysis(sample_ohlcv, "sma", param_grid, n_windows=4, train_ratio=0.7)
    assert len(wf_results) == 4

    for rec in wf_results:
        assert rec["train_range"][1] == rec["test_range"][0]  # Zero look-ahead leakage
        assert rec["test_range"][1] > rec["test_range"][0]
        assert "best_parameters" in rec
        assert "out_sample_sharpe" in rec


def test_walk_forward_in_sample_vs_out_of_sample_metrics(sample_ohlcv: dict[str, list[float]]) -> None:
    param_grid = {"fast_period": [3, 5], "slow_period": [10, 15]}
    wf_results = walk_forward_analysis(sample_ohlcv, "sma", param_grid, n_windows=3, train_ratio=0.6)
    for rec in wf_results:
        assert isinstance(rec["in_sample_result"], BacktestResult)
        assert isinstance(rec["out_sample_result"], BacktestResult)


# ============================================================================
# Section 9: Boundary, Corner & Zero-Division Safety
# ============================================================================

def test_zero_trades_inactive_strategy_zero_division(sample_ohlcv: dict[str, list[float]]) -> None:
    cfg = BacktestConfig(
        initial_capital=75000.0,
        strategy_name="rsi",
        parameters={"oversold": -9999.0, "overbought": 9999.0},
    )
    res = run_backtest(sample_ohlcv, "rsi", cfg)
    assert res.total_trades == 0
    assert res.win_rate == 0.0
    assert res.profit_factor == 0.0
    assert math.isclose(res.final_equity, 75000.0, rel_tol=1e-5)
    assert res.max_drawdown == 0.0


def test_catastrophic_crash_prices_drawdown_limit() -> None:
    crash_prices = [1000.0 * (0.1 ** i) for i in range(8)]
    crash_data = {
        "open": crash_prices,
        "high": crash_prices,
        "low": [p * 0.95 for p in crash_prices],
        "close": crash_prices,
        "volume": [1000] * 8,
    }
    cfg = BacktestConfig(initial_capital=5000.0, strategy_name="momentum")
    res = run_backtest(crash_data, "momentum", cfg)
    assert res is not None
    assert res.max_drawdown <= 1.0
    for eq in res.equity_curve:
        assert eq >= 0.0


def test_tiny_ohlcv_series_lookback_warmup() -> None:
    tiny = {
        "open": [100.0],
        "high": [101.0],
        "low": [99.0],
        "close": [100.5],
        "volume": [500.0],
    }
    res = run_backtest(tiny, "sma")
    assert res.total_trades == 0
    assert math.isclose(res.final_equity, 100000.0, rel_tol=1e-5)


def test_negative_capital_validation_rejection(sample_ohlcv: dict[str, list[float]]) -> None:
    with pytest.raises(ValueError):
        _ = BacktestConfig(initial_capital=-50000.0)


def test_equity_curve_all_points_finite(sample_ohlcv: dict[str, list[float]]) -> None:
    res = run_backtest(sample_ohlcv, "sma")
    for eq in res.equity_curve:
        assert eq is not None
        assert math.isfinite(eq)


# ============================================================================
# Section 10: Headless CLI Subparser & Handlers
# ============================================================================

def test_cli_backtest_argument_parsing() -> None:
    from sktui.app import build_parser
    parser = build_parser()
    args = parser.parse_args(["backtest", "--strategy", "rsi", "--symbol", "TCS", "--capital", "250000", "--optimize"])
    assert args.command == "backtest"
    assert args.strategy == "rsi"
    assert args.symbol == "TCS"
    assert args.capital == 250000.0
    assert args.optimize is True


def test_cli_backtest_headless_execution_rich_table(capsys: pytest.CaptureFixture) -> None:
    from sktui.app import handle_backtest
    args = argparse.Namespace(
        strategy="sma",
        symbol="RELIANCE",
        capital=100000.0,
        period="1y",
        commission=0.0003,
        slippage=0.0002,
        mode="vectorized",
        optimize=False,
        walk_forward=False,
        output=None,
        json=False,
    )
    code = handle_backtest(args)
    assert code == 0
    out, err = capsys.readouterr()
    assert "RELIANCE" in out
    assert "Performance & Risk Ratios" in out


def test_cli_backtest_headless_execution_json_stdout(capsys: pytest.CaptureFixture) -> None:
    import json
    from sktui.app import handle_backtest
    args = argparse.Namespace(
        strategy="rsi",
        symbol="INFY",
        capital=100000.0,
        period="1y",
        commission=0.0003,
        slippage=0.0002,
        mode="vectorized",
        optimize=False,
        walk_forward=False,
        output=None,
        json=True,
    )
    code = handle_backtest(args)
    assert code == 0
    out, _ = capsys.readouterr()
    parsed = json.loads(out)
    assert "total_return" in parsed
    assert "equity_points" in parsed


def test_cli_backtest_grid_optimization_flag(capsys: pytest.CaptureFixture) -> None:
    from sktui.app import handle_backtest
    args = argparse.Namespace(
        strategy="sma",
        symbol="TCS",
        capital=100000.0,
        period="1y",
        commission=0.0003,
        slippage=0.0002,
        mode="vectorized",
        optimize=True,
        walk_forward=False,
        output=None,
        json=False,
    )
    code = handle_backtest(args)
    assert code == 0
    out, _ = capsys.readouterr()
    assert "Grid Search Optimization" in out


def test_cli_backtest_invalid_inputs_exit_code_1() -> None:
    from sktui.app import handle_backtest
    # Missing strategy
    args1 = argparse.Namespace(strategy="", symbol="TCS", capital=100000.0)
    assert handle_backtest(args1) == 1

    # Missing symbol
    args2 = argparse.Namespace(strategy="sma", symbol="", capital=100000.0)
    assert handle_backtest(args2) == 1

    # Negative capital
    args3 = argparse.Namespace(strategy="sma", symbol="TCS", capital=-500.0)
    assert handle_backtest(args3) == 1


# ============================================================================
# Section 11: TUI BacktestModal Lifecycle & Slash Routing
# ============================================================================

def test_backtest_modal_composition_and_widgets() -> None:
    from sktui.screens.modals import BacktestModal
    modal = BacktestModal(strategy="sma", symbol="RELIANCE", capital=100000.0)
    assert modal.strategy_name == "sma"
    assert modal.symbol == "RELIANCE"
    assert modal.capital == 100000.0


def test_backtest_modal_simulation_mount() -> None:
    from sktui.screens.modals import BacktestModal
    modal = BacktestModal(strategy="sma", symbol="RELIANCE", capital=100000.0)
    modal.action_run_simulation()
    assert modal.result is not None
    assert isinstance(modal.result, BacktestResult)
    assert len(modal.result.equity_curve) > 0


def test_mainscreen_slash_backtest_dispatch() -> None:
    from sktui.screens.main import MainScreen
    screen = MainScreen.__new__(MainScreen)
    mock_app = MagicMock()
    with patch.object(MainScreen, "app", new_callable=lambda: mock_app):
        screen.status = MagicMock()
        screen.current_symbol = "RELIANCE"

        screen.action_backtest(strategy="rsi")
        mock_app.push_screen.assert_called_once()
        screen.status.assert_called_once()
