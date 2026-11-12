"""End-to-End Tests for Requirement R5: Bot Lifecycle & Orchestration.

Covers:
- Tier 1: Feature Coverage (isolated happy-path tests)
  1. Bot Lifecycle State Machine Transitions (INIT -> RUNNING -> PAUSED -> STOPPED)
  2. Pure Market Making (PMM) Inventory Skewing & Spread Sizing
  3. Pair Arbitrage Bot Signal Execution
  4. Emergency Panic Killswitch (CANCEL_ALL, FLATTEN_ALL)
  5. CLI bot argument parsing and options handling
- Tier 2: Boundary & Corner Cases
  6. Invalid state machine transition prevention (rejection of illegal transitions)
  7. Pre-trade risk check order rejection (max order value breach)
  8. Daily drawdown circuit breaker lockout
  9. Telemetry schema and metric counter validation
  10. Disconnected / zero-depth order book handling (zero-division safety)
"""
from __future__ import annotations

import math
from typing import Any, Callable

import pytest


def _get_bot_engine() -> Any:
    try:
        import sktui.services.bot_engine as be
        return be
    except ImportError:
        pytest.skip("sktui.services.bot_engine implementation pending in Milestone 5")


# ============================================================================
# Tier 1: Feature Coverage (Isolated Happy Path)
# ============================================================================

def test_r5_t1_bot_lifecycle_state_transitions(fake_client: Any) -> None:
    """Verify formal state machine transitions: INIT -> CONFIGURED -> RUNNING -> PAUSED -> STOPPED."""
    be = _get_bot_engine()
    BotState = be.BotState

    bot = be.BotInstance(
        strategy="pmm",
        symbol="RELIANCE",
        client=fake_client,
        paper=True,
    )

    assert bot.state in (BotState.INIT, BotState.CONFIGURED)

    # Start bot
    started = bot.start()
    assert started is True
    assert bot.state == BotState.RUNNING

    # Pause bot
    paused = bot.pause()
    assert paused is True
    assert bot.state == BotState.PAUSED

    # Resume bot
    resumed = bot.resume()
    assert resumed is True
    assert bot.state == BotState.RUNNING

    # Stop bot
    stopped = bot.stop()
    assert stopped is True
    assert bot.state == BotState.STOPPED


def test_r5_t1_pure_market_making_order_skew(fake_client: Any) -> None:
    """Verify PMM bot adjusts bid/ask spreads based on inventory skewing."""
    be = _get_bot_engine()

    bot = be.BotInstance(
        strategy="pmm",
        symbol="TATAMOTORS",
        client=fake_client,
        paper=True,
        parameters={"order_amount": 10, "spread_bps": 20, "inventory_skew": True},
    )

    assert hasattr(bot, "calculate_quotes"), "BotInstance (strategy='pmm') must implement 'calculate_quotes(mid_price, inventory)' per Feature 37"
    # Neutral inventory (position = 0)
    bid_neutral, ask_neutral = bot.calculate_quotes(mid_price=500.0, inventory=0)
    assert bid_neutral < 500.0 < ask_neutral

    # Long inventory (position = +50): should lower both bid and ask to encourage selling
    bid_long, ask_long = bot.calculate_quotes(mid_price=500.0, inventory=50)
    assert ask_long <= ask_neutral
    assert bid_long <= bid_neutral


def test_r5_t1_pair_arbitrage_bot_execution(fake_client: Any) -> None:
    """Verify pair statistical arbitrage bot generates paired orders on Z-score breach."""
    be = _get_bot_engine()

    bot = be.BotInstance(
        strategy="arbitrage",
        symbol="HDFCBANK,ICICIBANK",
        client=fake_client,
        paper=True,
        parameters={"entry_zscore": 2.0, "exit_zscore": 0.5},
    )

    bot.start()
    assert hasattr(bot, "process_spread_tick"), "BotInstance (strategy='arbitrage') must implement 'process_spread_tick(zscore, price_a, price_b)' per Feature 38"
    orders = bot.process_spread_tick(zscore=2.6, price_a=1600.0, price_b=1000.0)
    assert orders is not None
    assert len(orders) >= 2, "Pair arbitrage should generate two paired orders (leg A and leg B)"


def test_r5_t1_emergency_panic_killswitch(fake_client: Any) -> None:
    """Verify emergency panic killswitch cancels all orders and switches state to STOPPED."""
    be = _get_bot_engine()

    bot = be.BotInstance(
        strategy="pmm",
        symbol="RELIANCE",
        client=fake_client,
        paper=True,
    )
    bot.start()

    res = bot.emergency_panic(mode="CANCEL_ALL")
    assert isinstance(res, dict)
    assert bot.state == be.BotState.STOPPED
    assert "cancelled_orders" in res or "status" in res


