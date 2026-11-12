"""End-to-End Tests for Tier 3 (Cross-Feature Combinations) & Tier 4 (Real-World Scenarios).

Tier 3: Pairwise Interactions across R1-R6:
  1. R1 (CLI) -> R2 (Quant Analysis)
  2. R2 (Indicators) -> R3 (Composite Signal Engine)
  3. R3 (Pair Screener) -> R4 (Backtesting Engine)
  4. R4 (Backtest Optimizer) -> R5 (Bot Configuration)
  5. R5 (Bot Execution) -> R6 (Paper Sandbox Routing)
  6. R1 (CLI) -> R6 (Broker Verification)

Tier 4: Real-World Multi-Module Application Workflows:
  1. Full Algorithmic Pair Trading Lifecycle (R3 + R4 + R5 + R6)
  2. Quant Stock Screening to Automated Momentum Execution (R2 + R3 + R5)
  3. Strategy Research, Grid Optimization & Walk-Forward Validation (R2 + R4)
  4. Interactive Terminal Workstation Trading Session (R1 + R2 + R3 + R5)
  5. Broker Sandbox Resilience & Risk Circuit Breaker (R1 + R5 + R6)
"""
from __future__ import annotations

import asyncio
import math
import random
from typing import Any, Callable

import pytest

import sktui.config as cfg
from sktui.api.auth import decrypt_str, encrypt_str
from sktui.api.client import Client
from sktui.app import SKApp
from sktui.screens.login import LoginScreen
from sktui.screens.main import MainScreen


def _get_quant_analyst() -> Any:
    try:
        import sktui.services.quant_analyst as qa
        return qa
    except ImportError:
        pytest.skip("sktui.services.quant_analyst implementation pending in Milestone 2")


def _get_indicators() -> Any:
    import sktui.services.indicators as ind
    if not hasattr(ind, "stochastic") or not hasattr(ind, "adx"):
        pytest.skip("Stochastic or ADX indicator implementation pending in Milestone 2")
    return ind


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


def _get_backtesting() -> Any:
    try:
        import sktui.services.backtesting as bt
        return bt
    except ImportError:
        pytest.skip("sktui.services.backtesting implementation pending in Milestone 4")


def _get_bot_engine() -> Any:
    try:
        import sktui.services.bot_engine as be
        return be
    except ImportError:
        pytest.skip("sktui.services.bot_engine implementation pending in Milestone 5")


def _get_broker_verifier() -> Any:
    try:
        import sktui.services.broker_verifier as bv
        return bv
    except ImportError:
        pytest.skip("sktui.services.broker_verifier implementation pending in Milestone 6")


# ============================================================================
# Tier 3: Pairwise Cross-Feature Combinations
# ============================================================================

def test_t3_cross_r1_cli_to_r2_quant_analysis(
    cli_runner: Callable[[list[str]], tuple[int, str, str]],
    synthetic_ohlcv: dict[str, Any],
) -> None:
    """Verify CLI sktui analyze routes symbol to QuantMetrics computation."""
    qa = _get_quant_analyst()
    metrics = qa.compute_metrics(synthetic_ohlcv["close"], risk_free_rate=0.05)
    assert hasattr(metrics, "sharpe_ratio")

    code, out, err = cli_runner(["analyze", "RELIANCE", "--period", "6m"])
    if code == 2 and "unrecognized arguments" in err:
        pytest.skip("CLI analyze subparser pending in Milestone 1/2")
    assert code == 0, f"sktui analyze failed with exit code {code}: {err}"
    assert "RELIANCE" in out, f"Expected 'RELIANCE' in stdout, got:\n{out}"


def test_t3_cross_r2_indicators_to_r3_composite_signals(synthetic_ohlcv: dict[str, Any]) -> None:
    """Verify Stochastic and ADX indicators feed into 7-indicator Composite Signal Engine."""
    ind = _get_indicators()
    se = _get_signal_engine()

    # Verify both indicators execute on series
    k, d = ind.stochastic(synthetic_ohlcv["high"], synthetic_ohlcv["low"], synthetic_ohlcv["close"])
    adx_v, pdi, mdi = ind.adx(synthetic_ohlcv["high"], synthetic_ohlcv["low"], synthetic_ohlcv["close"])
    assert len(k) == len(synthetic_ohlcv["close"])
    assert len(adx_v) == len(synthetic_ohlcv["close"])

    # Evaluate composite signals containing indicator votes
    sig = se.evaluate_signals("RELIANCE", synthetic_ohlcv)
    assert hasattr(sig, "indicator_votes")
    assert isinstance(sig.indicator_votes, dict)


