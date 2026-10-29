import asyncio

from sktui import app as sk
from sktui.api import Client


class FakeClient(Client):
    def __init__(self):
        super().__init__("k", "tok", "272616", "LOGIN1", exchanges=["NC", "BC", "NF", "MX"], paper=True)
        self.sent = []

    def orders(self):
        return [{"orderId": "9", "scripCode": 2475, "tradingSymbol": "ONGC", "exchange": "NC",
                 "buySell": "B", "orderQty": 1, "execQty": 0, "orderPrice": "92.50",
                 "orderStatus": "Pending", "rmsCode": "SKSIMNSE1"}]

    def positions(self):
        return []

    def holdings(self):
        return [{"tradingSymbol": "IOC", "exchange": "NSE", "aval": "2"}]

    def funds(self, exchange):
        return [{"customerId": 1, "currentCashBalance": 1000000.0}]

    def master(self, exchange):
        return [{"scripCode": 2475, "tradingSymbol": "ONGC", "companyName": "ONGC LTD", "instType": "EQ",
                 "tickSize": 0.05, "lotSize": 1}]

    def historical(self, e, c, i):
        return [{"close": x, "tradeDate": "18/01/2021", "tradeTime": "09:07:24"} for x in (1, 3, 2, 5)]

    def order_history(self, e, o):
        return [{"orderStatus": "Pending"}]

    def order_trades(self, e, o):
        return []


def test_full_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(sk, "DATA", tmp_path)
    monkeypatch.setattr(sk, "WATCH_FILE", tmp_path / "w.json")

    async def run():
        app = sk.SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            app.client = FakeClient()
            app.switch_screen(sk.MainScreen())
            await pilot.pause(0.6)
            scr = app.screen
            assert scr.query_one("#t-orders").row_count == 1
            assert scr.query_one("#t-funds").row_count >= 1
            # watchlist + tick
            item = sk.normalize_scrip("NC", app.client.master("NC")[0])
            scr.watch.append(item)
            scr.add_watch_row(item)
            scr.on_ws({"status": 100, "message": "feed",
                       "data": {"exchangeCode": "NC", "scripCode": 2475, "ltp": 92.5, "rsChange": 0.4,
                                "perChange": 0.4, "bidPrice": 92.45, "offPrice": 92.55, "qty": 1000}})
            assert app.raw_ticks["NC2475"]["ltp"] == 92.5
            # buy ticket -> confirm
            await pilot.press("b")
            await pilot.pause()
            assert type(app.screen).__name__ == "OrderTicket"
            app.screen.query_one("#review").press()
            await pilot.pause()
            assert type(app.screen).__name__ == "Confirm"
            await pilot.press("n")
            await pilot.pause()
            # orders tab: info, cancel confirm
            await pilot.press("3")
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            assert type(app.screen).__name__ == "Confirm"
            await pilot.press("n")
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            assert type(app.screen).__name__ == "OrderTicket"
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert type(app.screen).__name__ == "ProductsScreen"
    asyncio.run(run())


def test_search_chart_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(sk, "DATA", tmp_path)
    monkeypatch.setattr(sk, "WATCH_FILE", tmp_path / "w.json")

    async def run():
        app = sk.SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            app.client = FakeClient()
            app.switch_screen(sk.MainScreen())
            await pilot.pause(0.5)
            await pilot.press("a")
            await pilot.pause(1.0)
            assert type(app.screen).__name__ == "SymbolSearch"
            app.screen.query_one("#q").value = "ongc"
            await pilot.pause(0.6)
            assert len(app.screen.shown) >= 1
            app.screen.query_one("#results").focus()
            await pilot.press("enter")
            await pilot.pause(0.3)
            main = app.screen
            assert type(main).__name__ == "MainScreen" and any(w.get("tradingSymbol") == "ONGC" for w in main.watch)
            await pilot.press("c")
            await pilot.pause(0.6)
            assert type(app.screen).__name__ == "HistoryScreen"
            assert app.screen.query_one("#hist").row_count == 4
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            assert type(app.screen).__name__ == "QuoteScreen"
    asyncio.run(run())


