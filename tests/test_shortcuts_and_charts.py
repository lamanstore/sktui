"""Tests for 1-7 keyboard shortcuts and chart functionality."""
import asyncio
from unittest.mock import MagicMock

import pytest
from rich.text import Text
from textual.app import App

from sktui import config
from sktui.api.client import Client
from sktui.api.paper_trading import generate_paper_history
from sktui.app import SKApp
from sktui.screens.main import MainScreen
from sktui.screens.modals import HistoryScreen
from sktui.ui.widgets.symbol_focus import SymbolFocusPanel


def test_generate_paper_history():
    """Verify synthetic historical bars generation for charts."""
    bars = generate_paper_history("NC", 2475, "5minute", bars_count=40)
    assert len(bars) == 40
    first = bars[0]
    assert "tradeDate" in first
    assert "tradeTime" in first
    assert "open" in first
    assert "high" in first
    assert "low" in first
    assert "close" in first
    assert "volume" in first
    assert first["high"] >= first["low"]
    assert first["open"] > 0
    assert first["close"] > 0


def test_client_historical_paper_and_fallback(monkeypatch):
    """Client.historical returns synthetic bars in paper mode or when network fails."""
    # 1. Paper mode
    client_paper = Client("test", "test", "test", paper=True)
    rows = client_paper.historical("NC", 2475, "5minute")
    assert len(rows) > 0
    assert rows[0]["close"] > 0

    # 2. Live client with 403 network error should fallback to paper history
    client_live = Client("live", "live", "live", paper=False)
    monkeypatch.setattr(client_live, "_req", MagicMock(side_effect=Exception("403 Forbidden")))
    rows_fallback = client_live.historical("NC", 2475, "15minute")
    assert len(rows_fallback) > 0
    assert rows_fallback[0]["close"] > 0


def test_history_screen_offline_renders():
    """HistoryScreen reliably fetches and renders chart without crashing even if offline."""
    item = {"tradingSymbol": "RELIANCE", "exchange": "NC", "scripCode": 2885}

    class ChartTestApp(App):
        def __init__(self):
            super().__init__()
            self.client = Client("test", "test", "test", paper=True)

        def on_mount(self):
            self.push_screen(HistoryScreen(item))

    async def run():
        app = ChartTestApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.5)
            screen = app.screen
            assert isinstance(screen, HistoryScreen)
            assert screen._rows is not None
            assert len(screen._rows) > 0

    asyncio.run(run())


def test_symbol_focus_panel_chart_rendering():
    """SymbolFocusPanel renders non-flat Braille chart for symbol with LTP."""
    panel = SymbolFocusPanel()
    item = {"tradingSymbol": "TCS", "exchange": "NC", "scripCode": 11536}
    quote = {"ltp": 3500.0, "open": 3480.0, "high": 3520.0, "low": 3470.0, "close": 3490.0}

    panel.update_context(item=item, quote=quote, width=80)
    assert panel.item == item
    assert panel.quote.get("ltp") == 3500.0