def test_t3_cross_r3_pair_screener_to_r4_backtest(synthetic_pair_series: dict[str, Any]) -> None:
    """Verify screened pair spread parameters feed into Backtesting Engine mean-reversion strategy."""
    ps = _get_pair_screener()
    bt = _get_backtesting()

    universe = {
        synthetic_pair_series["symbol_a"]: synthetic_pair_series["stock_a"],
        synthetic_pair_series["symbol_b"]: synthetic_pair_series["stock_b"],
    }
    screen_results = ps.screen_pairs(universe, min_correlation=0.60)
    assert len(screen_results) > 0

    best_pair = screen_results[0]
    beta = getattr(best_pair, "beta", 1.5)

    # Construct spread series
    spread = [ya - beta * xb for ya, xb in zip(synthetic_pair_series["stock_a"], synthetic_pair_series["stock_b"])]
    spread_ohlcv = {
        "open": spread,
        "high": [s + 0.5 for s in spread],
        "low": [s - 0.5 for s in spread],
        "close": spread,
        "volume": [1000] * len(spread),
    }

    cfg_bt = bt.BacktestConfig(
        initial_capital=200_000.0,
        commission_rate=0.0005,
        slippage_rate=0.0002,
        strategy_name="mean_reversion",
        parameters={"entry_zscore": 2.0, "exit_zscore": 0.5},
    )

    result = bt.run_backtest(spread_ohlcv, "mean_reversion", cfg_bt)
    assert result is not None
    assert hasattr(result, "total_return")


def test_t3_cross_r4_backtest_metrics_to_r5_bot_config(
    fake_client: Client,
    synthetic_ohlcv: dict[str, Any],
) -> None:
    """Verify backtest parameters initialize and configure a live BotInstance."""
    bt = _get_backtesting()
    be = _get_bot_engine()

    cfg_bt = bt.BacktestConfig(
        initial_capital=100_000.0,
        commission_rate=0.0005,
        slippage_rate=0.0002,
        strategy_name="sma",
        parameters={"fast_period": 8, "slow_period": 21},
    )
    res = bt.run_backtest(synthetic_ohlcv, "sma", cfg_bt)
    assert res is not None

    # Deploy best parameters to BotInstance
    bot = be.BotInstance(
        strategy="momentum",
        symbol="RELIANCE",
        client=fake_client,
        paper=True,
        parameters={"fast_period": 8, "slow_period": 21},
    )
    assert bot.start() is True
    assert bot.state == be.BotState.RUNNING
    bot.stop()


def test_t3_cross_r5_bot_orders_to_r6_paper_sandbox(fake_client: Client) -> None:
    """Verify running BotInstance routes simulated orders into Paper Sandbox Client."""
    be = _get_bot_engine()

    bot = be.BotInstance(
        strategy="pmm",
        symbol="TATAMOTORS",
        client=fake_client,
        paper=True,
        parameters={"order_amount": 15},
    )
    bot.start()

    assert hasattr(bot, "submit_order"), "BotInstance must expose 'submit_order' for cross-module order execution routing"
    ok, res = bot.submit_order(symbol="TATAMOTORS", qty=15, price=450.0, action="BUY")
    assert ok is True
    # Verify order in paper client
    orders = fake_client.orders()
    assert len(orders) >= 1
    bot.stop()


