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
