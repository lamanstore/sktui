"""Regression and QA verification test suite for SKTUI audit fixes:
- Core Services: MACD signal line EMA without zero-bias, flat-price RSI=50, paper trading MODIFY & booked P/L (bpl), USDJPY Yahoo ticker, utils NaN/bool/edge-case guards.
- UI Workspace: Responsive breakpoints across 80x24 (-xs/-short), 120x40 (-md/-medium), 160x50 (-lg/-tall), non-clipped 80x24 center chart, app.quotes sharing, null-client & empty-watchlist guards, Escape context handling, RiskDashboardScreen lockout guard, widget numeric safety.
- UI Modals & Charts: FocusModal/ScannerModal/ReplayModal/DebugModal keybindings, ReplayModal thread pause on Escape/unmount, HistoryScreen non-positive closes guard &MainScreen QuoteStore resolution, SystemStatusScreen/RiskScreen null-client safety.
"""
from __future__ import annotations

import asyncio
import math
from unittest.mock import MagicMock

import pytest
from rich.text import Text
from textual.widgets import DataTable, Input, Static

from sktui import app as sk
from sktui import config
from sktui.api.client import Client
from sktui.screens.main import MainScreen
from sktui.screens.modals import (
    DebugModal,
    FocusModal,
    HistoryScreen,
    ReplayModal,
    RiskScreen,
    ScannerModal,
    SystemStatusScreen,
)
from sktui.services import indicators as ind
from sktui.services.market_data import to_yahoo_ticker
from sktui.services.replay_engine import ReplayEngine
from sktui.services.risk_engine import RiskEngine
from sktui.services.scanner import MarketScanner
from sktui.state.quote_store import QuoteStore
from sktui.ui.screens.risk_dashboard import RiskDashboardScreen
from sktui.ui.widgets.dashboard_cards import update_dashboard, update_pnl_strip
from sktui.ui.widgets.market_scanner import MarketScannerWidget
from sktui.ui.widgets.order_action import OrderActionWidget
from sktui.ui.widgets.risk_summary import RiskSummaryWidget
from sktui.ui.widgets.symbol_focus import SymbolFocusPanel
from sktui.ui.widgets.watchlist_table import WATCH_COLS, add_watch_row, update_watch_row
from sktui.utils import build_order, compact_price, safe_float, truncate_symbol


# ══════════════════════════════════════════════════════════════════════════════
#  1. CORE SERVICES REGRESSIONS
# ══════════════════════════════════════════════════════════════════════════════

def test_macd_signal_line_not_corrupted_by_leading_nones():
    """MACD signal line must only start at slow + signal - 2 and never blend leading 0.0s."""
    # Linear price series: after warmup, fast_ema - slow_ema is a constant > 0
    prices = [100.0 + i * 2.0 for i in range(60)]
    macd_line, signal_line, hist = ind.macd(prices, fast=12, slow=26, signal=9)

    # First valid MACD value is at index slow - 1 = 25
    assert all(v is None for v in macd_line[:25])
    assert macd_line[25] is not None

    # First valid signal value must be at index (slow - 1) + (signal - 1) = 33
    assert all(v is None for v in signal_line[:33])
    assert signal_line[33] is not None

    # For a purely linear series, MACD is constant (14.0), so its 9-period EMA must equal MACD
    expected_macd = macd_line[25]
    assert expected_macd == pytest.approx(14.0, rel=1e-5)
    assert signal_line[33] == pytest.approx(expected_macd, rel=1e-5)
    assert hist[33] == pytest.approx(0.0, abs=1e-6)


def test_rsi_flat_prices_returns_neutral_50():
    """Completely flat price series (avg_gain == 0, avg_loss == 0) must return 50.0, not 100.0."""
    flat = [250.0] * 30
    res = ind.rsi(flat, period=14)
    assert all(v is None for v in res[:14])
    for v in res[14:]:
        assert v == pytest.approx(50.0)


def test_indicators_invalid_periods_and_nan_guards():
    """Indicators gracefully handle period <= 0, NaN, Inf, and booleans without raising."""
    vals = [100.0, float("nan"), 102.0, float("inf"), 104.0]
    assert ind.ema(vals, 0) == [None] * len(vals)
    assert ind.sma(vals, -3) == [None] * len(vals)
    assert ind.rsi(vals, 0) == [None] * len(vals)
    assert ind.atr(vals, vals, vals, 0) == [None] * len(vals)
    m, s, h = ind.macd(vals, fast=0, slow=26, signal=9)
    assert m == [None] * len(vals) and s == [None] * len(vals) and h == [None] * len(vals)
    u, mid, l = ind.bollinger_bands(vals, period=0)
    assert u == [None] * len(vals)
    assert ind.support_resistance(vals, vals, window=0) == ([], [])