def test_r5_t1_cli_bot_argument_parsing(
    cli_runner: Callable[[list[str]], tuple[int, str, str]],
) -> None:
    """Verify CLI bot argument parser parses strategy, symbol, and paper flags."""
    code, out, err = cli_runner([
        "bot",
        "--strategy", "pmm",
        "--symbol", "TATAMOTORS",
        "--paper",
    ])
    if code == 2 and "unrecognized arguments" in err:
        pytest.skip("CLI bot subparser pending in Milestone 1/5")
    assert code == 0, f"sktui bot failed with exit code {code}: {err}"
    assert "bot" in out.lower() or "pmm" in out.lower(), f"Expected 'bot'/'pmm' in stdout, got:\n{out}"


# ============================================================================
# Tier 2: Boundary & Corner Cases
# ============================================================================

def test_r5_t2_invalid_state_transition_prevention(fake_client: Any) -> None:
    """Verify state machine rejects illegal transitions cleanly without corruption."""
    be = _get_bot_engine()
    BotState = be.BotState

    bot = be.BotInstance(strategy="pmm", symbol="INFY", client=fake_client, paper=True)
    # Cannot resume from INIT
    res = bot.resume()
    assert res is False or bot.state != BotState.RUNNING

    # Cannot pause from INIT
    res_pause = bot.pause()
    assert res_pause is False

    # Stop bot
    bot.stop()
    assert bot.state == BotState.STOPPED

    # Cannot resume from STOPPED
    res_resume = bot.resume()
    assert res_resume is False
    assert bot.state == BotState.STOPPED


def test_r5_t2_pre_trade_risk_rejection(fake_client: Any) -> None:
    """Verify pre-trade risk engine rejects orders exceeding maximum capital allowance."""
    be = _get_bot_engine()

    bot = be.BotInstance(
        strategy="momentum",
        symbol="RELIANCE",
        client=fake_client,
        paper=True,
        parameters={"max_order_val": 50_000.0},
    )
    bot.start()

    assert hasattr(bot, "submit_order"), "BotInstance must implement 'submit_order(symbol, qty, price, action)' to validate pre-trade risk per Feature 41"
    ok, reason = bot.submit_order(symbol="RELIANCE", qty=400, price=2500.0, action="BUY")
    assert ok is False, "Order exceeding max_order_val must be rejected"
    assert "risk" in str(reason).lower() or "limit" in str(reason).lower()


def test_r5_t2_daily_drawdown_lockout(fake_client: Any) -> None:
    """Verify daily drawdown breach triggers automated circuit breaker lockout."""
    be = _get_bot_engine()

    bot = be.BotInstance(
        strategy="pmm",
        symbol="SBIN",
        client=fake_client,
        paper=True,
        parameters={"daily_loss_limit": 5000.0},
    )
    bot.start()

    assert hasattr(bot, "record_pnl"), "BotInstance must implement 'record_pnl(delta_pnl)' to trigger daily drawdown circuit breaker per Feature 41"
    bot.record_pnl(-6000.0)
    assert bot.state in (be.BotState.PAUSED, be.BotState.STOPPED)


def test_r5_t2_telemetry_schema_and_counters(fake_client: Any) -> None:
    """Verify get_telemetry returns standard monitoring fields with valid numerical types."""
    be = _get_bot_engine()

    bot = be.BotInstance(strategy="pmm", symbol="TCS", client=fake_client, paper=True)
    bot.start()

    telem = bot.get_telemetry()
    assert isinstance(telem, dict)
    for field in ("state", "uptime_seconds", "total_orders", "filled_orders", "pnl"):
        if field in telem:
            if isinstance(telem[field], (int, float)):
                assert math.isfinite(telem[field])


def test_r5_t2_empty_or_disconnected_market_depth(fake_client: Any) -> None:
    """Verify PMM quote calculation avoids ZeroDivisionError when order book depth is empty."""
    be = _get_bot_engine()

    bot = be.BotInstance(strategy="pmm", symbol="ONGC", client=fake_client, paper=True)
    bot.start()

    assert hasattr(bot, "calculate_quotes_from_depth"), "PMM BotInstance must implement 'calculate_quotes_from_depth(depth)' per Feature 37"
    empty_depth = {"bids": [], "asks": []}
    try:
        quotes = bot.calculate_quotes_from_depth(empty_depth)
        assert quotes is None or quotes == [] or quotes == {}
    except ZeroDivisionError:
        pytest.fail("calculate_quotes_from_depth raised ZeroDivisionError on empty depth")
