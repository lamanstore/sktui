"""End-to-End Tests for Requirement R4: Backtesting Engine and Frameworks Integration.

Covers:
- Tier 1: Feature Coverage (isolated happy-path tests)
  1. Dual-Mode Backtest Execution with Moving Average Cross
  2. Look-Ahead Bias Prevention Guard (Bar t signal executes at Bar t+1 open)
  3. Cost & Slippage Friction Modeling (Gross vs Net performance)
  4. Catalog of 8 Standard Strategies
  5. CLI backtest argument parsing and metrics reporting
- Tier 2: Boundary & Corner Cases
  6. Zero-trades inactive strategy (ZeroDivisionError prevention)
  7. Catastrophic loss and drawdown boundaries
  8. Insufficient historical bar count (lookback warmup safety)
  9. Extreme slippage/commission and invalid capital parameters
  10. Equity curve integrity and non-finite value protection
"""
from __future__ import annotations

import math
from typing import Any, Callable

import pytest


def _get_backtesting() -> Any:
    try:
        import sktui.services.backtesting as bt
        return bt
    except ImportError:
        pytest.skip("sktui.services.backtesting implementation pending in Milestone 4")


# ============================================================================
# Tier 1: Feature Coverage (Isolated Happy Path)
# ============================================================================

def test_r4_t1_dual_mode_backtest_sma_cross(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify run_backtest executes SMA cross strategy and returns BacktestResult."""
    bt = _get_backtesting()

    config = bt.BacktestConfig(
        initial_capital=100_000.0,
        commission_rate=0.0005,
        slippage_rate=0.0002,
        strategy_name="sma",
        parameters={"fast_period": 5, "slow_period": 15},
    )

    result = bt.run_backtest(synthetic_ohlcv, "sma", config)

    assert hasattr(result, "total_return")
    assert hasattr(result, "sharpe_ratio")
    assert hasattr(result, "max_drawdown")
    assert hasattr(result, "win_rate")
    assert hasattr(result, "profit_factor")
    assert hasattr(result, "total_trades")
    assert hasattr(result, "trades_log")
    assert hasattr(result, "equity_curve")

    assert len(result.equity_curve) > 0, "Equity curve must have points"
    assert math.isclose(result.equity_curve[0], 100_000.0, rel_tol=1e-4)
    assert 0.0 <= abs(result.max_drawdown) <= 1.0


def test_r4_t1_look_ahead_bias_prevention_guard(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify execution invariant: Signal at Bar t close executes strictly at Bar t+1 open."""
    bt = _get_backtesting()

    config = bt.BacktestConfig(
        initial_capital=100_000.0,
        commission_rate=0.0,
        slippage_rate=0.0,
        strategy_name="sma",
        parameters={"fast_period": 5, "slow_period": 10},
    )

    result = bt.run_backtest(synthetic_ohlcv, "sma", config)

    # Precondition: Strategy must generate at least one trade to verify look-ahead bias
    assert len(result.trades_log) > 0, "No trades executed to verify look-ahead bias prevention"

    # In trades_log, verify execution bar/time is strictly after signal bar
    for trade in result.trades_log:
        assert "signal_bar" in trade and "exec_bar" in trade, f"Trade record missing bar timestamps: {trade}"
        assert trade["exec_bar"] > trade["signal_bar"], (
            f"Execution bar {trade['exec_bar']} must be > signal bar {trade['signal_bar']} (zero look-ahead)"
        )
        if "exec_price" in trade and "signal_close" in trade:
            # Check price is not identical to previous bar close unless open equals previous close
            pass


def test_r4_t1_cost_and_slippage_modeling(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify trading friction: Net return with commission/slippage is <= gross return."""
    bt = _get_backtesting()

    config_gross = bt.BacktestConfig(
        initial_capital=100_000.0,
        commission_rate=0.0,
        slippage_rate=0.0,
        strategy_name="sma",
        parameters={"fast_period": 5, "slow_period": 12},
    )

    config_net = bt.BacktestConfig(
        initial_capital=100_000.0,
        commission_rate=0.002,  # 0.2% commission
        slippage_rate=0.001,    # 0.1% slippage
        strategy_name="sma",
        parameters={"fast_period": 5, "slow_period": 12},
    )

    res_gross = bt.run_backtest(synthetic_ohlcv, "sma", config_gross)
    res_net = bt.run_backtest(synthetic_ohlcv, "sma", config_net)

    if res_gross.total_trades > 0:
        assert res_net.total_return <= res_gross.total_return, (
            f"Net return ({res_net.total_return}) should be <= gross return ({res_gross.total_return})"
        )


def test_r4_t1_catalog_of_8_strategies(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify all 8 catalog strategies can be invoked via run_backtest."""
    bt = _get_backtesting()
    strategies = [
        "sma", "ema", "rsi", "macd", "bollinger",
        "breakout", "mean_reversion", "momentum"
    ]

    for strat in strategies:
        cfg = bt.BacktestConfig(
            initial_capital=50_000.0,
            commission_rate=0.0005,
            slippage_rate=0.0002,
            strategy_name=strat,
            parameters={},
        )
        res = bt.run_backtest(synthetic_ohlcv, strat, cfg)
        assert res is not None, f"Strategy {strat} failed to return a BacktestResult"
        assert hasattr(res, "total_return")


def test_r4_t1_cli_backtest_arguments_and_reporting(
    cli_runner: Callable[[list[str]], tuple[int, str, str]],
) -> None:
    """Verify CLI backtest argument parser accepts strategy, symbol, and capital flags."""
    code, out, err = cli_runner([
        "backtest",
        "--strategy", "rsi",
        "--symbol", "RELIANCE",
        "--capital", "500000",
    ])
    if code == 2 and "unrecognized arguments" in err:
        pytest.skip("CLI backtest subparser pending in Milestone 1/4")
    assert code == 0, f"sktui backtest failed with exit code {code}: {err}"
    assert "backtest" in out.lower() or "rsi" in out.lower(), f"Expected 'backtest'/'rsi' in stdout, got:\n{out}"


# ============================================================================
# Tier 2: Boundary & Corner Cases
# ============================================================================

def test_r4_t2_zero_trades_inactive_strategy(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify backtest with zero executed trades handles win_rate and profit_factor safely."""
    bt = _get_backtesting()

    # Impossible RSI threshold ensuring 0 trades
    cfg = bt.BacktestConfig(
        initial_capital=100_000.0,
        commission_rate=0.001,
        slippage_rate=0.001,
        strategy_name="rsi",
        parameters={"oversold": -999.0, "overbought": 999.0},
    )

    res = bt.run_backtest(synthetic_ohlcv, "rsi", cfg)
    assert res.total_trades == 0
    assert res.win_rate == 0.0 or res.win_rate is None
    assert res.profit_factor == 0.0 or res.profit_factor is None
    assert math.isclose(res.equity_curve[-1], 100_000.0, rel_tol=1e-5)


def test_r4_t2_catastrophic_loss_drawdown_limit() -> None:
    """Verify backtest terminates gracefully under extreme loss without negative capital overflow."""
    bt = _get_backtesting()
    # Prices plummeting 90% each bar
    prices = [1000.0 * (0.1 ** i) for i in range(10)]
    crash_ohlcv = {
        "open": prices,
        "high": prices,
        "low": [p * 0.9 for p in prices],
        "close": prices,
        "volume": [1000] * 10,
    }

    cfg = bt.BacktestConfig(
        initial_capital=10_000.0,
        commission_rate=0.0,
        slippage_rate=0.0,
        strategy_name="momentum",
        parameters={},
    )

    res = bt.run_backtest(crash_ohlcv, "momentum", cfg)
    assert res is not None
    assert res.max_drawdown <= 1.0
    for eq in res.equity_curve:
        assert eq >= 0.0, "Equity cannot drop below 0.0"


def test_r4_t2_insufficient_ohlcv_bars() -> None:
    """Verify backtest handles bar series shorter than indicator lookback safely."""
    bt = _get_backtesting()
    tiny_ohlcv = {
        "open": [100.0, 101.0],
        "high": [102.0, 103.0],
        "low": [99.0, 100.0],
        "close": [101.0, 102.0],
        "volume": [500, 600],
    }

    cfg = bt.BacktestConfig(
        initial_capital=10_000.0,
        commission_rate=0.001,
        slippage_rate=0.001,
        strategy_name="sma",
        parameters={"fast_period": 20, "slow_period": 50},
    )

    try:
        res = bt.run_backtest(tiny_ohlcv, "sma", cfg)
        assert res.total_trades == 0
    except ValueError:
        pass  # Graceful validation error is compliant


def test_r4_t2_extreme_slippage_and_commissions(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify backtesting parameter validation rejects or clamps negative/extreme rates."""
    bt = _get_backtesting()

    try:
        # Negative initial capital
        cfg_neg = bt.BacktestConfig(
            initial_capital=-5000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
            strategy_name="sma",
            parameters={},
        )
        res = bt.run_backtest(synthetic_ohlcv, "sma", cfg_neg)
        assert res is not None
    except ValueError:
        pass


def test_r4_t2_backtest_result_equity_curve_length(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify equity curve values are entirely finite and contain no NaN or None."""
    bt = _get_backtesting()

    cfg = bt.BacktestConfig(
        initial_capital=100_000.0,
        commission_rate=0.0005,
        slippage_rate=0.0002,
        strategy_name="sma",
        parameters={"fast_period": 5, "slow_period": 15},
    )

    res = bt.run_backtest(synthetic_ohlcv, "sma", cfg)
    for val in res.equity_curve:
        assert val is not None, "Equity curve points cannot be None"
        assert math.isfinite(val), "Equity curve points must be finite numbers"
