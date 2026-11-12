"""Test verification for user watchlist with TATAMOTORS and elimination of hardcoded fake data."""
from __future__ import annotations

import pytest
from textual.widgets import DataTable, Static

from sktui.screens.main import MainScreen
from sktui.screens.modals import HistoryScreen
from sktui.services.market import MarketService
from sktui.state.quote_store import QuoteStore
from sktui.state.watchlist_store import WatchlistStore
from sktui.ui.widgets.symbol_focus import SymbolFocusPanel
from sktui.utils import resolve_code, resolve_symbol


def test_resolve_code_and_symbol():
    """Verify reciprocal resolution between symbol and code."""
    # TATAMOTORS -> 3456
    code = resolve_code("TATAMOTORS", "NC")
    assert code == 3456
    # 3456 -> TATAMOTORS
    sym = resolve_symbol(3456, "NC")
    assert sym == "TATAMOTORS"


def test_initial_quote_no_fake_synthetic_tape():
    """Verify initial_quote does NOT inject 900 fake random-walk ticks into QuoteStore."""
    qs = QuoteStore()
    ws = WatchlistStore()
    ms = MarketService(qs, ws)

    item = {
        "exchange": "NC",
        "scripCode": 3456,
        "tradingSymbol": "TATAMOTORS",
        "companyName": "Tata Motors Ltd",
    }
    q = ms.initial_quote(item, allow_network=False)
    assert q["tradingSymbol"] == "TATAMOTORS"
    assert q["scripCode"] == 3456

    # Verify no synthetic ticks were seeded into tick_tape
    key = "NC3456"
    assert not qs.has_live_ticks(key)
    # Candles should be empty until real ticks arrive
    candles = qs.get_candles(key, interval_sec=5)
    assert len(candles) == 0


def test_symbol_focus_panel_empty_ticks_state():
    """Verify SymbolFocusPanel renders clean awaiting status when no ticks exist."""
    panel = SymbolFocusPanel()
    item = {
        "exchange": "NC",
        "scripCode": 3456,
        "tradingSymbol": "TATAMOTORS",
        "companyName": "Tata Motors Ltd",
    }
    qs = QuoteStore()
    panel.update_context(item=item, quote={}, quotes=qs, width=100)

    # build_chart_text should display awaiting feed text without crashing or fabricating fake wave
    chart_text = panel.build_chart_text(width=80, height=12)
    plain = chart_text.plain
    assert "Awaiting Live Market Feed" in plain or "Awaiting Market Feed" in plain
    assert "TATAMOTORS" in plain
    assert "Sharekhan" in plain


def test_main_screen_tatamotors_selection_not_hijacked(monkeypatch, tmp_path):
    """Verify that background table updates (orders, scanner) do NOT hijack selected_symbol away from TATAMOTORS."""
    import asyncio
    import json
    from sktui.app import SKApp

    # Write a test watchlist with only TATAMOTORS
    watch_file = tmp_path / "watchlist.json"
    watch_file.write_text(json.dumps([
        {
            "exchange": "NC",
            "scripCode": 3456,
            "tradingSymbol": "TATAMOTORS",
            "companyName": "Tata Motors Ltd",
            "lotSize": 1,
            "tickSize": 0.05,
        }
    ]))

    import sktui.app as app_mod
    monkeypatch.setattr(app_mod, "WATCH_FILE", watch_file)

    async def run():
        app = SKApp(paper=True)
        async with app.run_test() as pilot:
            # Switch to MainScreen
            scr = MainScreen()
            await app.push_screen(scr)
            await pilot.pause()

            # TATAMOTORS must be the selected symbol
            assert scr.selected_symbol is not None
            assert scr.selected_symbol.get("tradingSymbol") == "TATAMOTORS"

            # Background orders update with a DIFFERENT symbol (e.g. RELIANCE)
            different_orders = [
                {
                    "orderId": "999001",
                    "tradingSymbol": "RELIANCE",
                    "exchange": "NC",
                    "scripCode": 2885,
                    "buySell": "B",
                    "orderQty": 10,
                    "orderPrice": "1300.00",
                    "orderStatus": "CONFIRMED",
                }
            ]
            scr.show_rows("orders", different_orders)
            await pilot.pause()

            # The selected symbol in MainScreen MUST REMAIN TATAMOTORS
            assert scr.selected_symbol.get("tradingSymbol") == "TATAMOTORS"

            # Background scanner update with another symbol
            t_scan = scr.query_one("#t-scanner", DataTable)
            t_scan.clear()
            t_scan.add_row("GAINER", "INFY", "+2.50%", "▲ Bullish")
            await pilot.pause()

            # The selected symbol in MainScreen MUST STILL REMAIN TATAMOTORS
            assert scr.selected_symbol.get("tradingSymbol") == "TATAMOTORS"

            # Focus panel must reflect TATAMOTORS
            focus_panel = scr.query_one("#symbol-focus-panel", SymbolFocusPanel)
            assert focus_panel.item.get("tradingSymbol") == "TATAMOTORS"

    asyncio.run(run())