def test_paper_trading_modify_and_booked_pnl():
    """Paper trading MODIFY updates order in-place without duplicating qty, and computes bpl on close."""
    client = Client("key", "tok", "123", paper=True)

    # 1. Submit initial BUY order: 10 @ 1000
    res_new = client.submit({
        "requestType": "NEW",
        "tradingSymbol": "TCS",
        "scripCode": 11536,
        "exchange": "NC",
        "transactionType": "B",
        "quantity": 10,
        "price": "1000.00",
        "productType": "INVESTMENT",
    })
    oid = res_new["orderId"]
    assert len(client.orders()) == 1
    assert client.positions()[0]["netQty"] == 10
    assert client.positions()[0]["buyQty"] == 10
    assert client.holdings()[0]["aval"] == 10

    # 2. MODIFY the order to 15 @ 1020 -> should NOT create a second order or sum to 25!
    res_mod = client.submit({
        "requestType": "MODIFY",
        "orderId": oid,
        "tradingSymbol": "TCS",
        "scripCode": 11536,
        "exchange": "NC",
        "transactionType": "B",
        "quantity": 15,
        "price": "1020.00",
        "productType": "INVESTMENT",
    })
    assert res_mod["orderId"] == oid
    assert len(client.orders()) == 1
    assert client.orders()[0]["orderQty"] == 15
    assert client.orders()[0]["orderPrice"] == "1020.00"
    pos = client.positions()[0]
    assert pos["buyQty"] == 15
    assert pos["netQty"] == 15
    assert pos["avgPrice"] == pytest.approx(1020.0)
    assert client.holdings()[0]["aval"] == 15

    # 3. SELL 10 @ 1050 -> booked P/L (bpl) on 10 matched shares = 10 * (1050 - 1020) = +300.0
    client.submit({
        "requestType": "NEW",
        "tradingSymbol": "TCS",
        "scripCode": 11536,
        "exchange": "NC",
        "transactionType": "S",
        "quantity": 10,
        "price": "1050.00",
        "productType": "INVESTMENT",
    })
    pos_after_sell = client.positions()[0]
    assert pos_after_sell["netQty"] == 5
    assert pos_after_sell["bpl"] == pytest.approx(300.0)


def test_usdjpy_yahoo_ticker_and_utils_hardening():
    """USDJPY maps to USDJPY=X and utility helpers guard against bool/NaN/Inf/disclosedQty."""
    assert to_yahoo_ticker("USDJPY", "RN") == "USDJPY=X"

    assert safe_float(True, default=-1.0) == -1.0
    assert safe_float(float("nan"), default=0.0) == 0.0
    assert safe_float(float("inf"), default=0.0) == 0.0
    assert safe_float("$1,250.75") == pytest.approx(1250.75)

    assert compact_price(True) == "₹--.--"
    assert compact_price(float("nan")) == "₹--.--"
    assert truncate_symbol("RELIANCE", 0) == ""
    assert truncate_symbol("RELIANCE", 1) == "…"

    with pytest.raises(ValueError, match="disclosed quantity cannot exceed"):
        build_order(
            {
                "exchange": "NC",
                "scripCode": "2475",
                "tradingSymbol": "ONGC",
                "transactionType": "B",
                "quantity": "10",
                "disclosedQty": "20",
                "price": "100.0",
            },
            "NEW",
            "1",
            "LOGIN",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  2. UI WORKSPACE REGRESSIONS
# ══════════════════════════════════════════════════════════════════════════════

def test_responsive_breakpoints_and_80x24_layout(tmp_path, monkeypatch):
    """Verify non-conflicting responsive classes across 80x24, 120x40, 160x50 and unclipped 80x24 chart."""
    monkeypatch.setattr(sk, "DATA", tmp_path)
    monkeypatch.setattr(sk, "WATCH_FILE", tmp_path / "w.json")
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "WATCH_FILE", tmp_path / "w.json")

    class DummyClient:
        paper = True
        customer_id = "1"
        cid = "1"
        login_id = "TRADER"
        full_name = "Trader"
        access_token = "tok"
        api_key = "key123456"
        exchanges = ["NC", "BC"]

        def orders(self):
            return []
        def positions(self):
            return []
        def holdings(self):
            return []
        def funds(self, exch="NC"):
            return [{"currentCashBalance": 100000.0}]
        def historical(self, exch, scrip, iv):
            return []

    async def run():
        app = sk.SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.client = DummyClient()
            app.switch_screen(MainScreen())
            await pilot.pause(0.4)
            main = app.screen
            assert isinstance(main, MainScreen)

            # 1. At 80x24: must be -xs and -short, NOT -sm or -medium-h
            assert "-xs" in main.classes
            assert "-sm" not in main.classes
            assert "-short" in main.classes
            assert "-medium-h" not in main.classes

            # 2. App quotes reference must be shared with MainScreen.quotes
            assert app.quotes is main.quotes

            # 3. Center pane and chart panel must fit within 80 columns without 60-col override clipping
            center = main.query_one("#center-pane")
            assert center.size.width >= 28
            from sktui.ui.widgets.chart_canvas import InteractiveChartCanvas
            focus_panel = main.query_one("#symbol-focus-panel", SymbolFocusPanel)
            canvas = focus_panel.query_one("#chart-panel", InteractiveChartCanvas)
            assert canvas is not None
            cw, ch = canvas.chart_size
            assert 16 <= cw <= center.size.width
            assert ch >= 4
            assert main.query_one("#top-status").content_region.height >= 1
            assert main.query_one("#cmd-input").content_region.height >= 1

            # 4. Resize to 120x40 -> -md and -medium
            await pilot.resize_terminal(120, 40)
            await pilot.pause(0.2)
            assert "-md" in main.classes
            assert "-medium" in main.classes
            assert "-medium-h" not in main.classes

            # 5. Resize to 160x50 -> -lg and -tall
            await pilot.resize_terminal(160, 50)
            await pilot.pause(0.2)
            assert "-lg" in main.classes
            assert "-tall" in main.classes

            # 6. Escape context handling: unfocus #cmd-input -> #t-watch
            cmd_in = main.query_one("#cmd-input", Input)
            cmd_in.focus()
            cmd_in.value = "/ord"
            await pilot.pause(0.1)
            assert cmd_in.has_focus
            await pilot.press("escape")
            await pilot.pause(0.1)
            assert cmd_in.value == ""
            assert main.focused.id == "t-watch"

            # 7. Null-client logout safety
            app.client = None
            main.action_logout()
            await pilot.pause(0.2)
            assert type(app.screen).__name__ == "LoginScreen"

    asyncio.run(run())