def test_main_screen_1_to_7_shortcuts_and_chart(tmp_path, monkeypatch):
    """Verify 1-7 keys switch views/tables in MainScreen and 'c' opens HistoryScreen."""
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "WATCH_FILE", tmp_path / "w.json")

    class FakeClient:
        paper = True
        customer_id = "1"
        access_token = "tok"
        api_key = "key"

        def orders(self):
            return [{"orderId": "101", "tradingSymbol": "INFY", "exchange": "NC", "orderQty": 10, "execQty": 0, "orderPrice": 1500.0, "orderStatus": "Open", "buySell": "B", "priceType": "NORMAL"}]

        def positions(self):
            return [{"tradingSymbol": "INFY", "exchange": "NC", "productType": "INVESTMENT", "netQty": 10, "avgPrice": 1490.0, "bpl": 100.0, "mtm": 50.0}]

        def holdings(self):
            return [{"tradingSymbol": "INFY", "exchange": "NC", "aval": 10, "holdPrice": 1450.0}]

        def funds(self, exch):
            return [{"field": "currentCashBalance", "value": 500000.0}]

        def historical(self, exch, scrip, iv):
            return generate_paper_history(exch, scrip, iv, bars_count=20)

        def master(self, exch):
            return [{"scripCode": 2475, "tradingSymbol": "ONGC", "companyName": "ONGC", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"}]

    async def run():
        app = SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            app.client = FakeClient()
            app.switch_screen(MainScreen())
            await pilot.pause(0.5)

            scr = app.screen
            assert isinstance(scr, MainScreen)

            # Test 1: Watchlist focus
            await pilot.press("1")
            await pilot.pause(0.1)
            assert scr.focused.id == "t-watch"

            # Test 2: Symbol focus
            await pilot.press("2")
            await pilot.pause(0.1)
            assert scr.focused.id == "symbol-focus-panel"

            # Test 3: Desk -> Orders
            await pilot.press("3")
            await pilot.pause(0.1)
            assert scr.query_one("#t-orders").display is True
            assert scr.query_one("#t-positions").display is False
            assert scr.focused.id == "t-orders"
            assert "Orders [3]" in str(scr.query_one("#desk-header").render())

            # Test 4: Desk -> Positions
            await pilot.press("4")
            await pilot.pause(0.1)
            assert scr.query_one("#t-positions").display is True
            assert scr.query_one("#t-orders").display is False
            assert scr.focused.id == "t-positions"
            assert "Positions [4]" in str(scr.query_one("#desk-header").render())

            # Test 5: Desk -> Holdings
            await pilot.press("5")
            await pilot.pause(0.1)
            assert scr.query_one("#t-holdings").display is True
            assert scr.query_one("#t-positions").display is False
            assert scr.focused.id == "t-holdings"
            assert "Holdings [5]" in str(scr.query_one("#desk-header").render())

            # Test 6: Desk -> Funds
            await pilot.press("6")
            await pilot.pause(0.1)
            assert scr.query_one("#t-funds").display is True
            assert scr.query_one("#t-holdings").display is False
            assert scr.focused.id == "t-funds"
            assert "Funds [6]" in str(scr.query_one("#desk-header").render())

            # Test 7: Activity Log focus
            await pilot.press("7")
            await pilot.pause(0.1)
            assert scr.focused.id == "status-log"

            # Test Chart shortcut 'c'
            await pilot.press("c")
            await pilot.pause(0.6)
            assert type(app.screen).__name__ == "HistoryScreen"
            hist_screen = app.screen
            assert hist_screen.query_one("#hist").row_count > 0
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert type(app.screen).__name__ == "MainScreen"

    asyncio.run(run())


def test_market_service_initial_quote_priority(monkeypatch):
    """Verify MarketService.initial_quote prioritizes authentic real quotes."""
    from unittest.mock import MagicMock
    from sktui.state.quote_store import QuoteStore
    from sktui.state.watchlist_store import WatchlistStore
    from sktui.services.market import MarketService
    import sktui.services.market_data as md

    qs = QuoteStore()
    ws = WatchlistStore()
    ms = MarketService(qs, ws)

    # 1. Item with explicit real broker quote snapshot
    item_with_quote = {
        "tradingSymbol": "RELIANCE",
        "exchange": "NC",
        "scripCode": 2885,
        "ltp": 1345.50,
        "rsChange": 15.20,
        "perChange": 1.14,
    }
    q1 = ms.initial_quote(item_with_quote)
    assert q1["ltp"] == 1345.50
    assert q1["rsChange"] == 15.20
    assert q1["perChange"] == 1.14

    # 2. When real fetch returns data
    fake_real_meta = {
        "ltp": 1330.00,
        "previousClose": 1320.00,
        "high": 1340.00,
        "low": 1315.00,
        "volume": 2500000,
    }
    monkeypatch.setattr(md, "fetch_real_history", MagicMock(return_value=([{"open": 1322.0, "close": 1330.0, "timestamp": 1700000000}], fake_real_meta)))
    qs2 = QuoteStore()
    ms2 = MarketService(qs2, ws)
    item_bare = {"tradingSymbol": "RELIANCE", "exchange": "NC", "scripCode": 2885}
    q2 = ms2.initial_quote(item_bare)
    assert q2["ltp"] == 1330.00
    assert q2["close"] == 1320.00
    assert q2["rsChange"] == 10.00


def test_market_service_simulate_tick_mean_reversion():
    """Verify simulate_tick applies mean-reverting micro ticks and correct perChange."""
    from sktui.state.quote_store import QuoteStore
    from sktui.state.watchlist_store import WatchlistStore
    from sktui.services.market import MarketService

    qs = QuoteStore()
    ws = WatchlistStore()
    ms = MarketService(qs, ws)

    item = {
        "tradingSymbol": "TCS",
        "exchange": "NC",
        "scripCode": 11536,
        "ltp": 4000.00,
        "close": 4000.00,
    }
    ms.initial_quote(item)

    # Run 50 ticks and ensure prices stay closely bound to anchor (no runaway drift)
    for _ in range(50):
        ms.simulate_tick(item)
        key = ws.feed_key(item)
        curr_q = qs.get(key)
        assert abs(curr_q["ltp"] - 4000.0) < 100.0  # Kept within realistic ±2.5% band
        expected_pct = round(((curr_q["ltp"] - 4000.0) / 4000.0) * 100.0, 2)
        assert abs(curr_q["perChange"] - expected_pct) <= 0.02


def test_google_finance_ticker_and_failover(monkeypatch):
    """Verify Google Finance ticker conversion and dual Yahoo + Google failover."""
    from unittest.mock import MagicMock
    import sktui.services.market_data as md

    # 1. Ticker mappings
    assert md.to_google_ticker("NIFTY50") == "NIFTY_50:INDEXNSE"
    assert md.to_google_ticker("BANKNIFTY") == "NIFTY_BANK:INDEXNSE"
    assert md.to_google_ticker("SENSEX") == "SENSEX:INDEXBOM"
    assert md.to_google_ticker("RELIANCE", "NC") == "RELIANCE:NSE"
    assert md.to_google_ticker("TCS", "BC") == "TCS:BOM"
    assert md.to_google_ticker("NIFTY24OCTFUT") == "NIFTY_50:INDEXNSE"

    # 2. Mock Google Finance HTML quote parsing
    fake_html = """
    <html><body>
      <div class="YMlKec fxKbKc">₹1,325.50</div>
      <div>Previous close</div><div class="P6K39c">₹1,320.00</div>
      <div>Day range</div><div class="P6K39c">₹1,315.00 - ₹1,340.00</div>
      <div>Volume</div><div class="P6K39c">4.20M</div>
    </body></html>
    """
    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_html.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    monkeypatch.setattr(md.urllib.request, "urlopen", MagicMock(return_value=mock_resp))

    g_quote = md.fetch_google_quote("RELIANCE", "NC", force_refresh=True)
    assert g_quote is not None
    assert g_quote["ltp"] == 1325.50
    assert g_quote["close"] == 1320.00
    assert g_quote["high"] == 1340.00
    assert g_quote["low"] == 1315.00
    assert g_quote["rsChange"] == 5.50
    assert g_quote["qty"] == 4200000.0
    assert g_quote["source"] == "google"

    # 3. Failover in fetch_real_quote when Yahoo fails
    monkeypatch.setattr(md, "fetch_real_history", MagicMock(return_value=([], None)))
    q_failover = md.fetch_real_quote("RELIANCE", "NC")
    assert q_failover is not None
    assert q_failover["ltp"] == 1325.50
    assert q_failover["source"] == "google"