def test_client_quote_parsing_and_market_service_integration():
    """Verify Client.quote queries broker REST endpoint and feeds accurate LTP to QuoteStore."""
    from unittest.mock import MagicMock
    from sktui.api.client import Client

    client = Client("key", "token123", "cust1", paper=False)
    # Mock _req to return 1-minute historical data ending at 446.05
    client._req = MagicMock(return_value=[
        {"time": "09:15:00", "open": 444.0, "high": 445.0, "low": 443.5, "close": 444.5, "volume": 12000},
        {"time": "09:16:00", "open": 444.5, "high": 446.5, "low": 444.0, "close": 446.05, "volume": 15000},
    ])

    quote = client.quote("NC", 3456)
    assert quote is not None
    assert quote["scripCode"] == 3456
    assert quote["ltp"] == 446.05
    assert quote["close"] == 444.5
    assert quote["rsChange"] == 1.55
    assert quote["perChange"] == 0.35
    assert quote["source"] == "sharekhan_rest"

    # Verify MarketService with client prioritizes this quote
    qs = QuoteStore()
    ws = WatchlistStore()
    ms = MarketService(qs, ws, client=client)
    item = {"exchange": "NC", "scripCode": 3456, "tradingSymbol": "TATAMOTORS"}
    q = ms.initial_quote(item, allow_network=True)
    assert q["ltp"] == 446.05
    assert q["tradingSymbol"] == "TATAMOTORS"
    assert qs.ltp("NC3456") == 446.05


def test_watchlist_store_feed_key_resilient():
    """Verify WatchlistStore.feed_key resolves correctly even without scripCode in item."""
    item_with_code = {"exchange": "NC", "scripCode": 3456, "tradingSymbol": "TATAMOTORS"}
    item_no_code = {"exchange": "NC", "tradingSymbol": "TATAMOTORS"}
    assert WatchlistStore.feed_key(item_with_code) == "NC3456"
    assert WatchlistStore.feed_key(item_no_code) == "NC3456"


def test_symbol_focus_panel_renders_true_market_price():
    """Verify SymbolFocusPanel displays ₹446.05 and does not display old corrupt values."""
    panel = SymbolFocusPanel()
    item = {
        "exchange": "NC",
        "scripCode": 3456,
        "tradingSymbol": "TATAMOTORS",
        "companyName": "Tata Motors Ltd",
    }
    qs = QuoteStore()
    quote = {
        "ltp": 446.05,
        "rsChange": 2.85,
        "perChange": 0.64,
        "open": 443.20,
        "high": 452.90,
        "low": 443.20,
        "close": 443.20,
        "bidPrice": 446.00,
        "offPrice": 446.10,
        "qty": 5500000,
    }
    panel.update_context(item=item, quote=quote, quotes=qs, width=80)
    chart_text = panel.build_chart_text(width=80, height=12)
    plain = chart_text.plain
    assert "₹446.05" in plain
    assert "299" not in plain


def test_zero_third_party_scrapers_and_no_299_overwrite(monkeypatch):
    """Verify Yahoo and Google scrapers are eliminated and never overwrite TATAMOTORS with 299."""
    from unittest.mock import MagicMock
    import sktui.services.market_data as md

    # 1. Verification of third-party scraper removal
    assert md.fetch_google_quote("TATAMOTORS", "NC") is None
    assert md.fetch_indices_quotes() == {}
    real_rows, meta = md.fetch_real_history("TATAMOTORS", "NC")
    assert real_rows == []
    assert meta is None

    # 2. Broker quote for TATAMOTORS returns genuine ₹446.05
    mock_client = MagicMock()
    mock_client.access_token = "valid_jwt"
    mock_client.quote.return_value = {
        "scripCode": 3456,
        "exchangeCode": "NC",
        "ltp": 446.05,
        "close": 443.20,
        "rsChange": 2.85,
        "perChange": 0.64,
        "open": 443.20,
        "high": 452.90,
        "low": 443.20,
        "qty": 5500000,
        "source": "sharekhan_rest",
    }

    # fetch_real_quote delegates directly to Sharekhan client
    quote = md.fetch_real_quote("TATAMOTORS", "NC", scrip_code=3456, client=mock_client)
    assert quote is not None
    assert quote["ltp"] == 446.05
    assert quote["source"] == "sharekhan_rest"
    assert quote["ltp"] != 299.0