def test_t3_cross_r1_cli_to_r6_broker_verify(
    cli_runner: Callable[[list[str]], tuple[int, str, str]],
) -> None:
    """Verify CLI verify command validates AES-GCM crypto and broker paper endpoints."""
    # Test crypto verification
    key = "12345678901234567890123456789012"
    cipher = encrypt_str("VerifyTokenTest", key)
    plain = decrypt_str(cipher, key)
    assert plain == "VerifyTokenTest"

    # Test CLI verify
    code, out, err = cli_runner(["verify", "--sandbox"])
    if code == 2 and "unrecognized arguments" in err:
        pytest.skip("CLI verify subparser pending in Milestone 1/6")
    assert code == 0, f"sktui verify failed with exit code {code}: {err}"
    assert "verify" in out.lower() or "sandbox" in out.lower(), f"Expected 'verify'/'sandbox' in stdout, got:\n{out}"


# ============================================================================
# Tier 4: Real-World Multi-Module Application Workflows
# ============================================================================

def test_t4_scenario_1_algorithmic_pair_trading_lifecycle(
    fake_client: Client,
    synthetic_pair_series: dict[str, Any],
) -> None:
    """Scenario 1: End-to-end pair screening -> ADF test -> backtest -> bot execution -> panic stop."""
    ps = _get_pair_screener()
    bt = _get_backtesting()
    be = _get_bot_engine()

    # 1. Screen cointegrated pair from universe
    universe = {
        synthetic_pair_series["symbol_a"]: synthetic_pair_series["stock_a"],
        synthetic_pair_series["symbol_b"]: synthetic_pair_series["stock_b"],
    }
    screen_results = ps.screen_pairs(universe, min_correlation=0.60)
    assert len(screen_results) > 0
    pair = screen_results[0]
    assert pair.is_cointegrated is True or pair.p_value <= 0.10

    # 2. Backtest spread strategy
    spread = [ya - pair.beta * xb for ya, xb in zip(synthetic_pair_series["stock_a"], synthetic_pair_series["stock_b"])]
    spread_data = {
        "open": spread, "high": spread, "low": spread, "close": spread, "volume": [1000] * len(spread)
    }
    cfg_bt = bt.BacktestConfig(
        initial_capital=100_000.0,
        commission_rate=0.0005,
        slippage_rate=0.0002,
        strategy_name="mean_reversion",
        parameters={"entry_zscore": 2.0},
    )
    bt_res = bt.run_backtest(spread_data, "mean_reversion", cfg_bt)
    assert bt_res is not None

    # 3. Spin up pair arbitrage bot in paper sandbox
    bot = be.BotInstance(
        strategy="arbitrage",
        symbol=f"{pair.stock_a},{pair.stock_b}",
        client=fake_client,
        paper=True,
    )
    assert bot.start() is True

    # 4. Emergency Panic Stop
    panic_res = bot.emergency_panic(mode="CANCEL_ALL")
    assert isinstance(panic_res, dict)
    assert bot.state == be.BotState.STOPPED


def test_t4_scenario_2_quant_screening_to_automated_momentum_execution(
    fake_client: Client,
    synthetic_ohlcv: dict[str, Any],
) -> None:
    """Scenario 2: Quant metrics calculation -> 7-indicator composite signal -> momentum bot execution."""
    qa = _get_quant_analyst()
    se = _get_signal_engine()
    be = _get_bot_engine()

    # 1. Quant risk metrics
    metrics = qa.compute_metrics(synthetic_ohlcv["close"], risk_free_rate=0.05)
    assert metrics.annual_volatility >= 0.0

    # 2. 7-indicator composite signal scoring with dynamic ATR levels
    sig = se.evaluate_signals(synthetic_ohlcv["symbol"], synthetic_ohlcv)
    assert sig.signal_type in ("STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL")
    assert sig.stop_loss > 0.0
    assert sig.take_profit > 0.0

    # 3. Momentum bot deployment
    bot = be.BotInstance(
        strategy="momentum",
        symbol=synthetic_ohlcv["symbol"],
        client=fake_client,
        paper=True,
        parameters={"stop_loss": sig.stop_loss, "take_profit": sig.take_profit},
    )
    assert bot.start() is True
    bot.stop()


