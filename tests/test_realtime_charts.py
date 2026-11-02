"""Tests for Phase 3 real-time scalper charts, sub-minute candle formation,
multi-density zoom, 2D visual crosshair, full chart fit-all, and interactive canvas."""
from __future__ import annotations

import asyncio
import time
import pytest

from rich.text import Text
from textual.app import App, ComposeResult

from sktui.chart import (
    Candle, chart_chrome_rows, compress_candles, compute_viewport,
    merge_live_tick_into_candles, render_candlestick_chart, render_chart,
    step_zoom,
)
from sktui.config import INTERVAL_SECONDS, SUB_MINUTE_INTERVALS
from sktui.screens.modals import HistoryScreen
from sktui.state.quote_store import QuoteStore
from sktui.ui.widgets.chart_canvas import InteractiveChartCanvas
from sktui.ui.widgets.symbol_focus import SymbolFocusPanel


# ── 1. QuoteStore Tick Tape & Sub-Minute Candles ─────────────────────────────

def test_quote_store_tick_tape_and_listeners():
    store = QuoteStore()
    key = "NC2475"
    events: list[tuple[str, float, float]] = []

    def on_tick(k: str, raw: dict, ltp: float, vol: float):
        events.append((k, ltp, vol))

    store.add_listener(on_tick)
    assert not store.has_live_ticks(key)

    # 1. First tick with cumulative volume
    store.update(key, {"ltp": 100.0, "qty": 5000}, wall_ts=1000.0)
    assert store.has_live_ticks(key)
    assert len(events) == 1
    assert events[0] == (key, 100.0, 0.0)

    # 2. Second tick with cumulative volume delta
    store.update(key, {"ltp": 101.5, "qty": 5250}, wall_ts=1002.0)
    assert len(events) == 2
    assert events[1] == (key, 101.5, 250.0)

    # 3. Third tick with explicit tickVol
    store.update(key, {"ltp": 101.0, "tickVol": 75}, wall_ts=1004.0)
    assert len(events) == 3
    assert events[2] == (key, 101.0, 75.0)

    # Tape contents
    tape = store.tape(key, include_seeded=False)
    assert len(tape) == 3
    assert tape[1] == (1002.0, 101.5, 250.0)

    # Test listener removal
    store.remove_listener(on_tick)
    store.update(key, {"ltp": 102.0, "tickVol": 10}, wall_ts=1005.0)
    assert len(events) == 3  # Not called after removal


def test_quote_store_get_candles_aggregation():
    store = QuoteStore()
    key = "NC11536"
    t0 = 1700000000.0  # reference epoch

    # Add 10 ticks across three 5-second buckets
    # Bucket 0: 0.0, 1.0, 2.0 (prices 100, 103, 99; vols 10, 20, 30)
    store.update(key, {"ltp": 100.0, "tickVol": 10}, wall_ts=t0 + 0.0)
    store.update(key, {"ltp": 103.0, "tickVol": 20}, wall_ts=t0 + 1.0)
    store.update(key, {"ltp": 99.0,  "tickVol": 30}, wall_ts=t0 + 2.0)
    # Bucket 1: 5.0, 7.0 (prices 102, 105; vols 40, 50)
    store.update(key, {"ltp": 102.0, "tickVol": 40}, wall_ts=t0 + 5.0)
    store.update(key, {"ltp": 105.0, "tickVol": 50}, wall_ts=t0 + 7.0)
    # Bucket 2: 10.0 (price 104; vol 60)
    store.update(key, {"ltp": 104.0, "tickVol": 60}, wall_ts=t0 + 10.0)

    # 5-second candles
    c_5s = store.get_candles(key, interval_sec=5)
    assert len(c_5s) == 3

    b0 = c_5s[0]
    assert b0.open == 100.0
    assert b0.high == 103.0
    assert b0.low == 99.0
    assert b0.close == 99.0
    assert b0.volume == 60.0

    b1 = c_5s[1]
    assert b1.open == 102.0
    assert b1.high == 105.0
    assert b1.low == 102.0
    assert b1.close == 105.0
    assert b1.volume == 90.0

    # TICK candles (interval_sec <= 0)
    c_tick = store.get_candles(key, interval_sec=0)
    assert len(c_tick) == 6
    assert c_tick[-1].close == 104.0


