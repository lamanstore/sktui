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
            await pilot.press("2")
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
            assert len(app.screen.shown) == 1
            app.screen.query_one("#results").focus()
            await pilot.press("enter")
            await pilot.pause(0.3)
            main = app.screen
            assert type(main).__name__ == "MainScreen" and len(main.watch) == 1
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