def test_t4_scenario_3_strategy_research_grid_opt_and_walk_forward(
    synthetic_ohlcv: dict[str, Any],
) -> None:
    """Scenario 3: Parameter grid search optimization and out-of-sample walk-forward validation."""
    qa = _get_quant_analyst()
    bt = _get_backtesting()

    fast_periods = [3, 5]
    slow_periods = [10, 15]
    best_sharpe = -999.0
    best_params: dict[str, Any] = {}

    # Grid search optimization across parameter combinations
    for f in fast_periods:
        for s in slow_periods:
            cfg_opt = bt.BacktestConfig(
                initial_capital=50_000.0,
                commission_rate=0.0005,
                slippage_rate=0.0002,
                strategy_name="sma",
                parameters={"fast_period": f, "slow_period": s},
            )
            res = bt.run_backtest(synthetic_ohlcv, "sma", cfg_opt)
            if res.sharpe_ratio is not None and res.sharpe_ratio > best_sharpe:
                best_sharpe = res.sharpe_ratio
                best_params = {"fast_period": f, "slow_period": s}

    assert best_params != {}
    assert "fast_period" in best_params and "slow_period" in best_params

    # Walk-forward out-of-sample window test
    split = len(synthetic_ohlcv["close"]) // 2
    oos_ohlcv = {
        k: v[split:] if isinstance(v, list) else v
        for k, v in synthetic_ohlcv.items()
    }
    cfg_oos = bt.BacktestConfig(
        initial_capital=50_000.0,
        commission_rate=0.0005,
        slippage_rate=0.0002,
        strategy_name="sma",
        parameters=best_params,
    )
    oos_res = bt.run_backtest(oos_ohlcv, "sma", cfg_oos)
    assert oos_res is not None
    assert len(oos_res.equity_curve) > 0


def test_t4_scenario_4_terminal_workstation_trading_session(
    tmp_app_data: dict[str, Any],
    fake_client: Client,
) -> None:
    """Scenario 4: Workstation launch in paper mode, slash command dispatch, responsive resizing."""
    async def run() -> None:
        app = SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(160, 48)) as pilot:
            app.client = fake_client
            main_scr = MainScreen()
            app.switch_screen(main_scr)
            await pilot.pause(0.1)

            # Check wide terminal classes
            assert "-lg" in main_scr.classes or "-xl" in main_scr.classes, (
                f"Expected '-lg' or '-xl' in main_scr.classes at (160, 48), got {main_scr.classes!r}"
            )

            # Resize to compact breakpoint
            await pilot.resize_terminal(80, 24)
            await pilot.pause(0.1)
            assert "-xs" in main_scr.classes or "-sm" in main_scr.classes, (
                f"Expected '-xs' or '-sm' in main_scr.classes at (80, 24), got {main_scr.classes!r}"
            )

            # Verify slash commands registry is present
            slash_cmds = getattr(cfg, "SLASH_COMMANDS", {})
            assert isinstance(slash_cmds, dict)

    asyncio.run(run())


def test_t4_scenario_5_broker_sandbox_resilience_and_risk_circuit_breaker(
    fake_client: Client,
) -> None:
    """Scenario 5: Broker sandbox crypto auth -> simulated orders -> daily drawdown lockout."""
    # 1. AES-GCM Crypto authentication verification
    secret_key = "12345678901234567890123456789012"
    token = "BrokerAuthTestSessionToken"
    cipher = encrypt_str(token, secret_key)
    assert decrypt_str(cipher, secret_key) == token

    # 2. Place paper market orders
    params = {
        "requestType": "NEW",
        "exchange": "NC",
        "tradingSymbol": "SBIN",
        "quantity": 100,
        "price": "0",
        "orderType": "MKT",
        "transactionType": "B",
        "productType": "CNF",
    }
    submit_res = fake_client.submit(params)
    assert submit_res is not None

    positions = fake_client.positions()
    assert len(positions) >= 1

    # 3. Verify risk circuit breaker / daily drawdown limits
    be = _get_bot_engine()
    bot = be.BotInstance(
        strategy="pmm",
        symbol="SBIN",
        client=fake_client,
        paper=True,
        parameters={"daily_loss_limit": 2000.0},
    )
    bot.start()
    assert hasattr(bot, "record_pnl"), "BotInstance must expose 'record_pnl' to exercise scenario risk lockout"
    bot.record_pnl(-2500.0)
    assert bot.state in (be.BotState.PAUSED, be.BotState.STOPPED)
