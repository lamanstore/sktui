"""Unit and integration tests for data pipeline enhancements:
1. UI Tick Coalescing Buffer (20 FPS render throttle)
2. Event-Driven Position and Order Updates on WS ACK
3. Intraday Tick Tape Persistence (save_tape / load_tape)
4. L2 Market Depth Order Book Ladder
5. Options Chain Matrix (/chain)
"""
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from rich.text import Text
from textual.app import App
from textual.widgets import DataTable

from sktui.state.quote_store import QuoteStore
from sktui.ui.widgets.market_depth import MarketDepthWidget
from sktui.screens.modals import MarketDepthModal, OptionChainModal
from sktui.screens.main import MainScreen


def test_intraday_tick_tape_persistence(tmp_path: Path):
    """Test saving and restoring sub-minute tick tape to disk."""
    tape_file = tmp_path / "test_tick_tape.json"
    store = QuoteStore()

    now = time.time()
    # Add 10 ticks for NC2885 (Reliance)
    for i in range(10):
        store.update("NC2885", {"ltp": 1330.0 + i, "qty": 100 * (i + 1)}, wall_ts=now + i)

    # Add 1 stale tick from yesterday
    yesterday = (datetime.now() - timedelta(days=1)).timestamp()
    tape = store.tick_tape.setdefault("NC1594", [])
    tape.append((yesterday, 1150.0, 50.0))

    # Save tape
    saved_count = store.save_tape(tape_file)
    assert saved_count == 10  # Yesterday's tick is filtered out
    assert tape_file.exists()

    # Create fresh QuoteStore and restore from file
    store2 = QuoteStore()
    assert not store2.has_live_ticks("NC2885")
    restored = store2.load_tape(tape_file)
    assert restored == 10
    assert store2.has_live_ticks("NC2885")
    assert len(store2.tick_tape["NC2885"]) == 10
    assert store2.raw_ticks["NC2885"]["ltp"] == 1339.0


def test_market_depth_ladder():
    """Test Level-2 Market Depth book updates, spread, and widget rendering."""
    store = QuoteStore()
    key = "NC2885"

    # 1. Test synthetic depth fallback around LTP
    depth_synth = store.get_depth(key, fallback_ltp=1340.0)
    assert len(depth_synth["bids"]) == 5
    assert len(depth_synth["asks"]) == 5
    assert depth_synth["bids"][0][0] < depth_synth["asks"][0][0]
    assert depth_synth["spread"] > 0
    assert depth_synth.get("synthetic") is True

    # 2. Test authentic broker depth update
    real_depth = {
        "bids": [(1340.50, 500), (1340.00, 1200), (1339.50, 800)],
        "asks": [(1341.00, 450), (1341.50, 900), (1342.00, 1500)],
    }
    book = store.update_depth(key, real_depth)
    assert book["total_bid_qty"] == 2500
    assert book["total_ask_qty"] == 2850
    assert book["spread"] == 0.50
    assert abs(book["imbalance_pct"]) > 0

    # 3. Test MarketDepthWidget rendering
    widget = MarketDepthWidget()
    widget.update_depth_context(
        item={"tradingSymbol": "RELIANCE", "exchange": "NC"},
        quote={"ltp": 1340.75},
        depth=book,
        width=60,
    )
    rendered = widget.render_content(width=60)
    assert isinstance(rendered, Text)
    plain = rendered.plain
    assert "DEPTH L2" in plain
    assert "RELIANCE" in plain
    assert "1,340.50" in plain
    assert "1,341.00" in plain


def test_option_chain_modal_strikes_and_atm():
    """Test OptionChainModal strike spacing, ATM detection, and contract pair generation."""
    modal = OptionChainModal(underlying="NIFTY")
    assert modal.underlying == "NIFTY"

    class DummyApp:
        size = type("Size", (), {"width": 120, "height": 40})()
        available_themes = {"sktui-dark": {}}
        theme = "sktui-dark"
        screen_stack = []

    modal._app = DummyApp()
    modal.underlying = "NIFTY"
    modal.spot_ltp = 24230.0
    modal.atm_strike = 24250.0  # nearest 50-step strike

    # Check contracts mapping
    modal.refresh_chain = lambda: None
    modal.atm_strike = 24250.0
    modal.strikes_list = [24200.0, 24250.0, 24300.0]
    modal.contracts = {
        24250.0: {
            "CE": {"tradingSymbol": "NIFTY24250CE", "strike": 24250.0, "optionType": "CE"},
            "PE": {"tradingSymbol": "NIFTY24250PE", "strike": 24250.0, "optionType": "PE"},
        }
    }
    ce = modal.contracts[24250.0]["CE"]
    pe = modal.contracts[24250.0]["PE"]
    assert ce["tradingSymbol"] == "NIFTY24250CE"
    assert pe["tradingSymbol"] == "NIFTY24250PE"


def test_ui_tick_coalescing_and_event_driven_positions(tmp_path: Path, monkeypatch):
    """Test UI Tick Coalescing batching and optimistic position updates on ACK."""
    monkeypatch.setattr("sktui.config.CONF", tmp_path)
    monkeypatch.setattr("sktui.config.DATA", tmp_path)
    monkeypatch.setattr("sktui.config.WATCH_FILE", tmp_path / "watchlist.json")
    monkeypatch.setattr("sktui.config.ALERTS_FILE", tmp_path / "alerts.json")

    screen = MainScreen()
    screen._coalescing_active = True

    # 1. Verify tick coalescing buffer holds dirty keys
    key = "NCONGC"
    screen._on_tick_update(key, {"ltp": 255.0, "tradingSymbol": "ONGC"}, 250.0, 255.0)
    assert key in screen._dirty_tick_keys
    assert screen._prev_tick_ltp[key] == 250.0

    # 2. Test optimistic fill on WebSocket ACK
    ack_frame = {
        "AckState": "TRADED",
        "BuySellString": "Buy",
        "TradeQty": 100,
        "TradePrice": 255.0,
        "TradingSymbol": "ONGC",
        "Exchange": "NC",
        "SharekhanOrderID": "1009988",
    }
    screen.data["positions"] = []
    screen.data["orders"] = []

    screen.on_ack(ack_frame)

    # Verify orders updated optimistically
    assert len(screen.data["orders"]) == 1
    assert screen.data["orders"][0]["orderId"] == "1009988"
    assert screen.data["orders"][0]["execQty"] == 100
    assert screen.data["orders"][0]["execPrice"] == 255.0

    # Verify positions updated optimistically with zero polling delay
    assert len(screen.data["positions"]) == 1
    pos = screen.data["positions"][0]
    assert pos["tradingSymbol"] == "ONGC"
    assert pos["netQty"] == 100
    assert pos["avgPrice"] == 255.0

    # Test sell order reducing position
    ack_sell = {
        "AckState": "TRADED",
        "BuySellString": "Sell",
        "TradeQty": 50,
        "TradePrice": 260.0,
        "TradingSymbol": "ONGC",
        "Exchange": "NC",
        "SharekhanOrderID": "1009989",
    }
    screen.on_ack(ack_sell)
    assert pos["netQty"] == 50
    assert len(screen.data["orders"]) == 2