# ── 2. Real-Time Candle Formation & Rollover ─────────────────────────────────

def test_merge_live_tick_into_candles_forming_and_rollover():
    candles: list[Candle] = []
    t_start = 100.0  # epoch
    sec = 5

    # 1. First tick in bucket 20 (100.0 - 104.9)
    candles, rem = merge_live_tick_into_candles(candles, ltp=250.0, vol_delta=100.0, interval_sec=sec, now_ts=100.0)
    assert len(candles) == 1
    assert candles[0].open == 250.0
    assert candles[0].close == 250.0
    assert candles[0].volume == 100.0
    assert rem == 5.0

    # 2. Tick within same bucket makes new high and updates close
    candles, rem = merge_live_tick_into_candles(candles, ltp=255.0, vol_delta=50.0, interval_sec=sec, now_ts=102.5)
    assert len(candles) == 1
    assert candles[0].high == 255.0
    assert candles[0].low == 250.0
    assert candles[0].close == 255.0
    assert candles[0].volume == 150.0
    assert pytest.approx(rem, 0.1) == 2.5

    # 3. Tick advances into bucket 21 (105.0+) -> rolls over new candle
    candles, rem = merge_live_tick_into_candles(candles, ltp=253.0, vol_delta=80.0, interval_sec=sec, now_ts=105.1)
    assert len(candles) == 2
    assert candles[0].close == 255.0  # previous candle finalized
    assert candles[1].open == 253.0
    assert candles[1].close == 253.0
    assert candles[1].volume == 80.0


# ── 3. Multi-Density Zoom, Compression & Viewport ────────────────────────────

def test_compress_candles_preserves_ohlcv_extremes():
    raw_candles = [
        Candle(timestamp=str(i), open=100.0 + i, high=105.0 + i, low=95.0 + i, close=102.0 + i, volume=100.0)
        for i in range(100)
    ]
    # Compress 100 bars down to 10 bars
    comp = compress_candles(raw_candles, target_bars=10)
    assert len(comp) == 10

    # First group covers raw_candles[0:10]
    assert comp[0].open == raw_candles[0].open
    assert comp[0].high == max(c.high for c in raw_candles[:10])
    assert comp[0].low == min(c.low for c in raw_candles[:10])
    assert comp[0].close == raw_candles[9].close
    assert comp[0].volume == sum(c.volume for c in raw_candles[:10])

    # Global high and low across all compressed bars must match the raw series
    assert max(c.high for c in comp) == max(c.high for c in raw_candles)
    assert min(c.low for c in comp) == min(c.low for c in raw_candles)


def test_compute_viewport_and_step_zoom():
    # 200 total bars in 60-col plot width
    # 1. Default comfortable view
    vp = compute_viewport(n_total=200, plot_w=60, zoom_bars=None)
    assert vp.span == 30
    assert vp.step == 2
    assert vp.compress_to == 0
    assert vp.pan == 0

    # 2. Dense view (span between 30 and 60)
    vp_dense = compute_viewport(n_total=200, plot_w=60, zoom_bars=50)
    assert vp_dense.span == 50
    assert vp_dense.step == 1
    assert vp_dense.compress_to == 0

    # 3. Zoomed out past width (span 120 > 60) -> compression activated
    vp_comp = compute_viewport(n_total=200, plot_w=60, zoom_bars=120)
    assert vp_comp.span == 120
    assert vp_comp.compress_to == 60

    # 4. Fit All full series
    vp_fit = compute_viewport(n_total=200, plot_w=60, fit_all=True)
    assert vp_fit.span == 200
    assert vp_fit.compress_to == 60

    # 5. step_zoom function
    z_in = step_zoom(cur_bars=40, n_total=200, direction=-1)
    assert z_in < 40
    z_out = step_zoom(cur_bars=40, n_total=200, direction=1)
    assert z_out > 40


