"""Tests for the concrete 3-pane fixed workspace redesign, new utilities, and state models."""
import pytest

from sktui import api
from sktui.api.market_state import (
    MarketState, SubscriptionManager, SymbolState, normalize_tick,
)
from sktui.config import (
    ALERT_THRESHOLDS, DEFAULT_PANEL_WIDTHS, KEY_ACTIONS, PANE_KEYS, SCAN_DEFAULTS,
)
from sktui.screens.main import (
    CommandBar, MainScreen, StatusLogPanel, SymbolFocusPanel, TopStatusBar,
    TradeRiskPanel, WatchlistPanel,
)
from sktui.utils import (
    compact_number, compact_price, format_change, format_volume,
    render_alert_badge, safe_float, status_text, truncate_symbol,
)


def test_utils_compact_and_formatting():
    # safe_float
    assert safe_float(12.34) == 12.34
    assert safe_float("₹2,998.40") == 2998.40
    assert safe_float(None, default=0.0) == 0.0
    assert safe_float("invalid", default=-1.0) == -1.0

    # compact_number
    assert compact_number(1_250_000_000) == "1.25B"
    assert compact_number(1_200_000) == "1.2M"
    assert compact_number(55_400) == "55.4K"
    assert compact_number(450) == "450"
    assert compact_number(0) == "0"


    # compact_price
    assert compact_price(2998.40) == "₹2,998.40"
    assert compact_price("150.5", symbol="$") == "$150.50"
    assert compact_price(None) == "₹--.--"
    assert compact_price("") == "₹--.--"

    # format_change
    assert format_change(18.2, 0.61) == "+18.20 (+0.61%)"
    assert format_change(-12.5, -0.42) == "-12.50 (-0.42%)"
    assert format_change(0.0, 0.0) == "0.00 (0.00%)"

    # format_volume
    assert format_volume(2_100_000) == "2.1M"

    # render_alert_badge
    assert render_alert_badge("critical") == "🚨"
    assert render_alert_badge("warning") == "▲"
    assert render_alert_badge("info") == "ℹ"
    assert render_alert_badge("nominal") == "●"

    # truncate_symbol
    assert truncate_symbol("RELIANCE", 10) == "RELIANCE"
    assert truncate_symbol("VERYLONGSYMBOLNAME", 8) == "VERYLON…"

    # status_text
    assert status_text("CONNECTED", 14.2) == "FEED: OK (14ms)"
    assert status_text("DISCONNECTED") == "FEED: DISCONNECTED"


def test_config_registry():
    assert PANE_KEYS["watchlist"] == "1"
    assert PANE_KEYS["symbol"] == "2"
    assert PANE_KEYS["trade"] == "3"
    assert PANE_KEYS["scanner"] == "4"
    assert PANE_KEYS["alerts"] == "5"
    assert PANE_KEYS["logs"] == "6"

    assert KEY_ACTIONS["b"] == "buy"
    assert KEY_ACTIONS["s"] == "sell"
    assert KEY_ACTIONS["m"] == "modify"
    assert KEY_ACTIONS["x"] == "cancel_order"
    assert KEY_ACTIONS["c"] == "chart"

    assert DEFAULT_PANEL_WIDTHS["left_pane"] == 32
    assert ALERT_THRESHOLDS["pct"] > 0
    assert SCAN_DEFAULTS["gainers_min_pct"] == 1.0


def test_market_state_and_models():
    # normalize_tick
    raw = {
        "status": 100,
        "message": "feed",
        "data": {
            "exchangeCode": "NC",
            "scripCode": 2885,
            "lastTradedPrice": 2998.40,
            "netPriceChange": 18.20,
            "percentChange": 0.61,
            "bid": 2998.25,
            "ask": 2998.55,
            "volume": 1200000,
            "openInterest": 55400,
        },
    }
    norm = normalize_tick(raw)
    assert norm["ltp"] == 2998.40
    assert norm["rsChange"] == 18.20
    assert norm["perChange"] == 0.61
    assert norm["bidPrice"] == 2998.25
    assert norm["offPrice"] == 2998.55
    assert norm["qty"] == 1200000
    assert norm["currentOI"] == 55400

    # MarketState & SymbolState
    state = MarketState()
    sym_state = state.update_tick(raw)
    assert sym_state is not None
    assert sym_state.key == "NC2885"
    assert sym_state.last_price == 2998.40
    assert sym_state.bid == 2998.25
    assert sym_state.ask == 2998.55
    assert sym_state.volume == 1200000
    assert not state.is_stale("NC2885")

    # SubscriptionManager
    feed_calls = []
    class DummyFeed:
        ready = True
        def subscribe(self, key):
            feed_calls.append(("sub", key))
        def unsubscribe(self, key):
            feed_calls.append(("unsub", key))

    mgr = SubscriptionManager(get_feed=lambda: DummyFeed())
    mgr.add("NC2885")
    mgr.add("NC11536")
    assert "NC2885" in mgr.keys()
    assert ("sub", "NC2885") in feed_calls

    mgr.remove("NC2885")
    assert "NC2885" not in mgr.keys()
    assert ("unsub", "NC2885") in feed_calls


def test_redesigned_screen_structure():
    screen = MainScreen()
    assert hasattr(screen, "selected_symbol")
    assert hasattr(screen, "market_state")
    assert hasattr(screen, "watchlist_service")
    assert hasattr(screen, "quotes")

    # Verify panel classes are exported and instantiate
    top = TopStatusBar()
    watch_p = WatchlistPanel()
    sym_p = SymbolFocusPanel()
    trade_p = TradeRiskPanel()
    log_p = StatusLogPanel()
    cmd_b = CommandBar()

    assert top is not None
    assert watch_p is not None
    assert sym_p is not None
    assert trade_p is not None
    assert log_p is not None
    assert cmd_b is not None
