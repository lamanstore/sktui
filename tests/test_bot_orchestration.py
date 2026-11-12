"""Comprehensive Unit and Integration Test Suite for Milestone 5: Bot Orchestration & Automation.

Covers:
- Section 1: Enum & Dataclass Fidelity (BotState, StrategyType, PanicMode, BotInstance)
- Section 2: Lifecycle State Machine Transitions & Invariant Enforcement
- Section 3: Pure Market Making (PMM) Quotes & Inventory Skewing
- Section 4: Empty Depth & Zero-Division Safety (calculate_quotes_from_depth)
- Section 5: Pair Statistical Arbitrage Bot Execution & Spread Ticks
- Section 6: Pre-Trade Risk Engine & Order Limits (submit_order)
- Section 7: Daily Drawdown Circuit Breaker & Lockout (record_pnl)
- Section 8: Emergency Panic Killswitch (CANCEL_ALL & FLATTEN_ALL)
- Section 9: Telemetry Schema, Finite Numerical Values & Counters
- Section 10: Multi-Bot Registry & Fleet Operations (BotManager)
- Section 11: Headless CLI Subparser & Telemetry Handlers (sktui bot)
- Section 12: TUI BotManagerModal Lifecycle & Slash Routing (/bot, /bots)
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import sktui.services.bot_engine as be
from sktui.services.bot_engine import (
    BotInstance,
    BotManager,
    BotState,
    PanicMode,
    StrategyType,
)


@pytest.fixture(autouse=True)
def reset_bot_manager() -> Any:
    """Reset the singleton BotManager before each test for clean isolation."""
    BotManager.reset_instance()
    yield
    BotManager.reset_instance()


# ============================================================================
# Section 1: Enum & Dataclass Fidelity
# ============================================================================

def test_bot_state_enum_values() -> None:
    assert BotState.INIT.value == "INIT"
    assert BotState.CONFIGURED.value == "CONFIGURED"
    assert BotState.RUNNING.value == "RUNNING"
    assert BotState.PAUSED.value == "PAUSED"
    assert BotState.STOPPED.value == "STOPPED"
    assert BotState.ERROR.value == "ERROR"


def test_strategy_type_enum_values() -> None:
    assert StrategyType.PMM.value == "pmm"
    assert StrategyType.ARBITRAGE.value == "arbitrage"
    assert StrategyType.MOMENTUM.value == "momentum"
    assert StrategyType.PREDICTOR.value == "predictor"


def test_panic_mode_enum_values() -> None:
    assert PanicMode.CANCEL_ALL.value == "CANCEL_ALL"
    assert PanicMode.FLATTEN_ALL.value == "FLATTEN_ALL"


def test_bot_instance_defaults() -> None:
    bot = BotInstance(strategy="pmm", symbol="RELIANCE")
    assert bot.strategy == "pmm"
    assert bot.symbol == "RELIANCE"
    assert bot.paper is True
    assert bot.capital == 100000.0
    assert bot.state == BotState.INIT
    assert bot.total_orders == 0
    assert bot.filled_orders == 0
    assert bot.pnl == 0.0
    assert bot.bot_id.startswith("bot_pmm_RELIANCE_")


def test_bot_instance_configured_with_parameters() -> None:
    bot = BotInstance(
        strategy="arbitrage",
        symbol="HDFCBANK,ICICIBANK",
        parameters={"entry_zscore": 2.5},
    )
    assert bot.state == BotState.CONFIGURED
    assert bot.parameters.get("entry_zscore") == 2.5


# ============================================================================
# Section 2: Lifecycle State Machine Transitions & Invariants
# ============================================================================

def test_valid_lifecycle_transitions() -> None:
    bot = BotInstance(strategy="pmm", symbol="INFY")
    assert bot.state == BotState.INIT

    # 1. start
    assert bot.start() is True
    assert bot.state == BotState.RUNNING

    # 2. pause
    assert bot.pause() is True
    assert bot.state == BotState.PAUSED

    # 3. resume
    assert bot.resume() is True
    assert bot.state == BotState.RUNNING

    # 4. stop
    assert bot.stop() is True
    assert bot.state == BotState.STOPPED


def test_start_idempotent_when_running() -> None:
    bot = BotInstance(strategy="pmm", symbol="TCS")
    assert bot.start() is True
    assert bot.start() is True
    assert bot.state == BotState.RUNNING


def test_illegal_pause_from_init() -> None:
    bot = BotInstance(strategy="pmm", symbol="SBIN")
    assert bot.pause() is False
    assert bot.state == BotState.INIT


def test_illegal_resume_from_init() -> None:
    bot = BotInstance(strategy="pmm", symbol="SBIN")
    assert bot.resume() is False
    assert bot.state == BotState.INIT


def test_illegal_resume_from_stopped() -> None:
    bot = BotInstance(strategy="pmm", symbol="TATAMOTORS")
    bot.start()
    bot.stop()
    assert bot.state == BotState.STOPPED

    assert bot.resume() is False
    assert bot.state == BotState.STOPPED


def test_illegal_start_from_stopped() -> None:
    bot = BotInstance(strategy="pmm", symbol="TATAMOTORS")
    bot.start()
    bot.stop()
    assert bot.start() is False
    assert bot.state == BotState.STOPPED


def test_stop_from_paused() -> None:
    bot = BotInstance(strategy="pmm", symbol="ITC")
    bot.start()
    bot.pause()
    assert bot.state == BotState.PAUSED
    assert bot.stop() is True
    assert bot.state == BotState.STOPPED


# ============================================================================
# Section 3: Pure Market Making (PMM) Strategy Quotes & Inventory Skewing
# ============================================================================

def test_pmm_neutral_inventory_spread() -> None:
    bot = BotInstance(
        strategy="pmm",
        symbol="TATAMOTORS",
        parameters={"spread_bps": 20, "inventory_skew": True},
    )
    bid, ask = bot.calculate_quotes(mid_price=500.0, inventory=0)
    assert bid < 500.0 < ask
    spread = ask - bid
    assert round(spread, 2) == 1.0  # 500 * (20/10000) = 1.0


def test_pmm_long_inventory_skewing() -> None:
    bot = BotInstance(
        strategy="pmm",
        symbol="TATAMOTORS",
        parameters={"spread_bps": 20, "inventory_skew": True},
    )
    bid_neutral, ask_neutral = bot.calculate_quotes(mid_price=500.0, inventory=0)
    bid_long, ask_long = bot.calculate_quotes(mid_price=500.0, inventory=50)

    # Long inventory lowers quotes to incentivize selling excess inventory
    assert ask_long <= ask_neutral
    assert bid_long <= bid_neutral


def test_pmm_short_inventory_skewing() -> None:
    bot = BotInstance(
        strategy="pmm",
        symbol="TATAMOTORS",
        parameters={"spread_bps": 20, "inventory_skew": True},
    )
    bid_neutral, ask_neutral = bot.calculate_quotes(mid_price=500.0, inventory=0)
    bid_short, ask_short = bot.calculate_quotes(mid_price=500.0, inventory=-50)

    # Short inventory raises quotes to incentivize buying back inventory
    assert ask_short >= ask_neutral
    assert bid_short >= bid_neutral


def test_pmm_zero_or_negative_mid_price() -> None:
    bot = BotInstance(strategy="pmm", symbol="TEST")
    assert bot.calculate_quotes(mid_price=0.0) == (0.0, 0.0)
    assert bot.calculate_quotes(mid_price=-100.0) == (0.0, 0.0)


# ============================================================================
# Section 4: Empty Depth & Zero-Division Safety
# ============================================================================

def test_pmm_empty_depth_safe() -> None:
    bot = BotInstance(strategy="pmm", symbol="ONGC")
    assert bot.calculate_quotes_from_depth({"bids": [], "asks": []}) is None


def test_pmm_one_sided_depth_safe() -> None:
    bot = BotInstance(strategy="pmm", symbol="ONGC")
    assert bot.calculate_quotes_from_depth({"bids": [[100.0, 10]], "asks": []}) is None
    assert bot.calculate_quotes_from_depth({"bids": [], "asks": [[102.0, 10]]}) is None


def test_pmm_non_dict_depth_safe() -> None:
    bot = BotInstance(strategy="pmm", symbol="ONGC")
    assert bot.calculate_quotes_from_depth(None) is None  # type: ignore[arg-type]
    assert bot.calculate_quotes_from_depth([]) is None  # type: ignore[arg-type]


def test_pmm_valid_depth_calculation() -> None:
    bot = BotInstance(
        strategy="pmm",
        symbol="ONGC",
        parameters={"spread_bps": 20, "inventory_skew": False},
    )
    depth = {
        "bids": [[200.0, 100]],
        "asks": [[202.0, 100]],
    }
    quotes = bot.calculate_quotes_from_depth(depth)
    assert quotes is not None
    bid, ask = quotes
    assert bid < 201.0 < ask


# ============================================================================
# Section 5: Pair Statistical Arbitrage Strategy Execution
# ============================================================================

def test_pair_arbitrage_zscore_upper_breach() -> None:
    bot = BotInstance(
        strategy="arbitrage",
        symbol="HDFCBANK,ICICIBANK",
        parameters={"entry_zscore": 2.0, "exit_zscore": 0.5, "order_amount": 15},
    )
    bot.start()
    orders = bot.process_spread_tick(zscore=2.6, price_a=1600.0, price_b=1000.0)
    assert orders is not None
    assert len(orders) == 2
    # Upper breach: A overpriced, B underpriced -> Sell A, Buy B
    order_a, order_b = orders
    assert order_a["symbol"] == "HDFCBANK"
    assert order_a["action"] == "SELL"
    assert order_a["qty"] == 15
    assert order_b["symbol"] == "ICICIBANK"
    assert order_b["action"] == "BUY"
    assert order_b["qty"] == 15


def test_pair_arbitrage_zscore_lower_breach() -> None:
    bot = BotInstance(
        strategy="arbitrage",
        symbol="HDFCBANK,ICICIBANK",
        parameters={"entry_zscore": 2.0, "exit_zscore": 0.5, "order_amount": 10},
    )
    bot.start()
    orders = bot.process_spread_tick(zscore=-2.8, price_a=1550.0, price_b=1050.0)
    assert orders is not None
    assert len(orders) == 2
    # Lower breach: A underpriced, B overpriced -> Buy A, Sell B
    order_a, order_b = orders
    assert order_a["action"] == "BUY"
    assert order_b["action"] == "SELL"


def test_pair_arbitrage_zscore_no_breach() -> None:
    bot = BotInstance(
        strategy="arbitrage",
        symbol="HDFCBANK,ICICIBANK",
        parameters={"entry_zscore": 2.0, "exit_zscore": 0.5},
    )
    orders = bot.process_spread_tick(zscore=1.2, price_a=1600.0, price_b=1000.0)
    assert orders == []


def test_pair_arbitrage_non_finite_inputs() -> None:
    bot = BotInstance(strategy="arbitrage", symbol="HDFCBANK,ICICIBANK")
    assert bot.process_spread_tick(zscore=float("nan"), price_a=1600.0, price_b=1000.0) == []
    assert bot.process_spread_tick(zscore=2.5, price_a=-10.0, price_b=1000.0) == []


# ============================================================================
# Section 6: Pre-Trade Risk Engine & Order Limits
# ============================================================================

def test_submit_order_within_capital_limit() -> None:
    bot = BotInstance(
        strategy="momentum",
        symbol="RELIANCE",
        parameters={"max_order_val": 100_000.0},
    )
    bot.start()
    ok, res = bot.submit_order(symbol="RELIANCE", qty=20, price=2500.0, action="BUY")
    assert ok is True
    assert isinstance(res, dict)
    assert bot.total_orders == 1
    assert bot.filled_orders == 1


def test_submit_order_exceeding_max_order_val() -> None:
    bot = BotInstance(
        strategy="momentum",
        symbol="RELIANCE",
        parameters={"max_order_val": 50_000.0},
    )
    bot.start()
    ok, reason = bot.submit_order(symbol="RELIANCE", qty=400, price=2500.0, action="BUY")
    assert ok is False
    assert "risk" in str(reason).lower() or "limit" in str(reason).lower()
    assert bot.total_orders == 0


def test_submit_order_when_paused_rejected() -> None:
    bot = BotInstance(strategy="momentum", symbol="RELIANCE")
    bot.start()
    bot.pause()
    ok, reason = bot.submit_order(symbol="RELIANCE", qty=10, price=2500.0, action="BUY")
    assert ok is False
    assert "rejection" in str(reason).lower() or "paused" in str(reason).lower()


def test_submit_order_negative_qty_rejected() -> None:
    bot = BotInstance(strategy="momentum", symbol="RELIANCE")
    bot.start()
    ok, reason = bot.submit_order(symbol="RELIANCE", qty=-5, price=2500.0, action="BUY")
    assert ok is False
    assert "risk" in str(reason).lower() or "positive" in str(reason).lower()


# ============================================================================
# Section 7: Daily Drawdown Circuit Breaker & Lockout
# ============================================================================

def test_record_pnl_within_daily_loss_limit() -> None:
    bot = BotInstance(
        strategy="pmm",
        symbol="SBIN",
        parameters={"daily_loss_limit": 5000.0},
    )
    bot.start()
    bot.record_pnl(-2000.0)
    assert bot.state == BotState.RUNNING
    assert bot.daily_pnl == -2000.0


def test_record_pnl_breaching_daily_loss_limit() -> None:
    bot = BotInstance(
        strategy="pmm",
        symbol="SBIN",
        parameters={"daily_loss_limit": 5000.0},
    )
    bot.start()
    bot.record_pnl(-6000.0)
    assert bot.state in (BotState.STOPPED, BotState.PAUSED)
    assert bot.daily_pnl == -6000.0
    assert bot.last_error is not None
    assert "circuit breaker" in bot.last_error.lower()


def test_record_pnl_multi_step_drawdown() -> None:
    bot = BotInstance(
        strategy="pmm",
        symbol="SBIN",
        parameters={"daily_loss_limit": 3000.0},
    )
    bot.start()
    bot.record_pnl(-1000.0)
    assert bot.state == BotState.RUNNING
    bot.record_pnl(-1200.0)
    assert bot.state == BotState.RUNNING
    bot.record_pnl(-1000.0)  # Total -3200 breaches 3000
    assert bot.state in (BotState.STOPPED, BotState.PAUSED)


# ============================================================================
# Section 8: Emergency Panic Killswitch
# ============================================================================

def test_emergency_panic_cancel_all() -> None:
    bot = BotInstance(strategy="pmm", symbol="RELIANCE")
    bot.start()
    bot.submit_order(symbol="RELIANCE", qty=10, price=2500.0, action="BUY")
    assert len(bot.active_orders) == 1

    res = bot.emergency_panic(mode="CANCEL_ALL")
    assert isinstance(res, dict)
    assert bot.state == BotState.STOPPED
    assert res.get("cancelled_orders") >= 1
    assert len(bot.active_orders) == 0


def test_emergency_panic_flatten_all() -> None:
    fake_client = MagicMock()
    fake_client.positions.return_value = [{"trading_symbol": "RELIANCE", "net_qty": 50}]
    bot = BotInstance(strategy="pmm", symbol="RELIANCE", client=fake_client)
    bot.start()

    res = bot.emergency_panic(mode="FLATTEN_ALL")
    assert isinstance(res, dict)
    assert bot.state == BotState.STOPPED
    assert res.get("mode") == "FLATTEN_ALL"
    fake_client.submit.assert_called_once()


# ============================================================================
# Section 9: Telemetry Schema, Finite Numerical Values & Counters
# ============================================================================

def test_telemetry_schema_keys_and_types() -> None:
    bot = BotInstance(strategy="pmm", symbol="TCS")
    bot.start()
    telem = bot.get_telemetry()
    assert isinstance(telem, dict)
    for field in ("state", "uptime_seconds", "total_orders", "filled_orders", "pnl", "daily_pnl"):
        assert field in telem
        if isinstance(telem[field], (int, float)):
            assert math.isfinite(telem[field])


def test_telemetry_counters_increment() -> None:
    bot = BotInstance(strategy="pmm", symbol="TCS")
    bot.start()
    bot.submit_order(symbol="TCS", qty=5, price=3500.0, action="BUY")
    bot.submit_order(symbol="TCS", qty=5, price=3510.0, action="SELL")
    bot.record_pnl(250.0)

    telem = bot.get_telemetry()
    assert telem["total_orders"] == 2
    assert telem["filled_orders"] == 2
    assert telem["pnl"] == 250.0


def test_telemetry_uptime_tracking() -> None:
    bot = BotInstance(strategy="pmm", symbol="TCS")
    assert bot.get_telemetry()["uptime_seconds"] == 0.0
    bot.start()
    time.sleep(0.05)
    telem = bot.get_telemetry()
    assert telem["uptime_seconds"] > 0.0


# ============================================================================
# Section 10: Multi-Bot Registry & Fleet Operations (BotManager)
# ============================================================================

def test_bot_manager_registration_and_lookup() -> None:
    mgr = BotManager.get_instance()
    b1 = BotInstance(strategy="pmm", symbol="RELIANCE", bot_id="bot_1")
    b2 = BotInstance(strategy="momentum", symbol="TCS", bot_id="bot_2")

    mgr.register(b1)
    mgr.register(b2)

    assert mgr.get_bot("bot_1") is b1
    assert mgr.get_bot("bot_2") is b2
    assert len(mgr.list_bots()) == 2


def test_bot_manager_start_and_stop_all() -> None:
    mgr = BotManager.get_instance()
    b1 = mgr.create_bot(strategy="pmm", symbol="INFY", bot_id="bot_infy")
    b2 = mgr.create_bot(strategy="arbitrage", symbol="SBIN,PNB", bot_id="bot_pairs")

    starts = mgr.start_all()
    assert starts["bot_infy"] is True
    assert starts["bot_pairs"] is True
    assert b1.state == BotState.RUNNING
    assert b2.state == BotState.RUNNING

    stops = mgr.stop_all()
    assert stops["bot_infy"] is True
    assert stops["bot_pairs"] is True
    assert b1.state == BotState.STOPPED
    assert b2.state == BotState.STOPPED


def test_bot_manager_global_panic() -> None:
    mgr = BotManager.get_instance()
    b1 = mgr.create_bot(strategy="pmm", symbol="TATAMOTORS", bot_id="b1")
    b1.start()
    res = mgr.panic_all(mode="CANCEL_ALL")
    assert "b1" in res
    assert b1.state == BotState.STOPPED


def test_bot_manager_aggregated_telemetry() -> None:
    mgr = BotManager.get_instance()
    b1 = mgr.create_bot(strategy="pmm", symbol="TATAMOTORS", bot_id="b1")
    b2 = mgr.create_bot(strategy="momentum", symbol="RELIANCE", bot_id="b2")
    b1.start()
    b1.record_pnl(500.0)
    b2.record_pnl(-200.0)

    aggr = mgr.get_aggregated_telemetry()
    assert aggr["total_bots"] == 2
    assert aggr["running_bots"] == 1
    assert aggr["total_pnl"] == 300.0


# ============================================================================
# Section 11: Headless CLI Subparser & Handlers (sktui bot)
# ============================================================================

def test_cli_bot_argument_parser_options() -> None:
    from sktui.app import build_parser
    parser = build_parser()
    args = parser.parse_args([
        "bot",
        "--strategy", "pmm",
        "--symbol", "TATAMOTORS",
        "--action", "start",
        "--capital", "50000",
        "--paper",
        "--output", "bot_telemetry.json",
        "--json",
    ])
    assert args.strategy == "pmm"
    assert args.symbol == "TATAMOTORS"
    assert args.action == "start"
    assert args.capital == 50000.0
    assert args.paper is True
    assert args.output == "bot_telemetry.json"
    assert args.json is True


def test_cli_bot_action_start_rich_output(capsys: pytest.CaptureFixture) -> None:
    from sktui.app import handle_bot
    args = argparse.Namespace(
        strategy="pmm",
        symbol="TATAMOTORS",
        action="start",
        capital=100000.0,
        paper=True,
        config=None,
        output=None,
        json=False,
    )
    code = handle_bot(args)
    assert code == 0
    out, _ = capsys.readouterr()
    assert "[SKTUI CLI] Automated Trading Bot Orchestrator" in out
    assert "Mode            : PAPER (SANDBOX)" in out
    assert "Action          : START" in out


def test_cli_bot_action_panic_and_status(capsys: pytest.CaptureFixture) -> None:
    from sktui.app import handle_bot
    args_panic = argparse.Namespace(
        strategy="pmm",
        symbol="TATAMOTORS",
        action="panic",
        capital=100000.0,
        paper=True,
        config=None,
        output=None,
        json=False,
    )
    assert handle_bot(args_panic) == 0

    args_status = argparse.Namespace(
        strategy="pmm",
        symbol="TATAMOTORS",
        action="status",
        capital=100000.0,
        paper=True,
        config=None,
        output=None,
        json=False,
    )
    assert handle_bot(args_status) == 0
    out, _ = capsys.readouterr()
    assert "Action          : STATUS" in out


def test_cli_bot_json_stdout(capsys: pytest.CaptureFixture) -> None:
    from sktui.app import handle_bot
    args = argparse.Namespace(
        strategy="pmm",
        symbol="TATAMOTORS",
        action="start",
        capital=100000.0,
        paper=True,
        config=None,
        output=None,
        json=True,
    )
    assert handle_bot(args) == 0
    out, _ = capsys.readouterr()
    parsed = json.loads(out)
    assert parsed["strategy"] == "pmm"
    assert parsed["symbol"] == "TATAMOTORS"
    assert "telemetry" in parsed
    assert parsed["telemetry"]["state"] == "RUNNING"


def test_cli_bot_output_to_file(tmp_path: Path) -> None:
    from sktui.app import handle_bot
    out_file = tmp_path / "bot_out.json"
    args = argparse.Namespace(
        strategy="momentum",
        symbol="RELIANCE",
        action="start",
        capital=100000.0,
        paper=True,
        config=None,
        output=str(out_file),
        json=True,
    )
    assert handle_bot(args) == 0
    assert out_file.exists()
    content = json.loads(out_file.read_text())
    assert content["symbol"] == "RELIANCE"


def test_cli_bot_validation_errors() -> None:
    from sktui.app import handle_bot
    # Missing strategy
    args1 = argparse.Namespace(strategy="", symbol="TCS", action="start", capital=100000.0)
    assert handle_bot(args1) == 1

    # Missing symbol
    args2 = argparse.Namespace(strategy="pmm", symbol="", action="start", capital=100000.0)
    assert handle_bot(args2) == 1

    # Invalid capital
    args3 = argparse.Namespace(strategy="pmm", symbol="TCS", action="start", capital=-500.0)
    assert handle_bot(args3) == 1


# ============================================================================
# Section 12: TUI BotManagerModal Lifecycle & Slash Routing (/bot, /bots)
# ============================================================================

def test_bot_manager_modal_composition() -> None:
    from sktui.screens.modals import BotManagerModal
    modal = BotManagerModal(strategy="pmm", symbol="TATAMOTORS", capital=100000.0)
    assert modal.initial_strategy == "pmm"
    assert modal.initial_symbol == "TATAMOTORS"
    assert modal.capital == 100000.0
    assert modal.is_paper is True


def test_bot_manager_modal_mount_and_refresh() -> None:
    from sktui.screens.modals import BotManagerModal
    modal = BotManagerModal(strategy="pmm", symbol="TATAMOTORS", capital=100000.0)
    # Mock textual query and DataTable components
    mock_tb = MagicMock()
    mock_to = MagicMock()
    mock_strip = MagicMock()
    mock_gauges = MagicMock()

    def query_mock(query_str: str, *args: Any) -> Any:
        if "t-bots-registry" in query_str:
            return mock_tb
        if "t-bot-orders" in query_str:
            return mock_to
        if "bot-status-strip" in query_str:
            return mock_strip
        if "bot-telemetry-gauges" in query_str:
            return mock_gauges
        return MagicMock()

    with patch.object(modal, "query_one", side_effect=query_mock):
        modal.on_mount()
        assert mock_tb.add_column.call_count >= 5
        assert mock_to.add_column.call_count >= 5
        assert mock_tb.add_row.call_count >= 1


def test_bot_manager_modal_panic_actions() -> None:
    from sktui.screens.modals import BotManagerModal
    modal = BotManagerModal(strategy="pmm", symbol="TATAMOTORS")
    mgr = BotManager.get_instance()
    mgr.create_bot(strategy="pmm", symbol="TATAMOTORS", bot_id="b_test")

    with patch.object(modal, "refresh_data"):
        modal.action_panic_cancel_all()
        bot = mgr.get_bot("b_test")
        assert bot is not None
        assert bot.state == BotState.STOPPED


def test_mainscreen_slash_bot_and_bots_dispatch() -> None:
    from sktui.screens.main import MainScreen
    screen = MainScreen.__new__(MainScreen)
    mock_app = MagicMock()
    with patch.object(MainScreen, "app", new_callable=lambda: mock_app):
        screen.status = MagicMock()
        screen.current_symbol = "RELIANCE"

        screen._dispatch_slash("/bot")
        mock_app.push_screen.assert_called_once()

        mock_app.reset_mock()
        screen._dispatch_slash("/bots")
        mock_app.push_screen.assert_called_once()