# ── 4. Chart Rendering: 2D Crosshair, Fit All & Metadata ─────────────────────

def test_candlestick_fit_all_and_crosshair_meta():
    candles = [
        Candle(timestamp=f"10:{i:02d}", open=100.0 + (i % 7), high=108.0 + (i % 7), low=96.0 + (i % 7), close=104.0 + (i % 7), volume=500.0)
        for i in range(250)
    ]
    # Render with fit_all=True on an 80-column terminal
    out = render_candlestick_chart(
        candles,
        width=80,
        total_height=24,
        symbol="RELIANCE",
        interval="5s",
        fit_all=True,
        crosshair_idx=12,
        crosshair_price=105.50,
        live_ltp=104.25,
        bar_countdown_sec=3.8,
    )
    plain = out.plain
    assert "RELIANCE" in plain
    assert "FIT ALL" in plain
    assert "⏱ 03.8s" in plain
    assert "┼" in plain  # 2D crosshair intersection
    assert "◀104.25" in plain  # Live LTP tag

    # Verify _chart_meta is attached for interactive hit testing
    meta = getattr(out, "_chart_meta", None)
    assert meta is not None
    assert meta["kind"] == "candle"
    assert meta["n_total"] == 250
    assert meta["compressed"] is True
    assert meta["plot_w"] > 0


def test_braille_line_chart_features_and_crosshair():
    prices = [100.0 + i * 0.5 for i in range(80)]
    vols = [1000.0 + i * 20 for i in range(80)]
    out = render_chart(
        prices,
        volumes=vols,
        width=75,
        total_height=20,
        symbol="TCS",
        interval="1s",
        crosshair_idx=40,
        live_ltp=139.5,
        bar_countdown_sec=0.8,
    )
    plain = out.plain
    assert "TCS" in plain
    assert "139.50" in plain
    assert "┼" in plain
    assert "⏱ 00.8s" in plain
    meta = getattr(out, "_chart_meta", None)
    assert meta is not None
    assert meta["kind"] == "line"
    assert meta["n_total"] == 80


# ── 5. InteractiveChartCanvas Hit-Testing ─────────────────────────────────────