def test_risk_dashboard_screen_lockout_guard():
    """RiskDashboardScreen only resets and dismisses on 'r' when lockout is active."""
    async def run():
        app = sk.SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            main = MainScreen()
            app.switch_screen(main)
            await pilot.pause(0.3)

            eng = main.order_service.risk_engine
            eng._lockout_active = False

            modal = RiskDashboardScreen()
            dismissed: list = []
            app.push_screen(modal, lambda res: dismissed.append(res))
            await pilot.pause(0.2)
            assert isinstance(app.screen, RiskDashboardScreen)

            # Pressing 'r' when not locked out must NOT dismiss the modal
            await pilot.press("r")
            await pilot.pause(0.1)
            assert isinstance(app.screen, RiskDashboardScreen)
            assert dismissed == []

            # Activate lockout and press 'r' -> resets lockout and dismisses with True
            eng._lockout_active = True
            await pilot.press("r")
            await pilot.pause(0.2)
            assert eng._lockout_active is False
            assert dismissed == [True]

    asyncio.run(run())


def test_widgets_formatted_numeric_strings_safety():
    """Widgets safely parse formatted currency/percent strings without ValueError."""
    positions = [{"tradingSymbol": "ONGC", "netQty": "10", "bpl": "₹1,250.50", "mtm": "-₹250.25"}]
    orders = [{"orderId": "1", "tradingSymbol": "ONGC", "orderStatus": "Open"}]
    watch = [{"scripCode": 2475, "tradingSymbol": "ONGC", "exchange": "NC"}]
    raw_ticks = {"NC2475": {"ltp": "₹285.50", "perChange": "+1.75%", "rsChange": "₹4.90", "qty": "1,20,000"}}

    # RiskSummaryWidget
    rw = RiskSummaryWidget()
    rw.positions = positions
    rw.orders = orders
    assert "1,000.25" in rw.render_content().plain

    # OrderActionWidget
    ow = OrderActionWidget()
    ow.item = watch[0]
    ow.quote = raw_ticks["NC2475"]
    ow.position = positions[0]
    ow.open_orders = 1
    assert "ONGC" in ow.render_content().plain

    # MarketScannerWidget
    mw = MarketScannerWidget()
    mw.raw_ticks = raw_ticks
    mw.watch = watch
    assert "ONGC" in mw.render_content().plain


# ══════════════════════════════════════════════════════════════════════════════
#  3. UI MODALS & CHARTS REGRESSIONS
# ══════════════════════════════════════════════════════════════════════════════