def test_feed_protocol():
    import json
    from sktui.api import Feed

    sent, got = [], []

    class WS:
        def send(self, m):
            sent.append(json.loads(m))

    f = Feed("tok", "key", 272616, lambda: ["NC2885", "NF60530"], got.append, lambda s, e: None)
    ws = WS()
    f._on_msg(ws, json.dumps({"status": 100, "message": "connect", "data": "Connected abc"}))
    assert sent[0] == {"action": "subscribe", "key": ["feed", "ack"], "value": [""]}
    f._on_msg(ws, json.dumps({"status": 100, "message": "subscribe", "data": "successFEED,successACK"}))
    assert sent[1] == {"action": "ack", "key": [""], "value": [272616]}
    assert sent[2] == {"action": "feed", "key": ["full"], "value": ["NC2885"]}
    assert sent[3]["value"] == ["NF60530"]
    assert len(got) == 2


def test_responsive_resizing_and_modals(tmp_path, monkeypatch):
    monkeypatch.setattr(sk, "DATA", tmp_path)
    monkeypatch.setattr(sk, "WATCH_FILE", tmp_path / "w.json")

    async def run():
        app = sk.SKApp(paper=True)
        app.enable_feed = False
        # Test compact terminal (80, 24)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.client = FakeClient()
            app.switch_screen(sk.MainScreen())
            await pilot.pause(0.5)
            main = app.screen
            assert "-sm" in main.classes or "-xs" in main.classes
            assert "-short" in main.classes

            # Toggle focus mode
            await pilot.press("f")
            await pilot.pause(0.2)
            assert "focus-mode" in main.classes
            await pilot.press("f")
            await pilot.pause(0.2)
            assert "focus-mode" not in main.classes

            from rich.text import Text
            from textual import events
            from sktui.screens.modals import Confirm, FocusModal, HistoryScreen

            # Focus modal at 80x24
            item = {"scripCode": 2475, "tradingSymbol": "ONGC", "exchange": "NC", "price": 92.5}
            app.push_screen(FocusModal(item))
            await pilot.pause(0.3)
            assert type(app.screen).__name__ == "FocusModal"
            await pilot.press("escape")
            await pilot.pause(0.2)

            # Confirm modal at 80x24
            app.push_screen(Confirm("Cancel Order", Text("Are you sure?"), paper=True))
            await pilot.pause(0.3)
            assert type(app.screen).__name__ == "Confirm"
            await pilot.press("n")
            await pilot.pause(0.2)

            # HistoryScreen at 80x24
            app.push_screen(HistoryScreen(item))
            await pilot.pause(0.3)
            # Trigger dynamic resize to larger display (160, 48)
            await pilot.resize_terminal(160, 48)
            await pilot.pause(0.3)
            assert "-lg" in app.screen.classes or "-xl" in app.screen.classes
            await pilot.press("escape")
            await pilot.pause(0.2)

    asyncio.run(run())


def test_symbol_focus_panel_and_trustworthy_indices(tmp_path, monkeypatch):
    monkeypatch.setattr(sk, "DATA", tmp_path)
    monkeypatch.setattr(sk, "WATCH_FILE", tmp_path / "w.json")

    async def run():
        app = sk.SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            app.client = FakeClient()
            app.switch_screen(sk.MainScreen())
            await pilot.pause(0.5)
            main = app.screen

            # 1. Verify SymbolFocusPanel is present
            from sktui.ui.widgets.symbol_focus import SymbolFocusPanel
            panel = main.query_one("#symbol-focus-panel", SymbolFocusPanel)
            assert panel is not None

            # 2. Verify Indices Bar shows waiting state, NOT fake hardcoded 25120.40
            idx_bar = main.query_one("#indices-bar")
            idx_text = str(idx_bar.render())
            assert "25120" not in idx_text
            assert "waiting" in idx_text or "--.--" in idx_text

            # 3. Simulate live tick for focused item
            item = {"scripCode": 2475, "tradingSymbol": "ONGC", "exchange": "NC"}
            main.watch.append(item)
            main.add_watch_row(item)
            main._update_symbol_focus(item)

            tick = {
                "exchangeCode": "NC", "scripCode": 2475,
                "ltp": 99.50, "rsChange": 2.50, "perChange": 2.58,
                "bidPrice": 99.45, "offPrice": 99.55, "qty": 50000,
            }
            main.on_ws({"status": 100, "message": "feed", "data": tick})
            await pilot.pause(0.3)

            # Focus panel should reflect the live tick
            panel_text = panel.render_content().plain
            assert "ONGC" in panel_text
            assert "99.50" in panel_text

    asyncio.run(run())