def test_interactive_chart_canvas_locate():
    canvas = InteractiveChartCanvas()
    candles = [
        Candle(timestamp=f"{i}", open=100.0, high=110.0, low=90.0, close=105.0, volume=100)
        for i in range(20)
    ]
    txt = render_candlestick_chart(candles, width=80, total_height=20, symbol="TEST")
    canvas.set_chart(txt)

    meta = canvas.meta
    assert meta is not None
    plot_x0 = meta["plot_x0"]
    grid_row0 = meta["grid_row0"]
    grid_rows = meta["grid_rows"]

    # Click in center of grid
    idx, price = canvas.locate(plot_x0 + 6, grid_row0 + grid_rows // 2)
    assert idx is not None
    assert price is not None
    assert 90.0 <= price <= 110.0


# ── 6. HistoryScreen Modal Real-Time Ticking & Interaction ───────────────────

def test_history_screen_realtime_ticking_and_hotkeys(monkeypatch):
    class DummyClient:
        paper = True
        customer_id = "1"
        access_token = "tok"
        api_key = "key"

        def historical(self, exch, scrip, iv):
            return [
                {"tradeDate": f"09:{i:02d}", "open": 200.0, "high": 205.0, "low": 198.0, "close": 202.0, "volume": 1000}
                for i in range(30)
            ]

    class TestApp(App):
        def __init__(self):
            super().__init__()
            self.client = DummyClient()
            self.quotes = QuoteStore()

    async def run():
        app = TestApp()
        item = {"tradingSymbol": "ONGC", "exchange": "NC", "scripCode": 2475}

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            screen = HistoryScreen(item, initial_interval="5second", initial_mode="candle")
            app.push_screen(screen)
            await pilot.pause(0.2)

            # 1. Canvas mounted & loaded
            canvas = screen.query_one("#chart-out", InteractiveChartCanvas)
            assert canvas is not None
            assert screen.query_one("#hist").row_count == 30

            # 2. Live tick arrival updates candle in place
            app.quotes.update("NC2475", {"ltp": 215.0, "tickVol": 500})
            await pilot.pause(0.1)
            assert screen._candles[-1].close == 215.0

            # 3. Test 'k' mode toggle (Candle <-> Line)
            await pilot.press("k")
            await pilot.pause(0.1)
            assert screen.mode == "line"
            await pilot.press("k")
            await pilot.pause(0.1)
            assert screen.mode == "candle"

            # 4. Test 'a' Fit All toggle
            await pilot.press("a")
            await pilot.pause(0.1)
            assert screen.fit_all is True
            await pilot.press("a")
            await pilot.pause(0.1)
            assert screen.fit_all is False

            # 5. Test 't' Table drawer toggle
            assert screen.table_visible is False
            await pilot.press("t")
            await pilot.pause(0.1)
            assert screen.table_visible is True
            await pilot.press("t")
            await pilot.pause(0.1)
            assert screen.table_visible is False

            # 6. Test 'z' Zen mode toggle
            assert screen.zen_mode is False
            await pilot.press("z")
            await pilot.pause(0.1)
            assert screen.zen_mode is True
            await pilot.press("z")
            await pilot.pause(0.1)
            assert screen.zen_mode is False

            # 7. Test Crosshair Left / Right / Snap Live
            await pilot.press("left")
            await pilot.pause(0.1)
            assert screen.crosshair_idx is not None
            await pilot.press("end")
            await pilot.pause(0.1)
            assert screen.crosshair_idx is None

            # 8. Test Quick Buy 'b' opens OrderTicket prefilled with price
            from sktui.screens.modals import OrderTicket
            screen.crosshair_price = 212.50
            await pilot.press("b")
            await pilot.pause(0.1)
            assert len(app.screen_stack) == 3
            ticket = app.screen_stack[-1]
            assert isinstance(ticket, OrderTicket)
            assert ticket.info["side"] == "B"
            assert ticket.info["price"] == "212.50"
            await pilot.press("escape")
            await pilot.pause(0.1)
            assert len(app.screen_stack) == 2

            # 9. Escape dismisses HistoryScreen
            await pilot.press("escape")
            await pilot.pause(0.1)
            assert len(app.screen_stack) == 1

    asyncio.run(run())


# ── 7. SymbolFocusPanel Live Tape & Interactive Actions ──────────────────────

def test_symbol_focus_panel_live_tape_and_actions():
    store = QuoteStore()
    item = {"tradingSymbol": "SBIN", "exchange": "NC", "scripCode": 3045}
    feed_key = "NC3045"

    t0 = time.time()
    for i in range(25):
        store.update(feed_key, {"ltp": 800.0 + i, "tickVol": 100}, wall_ts=t0 + i * 5)

    panel = SymbolFocusPanel()
    panel.update_context(
        item=item,
        quote={"ltp": 824.0, "open": 800.0, "high": 825.0, "low": 795.0, "close": 820.0},
        quotes=store,
        width=120,
    )
    # 1. Candles retrieved from store
    candles = panel.live_candles()
    assert len(candles) > 0
    assert candles[-1].close == 824.0

    # 2. Build chart text at uncapped dimensions (e.g. 110x28)
    chart_txt = panel.build_chart_text(width=110, height=28)
    assert "SBIN" in chart_txt.plain
    assert "5s" in chart_txt.plain

    # 3. Test TF cycle
    panel.action_chart_tf(1)
    assert panel.chart_iv == "15second"

    # 4. Test Mode cycle
    panel.action_chart_mode()
    assert panel.chart_mode == "line"
    panel.action_chart_mode()
    assert panel.chart_mode == "candle"

    # 5. Test Zoom and Fit All
    panel.action_chart_zoom(1)
    assert panel.zoom_bars is not None
    panel.action_chart_fit()
    assert panel.fit_all is True
    panel.action_chart_fit()
    assert panel.fit_all is False


# ── 8. Telemetry & Execution Audit Symbol Resolution ─────────────────────────

def test_telemetry_symbol_resolution():
    from sktui.utils import resolve_symbol

    # 1. Built-in scrip lookup by code number
    assert resolve_symbol(2885) == "RELIANCE"
    assert resolve_symbol("2885") == "RELIANCE"
    assert resolve_symbol("NC2885") == "RELIANCE"
    assert resolve_symbol({"scripCode": 2885, "exchange": "NC"}) == "RELIANCE"
    assert resolve_symbol(1594) == "INFY"
    assert resolve_symbol(11536) == "TCS"
    assert resolve_symbol(3045) == "SBIN"

    # 2. Watchlist custom resolution
    custom_watch = [{"scripCode": 9999, "tradingSymbol": "CUSTOMCO"}]
    assert resolve_symbol(9999, watch=custom_watch) == "CUSTOMCO"
    assert resolve_symbol({"scripCode": 9999}, watch=custom_watch) == "CUSTOMCO"

    # 3. Existing trading symbol string preserved
    assert resolve_symbol("TATAMOTORS") == "TATAMOTORS"


def test_main_screen_telemetry_logs_symbol_instead_of_scrip():
    from textual.widgets import RichLog
    from sktui.app import SKApp
    from sktui.screens.main import MainScreen

    class FakeClient:
        paper = True
        customer_id = "1"
        access_token = "tok"
        api_key = "key"

        def orders(self):
            return []
        def positions(self):
            return []
        def holdings(self):
            return []
        def funds(self, exch="NC"):
            return [{"exchange": "NC", "marginUsed": 0.0, "payIn": 100000.0, "totalFund": 100000.0}]

    async def run():
        app = SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            app.client = FakeClient()
            app.switch_screen(MainScreen())
            await pilot.pause(0.4)
            main = app.screen

            # Feed tick with only numeric scripCode 2885 (Reliance)
            main.on_ws({"status": 100, "data": {"exchangeCode": "NC", "scripCode": 2885, "ltp": 2980.50}})
            await pilot.pause(0.1)

            log_widget = main.query_one("#status-log", RichLog)
            log_lines = [line.text for line in log_widget.lines]
            full_text = "\n".join(log_lines)

            # Must contain RELIANCE and formatted price, NOT raw '2885 @'
            assert "RELIANCE" in full_text
            assert "2,980.50" in full_text
            assert "Tick: 2885 @" not in full_text

    asyncio.run(run())


def test_paper_history_accurate_pnb_pricing():
    from sktui.api.paper_trading import generate_paper_history
    from sktui.api.client import Client

    # 1. PNB NC 10666 default without explicit base_price
    rows_nc = generate_paper_history("NC", 10666, "5minute")
    assert len(rows_nc) > 0
    close_nc = float(rows_nc[-1]["close"])
    assert 100.0 <= close_nc <= 150.0
    assert abs(close_nc - 1605.0) > 1000.0

    # 2. PNB BC 532461 default without explicit base_price
    rows_bc = generate_paper_history("BC", 532461, "5minute")
    assert len(rows_bc) > 0
    close_bc = float(rows_bc[-1]["close"])
    assert 100.0 <= close_bc <= 150.0
    assert abs(close_bc - 1605.0) > 1000.0

    # 3. Explicit base_price passed through Client.historical
    client = Client("test_key", "test_tok", "test_cust", paper=True)
    rows_client = client.historical("NC", 10666, "5minute", base_price=123.50)
    assert len(rows_client) > 0
    close_client = float(rows_client[-1]["close"])
    assert 115.0 <= close_client <= 135.0


def test_history_screen_pnb_accurate_chart():
    from sktui.app import SKApp
    from sktui.screens.modals import HistoryScreen

    async def run():
        app = SKApp(paper=True)
        app.enable_feed = False
        pnb_item = {
            "tradingSymbol": "PNB",
            "scripCode": 10666,
            "exchange": "NC",
            "lastTradedPrice": 123.50,
        }
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            screen = HistoryScreen(pnb_item, initial_interval="5minute")
            await app.push_screen(screen)
            await pilot.pause(0.5)

            # Candles must be populated and anchored around 123.50, not 1605.0
            assert len(screen._candles) > 0
            latest_close = screen._closes[-1]
            assert 100.0 <= latest_close <= 150.0
            assert abs(latest_close - 1605.0) > 1000.0

    asyncio.run(run())


def test_to_yahoo_ticker_mapping():
    from sktui.services.market_data import to_yahoo_ticker

    assert to_yahoo_ticker("PNB", "NC") == "PNB.NS"
    assert to_yahoo_ticker("RELIANCE", "BC") == "RELIANCE.BO"
    assert to_yahoo_ticker("NIFTY50", "NC") == "^NSEI"
    assert to_yahoo_ticker("BANKNIFTY", "NF") == "^NSEBANK"
    assert to_yahoo_ticker("NIFTY24OCTFUT", "NF") == "^NSEI"
    assert to_yahoo_ticker("RELIANCEOCTFUT", "NF") == "RELIANCE.NS"


def test_market_data_cache_roundtrip(tmp_path, monkeypatch):
    import json
    import sktui.services.market_data as md

    # Redirect DATA to tmp_path
    monkeypatch.setattr(md, "DATA", tmp_path)
    cache_file = tmp_path / "cache_candles_TEST_NS_5m.json"
    dummy_payload = {
        "rows": [
            {"tradeDate": "2026-11-02", "tradeTime": "09:15:00", "timestamp": 1730500000.0,
             "open": 100.0, "high": 105.0, "low": 98.0, "close": 102.5, "volume": 50000.0}
        ],
        "meta": {"ltp": 102.5, "previousClose": 100.0, "high": 105.0, "low": 98.0, "volume": 50000.0}
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(dummy_payload, f)

    rows, meta = md.fetch_real_history("TEST", "NC", "5minute")
    assert len(rows) == 1
    assert rows[0]["close"] == 102.5
    assert meta["ltp"] == 102.5


def test_history_screen_timeframe_switching_and_live_ticks():
    from sktui.app import SKApp
    from sktui.screens.modals import HistoryScreen

    async def run():
        app = SKApp(paper=True)
        app.enable_feed = False
        item = {
            "tradingSymbol": "RELIANCE",
            "scripCode": 2885,
            "exchange": "NC",
            "lastTradedPrice": 2980.0,
        }
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            screen = HistoryScreen(item, initial_interval="5minute")
            await app.push_screen(screen)
            await pilot.pause(0.2)

            assert screen.current_iv == "5minute"
            assert len(screen._candles) > 0

            # Switch timeframe to 1minute
            screen.set_interval_val("1minute")
            await pilot.pause(0.2)
            assert screen.current_iv == "1minute"

            # Emit a live tick for RELIANCE
            feed_key = "NC2885"
            screen._on_live_tick(feed_key, {"ltp": 2995.0}, 2995.0, 150.0)
            await pilot.pause(0.1)

            # Active forming bar must reflect the live tick price
            assert screen._closes[-1] == 2995.0
            assert screen._candles[-1].close == 2995.0

    asyncio.run(run())