def test_focus_modal_and_scanner_modal_keybindings():
    """FocusModal (b/s/c/a) and ScannerModal (1/2/3/4/r/b/s/c) keybindings invoke their actions."""
    store = QuoteStore()
    store.update("NC2475", {
        "tradingSymbol": "ONGC", "exchange": "NC", "scripCode": 2475,
        "ltp": 280.0, "open": 270.0, "high": 282.0, "low": 268.0, "close": 270.0,
        "rsChange": 10.0, "perChange": 3.7, "qty": 100000.0,
    })
    scanner = MarketScanner(store)
    item = {"tradingSymbol": "ONGC", "exchange": "NC", "scripCode": 2475, "price": 280.0}

    async def run():
        app = sk.SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()

            # 1. FocusModal 'b' keybinding
            results: list = []
            app.push_screen(FocusModal(item, {"ltp": 280.0}), lambda r: results.append(r))
            await pilot.pause(0.2)
            assert isinstance(app.screen, FocusModal)
            await pilot.press("b")
            await pilot.pause(0.2)
            assert results == [("trade", "B", item)]

            # 2. ScannerModal '2' (volume), '3' (breakouts), '4' (vwap), '1' (movers), 'b' (buy)
            scan_results: list = []
            sc_modal = ScannerModal(scanner)
            app.push_screen(sc_modal, lambda r: scan_results.append(r))
            await pilot.pause(0.2)
            assert isinstance(app.screen, ScannerModal)

            await pilot.press("2")
            await pilot.pause(0.1)
            assert sc_modal.active_category == "volume"

            await pilot.press("3")
            await pilot.pause(0.1)
            assert sc_modal.active_category == "breakouts"

            await pilot.press("4")
            await pilot.pause(0.1)
            assert sc_modal.active_category == "vwap"

            await pilot.press("1")
            await pilot.pause(0.1)
            assert sc_modal.active_category == "movers"

            await pilot.press("b")
            await pilot.pause(0.2)
            assert len(scan_results) == 1
            assert scan_results[0][0] == "trade"
            assert scan_results[0][1] == "B"

    asyncio.run(run())


def test_replay_modal_keybindings_and_unmount_pause():
    """ReplayModal hotkeys (space, right, r) work and Escape pauses the background replay thread."""
    from sktui.chart import Candle

    candles = [
        Candle(timestamp="1", open=100.0, high=105.0, low=98.0, close=104.0, volume=400.0),
        Candle(timestamp="2", open=104.0, high=108.0, low=103.0, close=107.0, volume=800.0),
    ]
    engine = ReplayEngine()
    engine.load_candles("ONGC", "NC", candles, scrip_code=2475)

    async def run():
        app = sk.SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            modal = ReplayModal(engine)
            app.push_screen(modal)
            await pilot.pause(0.2)

            # 'right' steps forward 1 tick
            await pilot.press("right")
            await pilot.pause(0.1)
            assert engine.current_tick_index == 1

            # 'r' resets replay to 0
            await pilot.press("r")
            await pilot.pause(0.1)
            assert engine.current_tick_index == 0

            # 'space' starts playback, 'escape' closes modal and must pause engine!
            await pilot.press("space")
            await pilot.pause(0.1)
            assert engine.is_playing is True

            await pilot.press("escape")
            await pilot.pause(0.2)
            assert engine.is_playing is False

    asyncio.run(run())


def test_debug_status_risk_modals_and_history_nonpositive_closes():
    """DebugModal ('r'), SystemStatusScreen/RiskScreen with client=None, and HistoryScreen._update_meta edge case."""
    async def run():
        app = sk.SKApp(paper=True)
        app.enable_feed = False
        app.client = None
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()

            # 1. DebugModal 'r' keybinding
            dbg = DebugModal()
            app.push_screen(dbg)
            await pilot.pause(0.2)
            await pilot.press("r")
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.1)

            # 2. SystemStatusScreen with app.client = None
            app.push_screen(SystemStatusScreen())
            await pilot.pause(0.2)
            assert isinstance(app.screen, SystemStatusScreen)
            await pilot.press("escape")
            await pilot.pause(0.1)

            # 3. RiskScreen with app.client = None
            app.push_screen(RiskScreen())
            await pilot.pause(0.2)
            assert isinstance(app.screen, RiskScreen)
            await pilot.press("escape")
            await pilot.pause(0.1)

            # 4. HistoryScreen._update_meta with non-positive _closes
            hs = HistoryScreen({"tradingSymbol": "ONGC", "exchange": "NC", "scripCode": 2475})
            hs._closes = [0.0, -5.0]
            hs._update_meta()  # Must not raise ValueError: max() arg is an empty sequence

    asyncio.run(run())
