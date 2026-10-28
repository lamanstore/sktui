"""Tests for new modular services: MarketService, OrderService, WatchlistService, StatusService."""
import pytest
from textual.widgets import Static

from sktui.services.market import MarketService
from sktui.services.order_service import OrderService
from sktui.services.status_service import StatusService
from sktui.services.watchlist import WatchlistService
from sktui.state.quote_store import QuoteStore
from sktui.state.watchlist_store import WatchlistStore
from sktui.ui.widgets.dashboard_cards import update_dashboard, update_pnl_strip
from sktui.screens.main import MainScreen


def test_quote_store_and_market_service():
    quotes = QuoteStore()
    w_store = WatchlistStore()
    market = MarketService(quotes, w_store)

    received_updates = []
    market.on_tick_update = lambda key, tick, prev, new: received_updates.append((key, prev, new))

    # Test initial quote
    init_q = market.initial_quote({"scripCode": 2475, "tradingSymbol": "ONGC", "exchange": "NC"})
    assert init_q["ltp"] > 0
    assert quotes.ltp("NC2475") == init_q["ltp"]

    # Test WS tick routing
    ws_msg = {
        "status": 100,
        "message": "feed",
        "data": {
            "scripCode": 2475,
            "exchangeCode": "NC",
            "ltp": 95.5,
            "rsChange": 1.2,
            "perChange": 1.25,
        },
    }
    market.handle_ws(ws_msg)
    assert quotes.ltp("NC2475") == 95.5
    assert len(received_updates) == 1
    assert received_updates[0][0] == "NC2475"
    assert received_updates[0][2] == 95.5


def test_watchlist_service(tmp_path):
    w_file = tmp_path / "watch.json"
    store = WatchlistStore(w_file)
    svc = WatchlistService(store)

    item = {"scripCode": 9999, "tradingSymbol": "TEST", "exchange": "NC"}
    added = []
    svc.add(item, on_success=lambda it, sym: added.append(sym))
    assert len(added) == 1
    assert svc.contains(item)

    # Duplicate add
    dup = []
    svc.add(item, on_duplicate=lambda sym: dup.append(sym))
    assert len(dup) == 1

    # Remove
    removed = []
    svc.remove(item, on_success=lambda sym: removed.append(sym))
    assert len(removed) == 1
    assert not svc.contains(item)


def test_order_service_row_to_info():
    row = {
        "orderId": "12345",
        "scripCode": 2475,
        "tradingSymbol": "ONGC",
        "exchange": "NC",
        "buySell": "B",
        "orderQty": 50,
        "orderPrice": "100.50",
        "productType": "CNC",
    }
    info = OrderService.row_to_info(row)
    assert info["orderId"] == "12345"
    assert info["side"] == "B"
    assert info["quantity"] == 50
    assert info["tradingSymbol"] == "ONGC"


def test_status_service():
    class DummyClient:
        paper = True
        full_name = "Trader Joe"
        login_id = "TJ001"
        customer_id = "123456"
        exchanges = ["NC", "BC"]

    svc = StatusService(DummyClient())
    acc = svc.render_account_bar("1.2.3.4")
    assert "PAPER" in acc.plain
    assert "Trader Joe" in acc.plain
    assert "1.2.3.4" in acc.plain

    idx = svc.render_indices_bar({"NIFTY50": {"ltp": 25000.0, "rsChange": 50.0, "perChange": 0.2}})
    assert "NIFTY 50" in idx.plain


def test_dashboard_cards_update():
    class MockWidget:
        def __init__(self):
            self.content = None
        def update(self, content):
            self.content = content

    s_summary = MockWidget()
    s_orders = MockWidget()
    s_watch = MockWidget()

    orders = [
        {"orderId": "1", "tradingSymbol": "ONGC", "buySell": "B", "orderQty": 10, "orderPrice": 100, "orderStatus": "Fully Executed"}
    ]
    positions = [
        {"tradingSymbol": "ONGC", "bpl": "500.00", "mtm": "250.00"}
    ]
    holdings = [{"tradingSymbol": "INFY", "aval": 100}]
    watch = [{"scripCode": 2475, "tradingSymbol": "ONGC", "exchange": "NC"}]
    raw_ticks = {"NC2475": {"ltp": 105.0, "perChange": 1.5}}
    tick_history = {"NC2475": [100.0, 102.0, 105.0]}

    update_dashboard(
        dash_summary=s_summary,
        dash_orders=s_orders,
        dash_watch=s_watch,
        orders=orders,
        positions=positions,
        holdings=holdings,
        watch=watch,
        raw_ticks=raw_ticks,
        tick_history=tick_history,
        sparkline_fn=lambda h, width=12: "~~~",
    )
    assert "ACCOUNT & PORTFOLIO OVERVIEW" in s_summary.content.plain
    assert "Orders breakdown" in s_orders.content.plain
    assert "Live Market Snapshot" in s_watch.content.plain
