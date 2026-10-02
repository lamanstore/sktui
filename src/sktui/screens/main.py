"""Main dashboard screen view and navigation sidebar for SKTUI."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    DataTable, Footer, Header, Input, RichLog, Static, TabbedContent, TabPane,
)

from sktui import api
from sktui.config import (
    C_AMBER, C_CYAN, C_GREEN, C_MUTED, C_PANEL, C_RED, C_SUBTLE, C_TEXT,
    SESSION_FILE, WATCH_FILE,
)
from sktui.screens.login import LoginScreen
from sktui.screens.modals import (
    Confirm, DetailScreen, HelpScreen, HistoryScreen, OrderTicket, ProductsScreen,
    QuoteScreen, RiskScreen, SymbolSearch, SystemStatusScreen, WhatIfScreen,
)
from sktui.utils import (
    fill_table, fmt, get, human, is_open_order, norm_expiry, order_summary,
    read_json, scrip_label, sign_style, write_private,
)

_NAV_SECTIONS = [
    ("MARKET",   [
        ("\u2b21 Watchlist",   "[1]"),
        ("\u2b21 Orders",      "[2]"),
        ("\u2b21 Positions",   "[3]"),
        ("\u2b21 Holdings",    "[4]"),
        ("\u2b21 Funds",       "[5]"),
        ("\u2b21 Activity",    "[6]"),
    ]),
    ("TRADE",    [
        ("\u25b2 Buy",         "[b]"),
        ("\u25bc Sell",        "[s]"),
        ("\u270e Modify",      "[m]"),
        ("\u2717 Cancel",      "[x]"),
        ("\u2717\u2717 Cancel All", "[X]"),
    ]),
    ("TOOLS",    [
        ("\U0001f4c8 Chart",   "[c]"),
        ("\u2b21 Quote",       "[?]"),
        ("\u2295 Add Sym",     "[a]"),
        ("\u2296 Rem Sym",     "[Del]"),
        ("\u21bb Refresh",     "[r]"),
        ("\u2b22 Products",    "[p]"),
        ("\u25a4 Feed Log",    "[d]"),
    ]),
    ("SAFETY",   [
        ("\u2b21 What-If",     "/whatif"),
        ("\u2b21 Risk",        "/risk"),
        ("\u2b21 Status",      "/status"),
        ("\u26a0 Kill",        "/kill"),
        ("F1 Help",            "F1"),
    ]),
]


class NavSidebar(Static):
    """Left navigation sidebar with grouped command labels."""

    def compose(self) -> ComposeResult:
        for section, items in _NAV_SECTIONS:
            yield Static(section, classes="nav-section-header")
            is_safety = section == "SAFETY"
            for label, key in items:
                cls = "nav-item nav-safety" if is_safety else "nav-item"
                yield Static(f"  {label}  {key}", classes=cls)


# ── Main data columns ──────────────────────────────────────────────────────────
WATCH_COLS = [
    ("sym",   "  Symbol"),  ("exch",  "Exch"),
    ("ltp",   "       LTP"), ("chg",  "    Chg \u20b9"),
    ("pct",   "   Chg%"),   ("bid",   "       Bid"),
    ("ask",   "       Ask"), ("open",  "      Open"),
    ("high",  "      High"), ("low",   "       Low"),
    ("close", "     Close"), ("vol",   "     Volume"),
    ("oi",    "          OI"),
]
TICK_MAP = {
    "ltp":   "ltp",       "chg":  "rsChange",
    "pct":   "perChange", "bid":  "bidPrice",
    "ask":   "offPrice",  "open": "open",
    "high":  "high",      "low":  "low",
    "close": "close",     "vol":  "qty",
    "oi":    "currentOI",
}
ORDER_COLS = [
    ("orderId",       "Order ID"),    ("exchange",      "Exch"),
    ("tradingSymbol", "Symbol"),      ("buySell",       "Side"),
    ("orderQty",      "Qty"),         ("execQty",       "Filled"),
    ("orderPrice",    "Price"),       ("execPrice",     "Avg Fill"),
    ("orderStatus",   "Status"),      ("requestStatus", "Req Status"),
    ("priceType",     "Type"),        ("lastModTime",   "Last Update"),
    ("errorMsg",      "Error"),
]
POS_COLS = [
    ("tradingSymbol", "Symbol"),   ("exchange",   "Exch"),
    ("productType",   "Product"),  ("buyQty",     "Buy Q"),
    ("buyRate",       "Buy Avg"),  ("sellQty",    "Sell Q"),
    ("sellRate",      "Sell Avg"), ("netQty",     "Net Qty"),
    ("avgPrice",      "Avg Price"), ("bpl",       "Booked P/L"),
    ("mtm",           "MTM P/L"),
]
HOLD_COLS = [
    ("tradingSymbol", "Symbol"),     ("exchange",      "Exch"),
    ("aval",          "Available"),  ("cncqty",        "CNC Qty"),
    ("invstQty",      "Invst Qty"),  ("holdPrice",     "Hold Price"),
    ("dp",            "DP"),         ("pledge",        "Pledge"),
    ("mf",            "MF"),         ("receivable",    "Receivable"),
    ("tradingAllowed","Tradable"),
]
COLS = {"orders": ORDER_COLS, "positions": POS_COLS, "holdings": HOLD_COLS}


class MainScreen(Screen):
    BINDINGS = [
        Binding("b",           "trade('B')",     "Buy"),
        Binding("s",           "trade('S')",     "Sell"),
        Binding("a",           "add",            "Add"),
        Binding("delete",      "remove",         "Del"),
        Binding("m",           "modify",         "Modify"),
        Binding("x",           "cancel_order",   "Cancel"),
        Binding("X",           "cancel_all",     "Cancel all", show=False),
        Binding("r",           "refresh_all",    "Refresh"),
        Binding("c",           "chart",          "Chart"),
        Binding("i",           "detail",         "Info"),
        Binding("question_mark","quote",          "Quote",  show=False),
        Binding("p",           "products",       "Market"),
        Binding("d",           "toggle_log",     "Feed",   show=False),
        Binding("1",           "tab('watch')",   show=False),
        Binding("2",           "tab('orders')",  show=False),
        Binding("3",           "tab('positions')", show=False),
        Binding("4",           "tab('holdings')", show=False),
        Binding("5",           "tab('funds')",   show=False),
        Binding("6",           "tab('activity')", show=False),
        Binding("ctrl+l",      "logout",         "Logout"),
        Binding("q",           "app.quit",       "Quit"),
        Binding("slash",       "focus_cmd",      "Command", show=False),
        Binding("f1",          "help",           "Help",   show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.watch: list[dict]            = read_json(WATCH_FILE, [])
        self.data:  dict[str, list[dict]] = {}
        self.feed:  api.Feed | None       = None
        self._ack_pending                 = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="account")
        with Horizontal(id="main-body"):
            with Vertical(id="sidebar"):
                yield NavSidebar(id="nav")
            with Vertical(id="content-area"):
                with TabbedContent(id="tabs", initial="watch"):
                    with TabPane("\u2b21 Watchlist  [1]",  id="watch"):
                        yield DataTable(id="t-watch",     cursor_type="row")
                    with TabPane("\u2b21 Orders  [2]",     id="orders"):
                        yield DataTable(id="t-orders",    cursor_type="row")
                    with TabPane("\u2b21 Positions  [3]",  id="positions"):
                        yield DataTable(id="t-positions", cursor_type="row")
                    with TabPane("\u2b21 Holdings  [4]",   id="holdings"):
                        yield DataTable(id="t-holdings",  cursor_type="row")
                    with TabPane("\u2b21 Funds  [5]",      id="funds"):
                        yield DataTable(id="t-funds",     cursor_type="row")
                    with TabPane("\u2b21 Activity  [6]",   id="activity"):
                        yield RichLog(id="activity-log", max_lines=1000,
                                      wrap=True, markup=False)
                yield RichLog(id="feedlog", max_lines=300,
                              wrap=True, markup=False)
                with Horizontal(id="cmd-bar"):
                    yield Static("  /  ", id="cmd-prefix")
                    yield Input(
                        placeholder="command  \u2014  /whatif, /risk, /status, /help, /buy, /sell \u2026",
                        id="cmd-input")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        c = self.app.client

        # Account bar
        t = Text()
        if c.paper:
            t.append(" \u26a0  PAPER ", style=f"bold black on {C_AMBER}")
        else:
            t.append(" \u2b22  LIVE ",  style=f"bold white on {C_RED}")
        t.append(f"  {c.full_name or c.login_id}", style=f"bold {C_TEXT}")
        t.append(f"  \u00b7  CID: {c.customer_id}", style=C_MUTED)
        t.append("  \u00b7  ", style=C_MUTED)
        for exch in c.exchanges:
            t.append(f" {exch} ", style=f"bold {C_CYAN} on {C_PANEL}")
            t.append(" ")
        t.append("  \u00b7  Risk: ", style=C_MUTED)
        t.append("NORMAL", style=f"bold {C_GREEN}")
        t.append("  \u00b7  / = cmd   F1 = help", style=C_SUBTLE)
        self.query_one("#account", Static).update(t)

        self.query_one("#feedlog").display = False

        w = self.query_one("#t-watch", DataTable)
        for key, label in WATCH_COLS:
            w.add_column(label, key=key)
        for item in self.watch:
            self.add_watch_row(item)

        self.refresh_all_data()
        self.set_interval(20, self.refresh_active)

        if getattr(self.app, "enable_feed", True):
            self.feed = api.Feed(
                c.access_token, c.api_key, c.cid,
                lambda: [self.feed_key(w) for w in self.watch],
                lambda m: self.post(self.on_ws, m),
                lambda s, err: self.post(self.status, s, err),
            )
            self.feed.start()

    def on_unmount(self) -> None:
        if self.feed:
            self.feed.stop()

    def status(self, msg: str, error: bool = False) -> None:
        prefix = "  \u2717  " if error else "  \u00b7  "
        style  = f"bold {C_RED}" if error else C_MUTED
        now    = datetime.now().strftime("%H:%M:%S")
        self.query_one("#status", Static).update(
            Text(f"{prefix}{msg}", style=style)
            + Text(f"  [{now}]", style=C_SUBTLE))

    def log_activity(self, line: str) -> None:
        ts  = datetime.now().strftime("%H:%M:%S")
        log = self.query_one("#activity-log", RichLog)
        t   = Text()
        t.append(f"  {ts}  ", style=C_SUBTLE)
        t.append(line)
        log.write(t)

    def post(self, fn, *a) -> None:
        try:
            self.app.call_from_thread(fn, *a)
        except Exception:
            pass

    @staticmethod
    def feed_key(item: dict) -> str:
        return f"{item['exchange']}{item['scripCode']}"

    def add_watch_row(self, item: dict) -> None:
        t = self.query_one("#t-watch", DataTable)
        k = self.feed_key(item)
        if k not in t.rows:
            t.add_row(scrip_label(item), item["exchange"],
                      "\u2014", *["\u2014"] * (len(WATCH_COLS) - 3), key=k)

    def active_tab(self) -> str:
        return self.query_one("#tabs", TabbedContent).active

    def selected(self, tab: str) -> dict | None:
        t = self.query_one(f"#t-{tab}", DataTable)
        if t.row_count == 0:
            return None
        if tab == "watch":
            try:
                key = t.coordinate_to_cell_key(t.cursor_coordinate).row_key.value
            except Exception:
                return None
            return next((w for w in self.watch if self.feed_key(w) == key), None)
        rows = self.data.get(tab, [])
        return rows[t.cursor_row] if t.cursor_row < len(rows) else None

    def action_focus_cmd(self) -> None:
        self.query_one("#cmd-input", Input).focus()

    @on(Input.Submitted, "#cmd-input")
    def _cmd_submitted(self, e: Input.Submitted) -> None:
        raw = e.value.strip()
        if not raw:
            return
        cmd = raw.split()[0].lower()
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        e.input.value = ""
        self._dispatch_slash(cmd)

    def _dispatch_slash(self, cmd: str) -> None:
        dispatch = {
            "/dashboard":  lambda: self.action_tab("watch"),
            "/watchlist":  lambda: self.action_tab("watch"),
            "/orders":     lambda: self.action_tab("orders"),
            "/positions":  lambda: self.action_tab("positions"),
            "/holdings":   lambda: self.action_tab("holdings"),
            "/funds":      lambda: self.action_tab("funds"),
            "/activity":   lambda: self.action_tab("activity"),
            "/buy":        lambda: self.action_trade("B"),
            "/sell":       lambda: self.action_trade("S"),
            "/cancel":     self.action_cancel_order,
            "/modify":     self.action_modify,
            "/chart":      self.action_chart,
            "/quote":      self.action_quote,
            "/products":   self.action_products,
            "/status":     self.action_system_status,
            "/whatif":     self.action_whatif,
            "/risk":       self.action_show_risk,
            "/feed":       self.action_toggle_log,
            "/refresh":    self.action_refresh_all,
            "/logout":     self.action_logout,
            "/help":       self.action_help,
            "/kill":       self.action_kill,
        }
        fn = dispatch.get(cmd)
        if fn:
            fn()
        else:
            self.status(
                f"Unknown command: {cmd}  \u2014  F1 for full command reference",
                True)

    def refresh_all_data(self) -> None:
        for tab in ("orders", "positions", "holdings", "funds"):
            self.load(tab)

    def refresh_active(self) -> None:
        tab = self.active_tab()
        if tab in ("orders", "positions", "holdings", "funds"):
            self.load(tab)

    @work(thread=True)
    def load(self, tab: str) -> None:
        c = self.app.client
        try:
            if tab == "funds":
                groups: list[str] = []
                if any(e in c.exchanges for e in ("NC", "BC", "NF")):
                    groups.append("NC")
                groups += [g for g in ("MX", "RN") if g in c.exchanges]
                groups = groups or ["NC"]
                rows: list[dict] = []
                for g in groups:
                    for r in c.funds(g):
                        for k, v in r.items():
                            if not isinstance(v, (dict, list)):
                                rows.append({"segment": g, "field": human(k), "value": v})
            else:
                rows = {
                    "orders":    c.orders,
                    "positions": c.positions,
                    "holdings":  c.holdings,
                }[tab]()
            self.post(self.show_rows, tab, rows)
        except Exception as e:
            self.post(self.status, f"{tab}: {e}", True)

    def show_rows(self, tab: str, rows: list[dict]) -> None:
        self.data[tab] = rows
        fill_table(
            self.query_one(f"#t-{tab}", DataTable), rows,
            COLS.get(tab) or [
                ("segment", "Segment"), ("field", "Field"), ("value", "Value")])
        n = len(rows)
        self.status(
            f"{tab.capitalize()}: {n} record{'s' if n != 1 else ''}"
            if n else f"{tab.capitalize()}: no records found")

    def action_tab(self, tab: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab

    def action_refresh_all(self) -> None:
        self.refresh_all_data()
        self.status("All data refreshed")

    def action_toggle_log(self) -> None:
        log         = self.query_one("#feedlog")
        log.display = not log.display

    def action_products(self) -> None:
        self.app.push_screen(ProductsScreen())

    def action_system_status(self) -> None:
        self.app.push_screen(SystemStatusScreen())

    def action_show_risk(self) -> None:
        self.app.push_screen(RiskScreen())

    def action_whatif(self) -> None:
        item = self.selected("watch") if self.active_tab() == "watch" else None
        self.app.push_screen(WhatIfScreen(item))

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen())

    def action_kill(self) -> None:
        self.log_activity(
            "\u26a0  KILL SWITCH \u2014 automated order entry would be blocked")
        if self.app.client.paper:
            self.status(
                "\u26a0 KILL \u2014 automation disabled  (already in paper mode)")
        else:
            self.status(
                "\u26a0 KILL \u2014 block automated orders  "
                "(server-side enforcement required in production)", True)

    def action_add(self) -> None:
        def done(item: dict | None) -> None:
            if not item or item.get("scripCode") is None:
                return
            if any(self.feed_key(w) == self.feed_key(item) for w in self.watch):
                return
            self.watch.append(item)
            write_private(WATCH_FILE, self.watch)
            self.add_watch_row(item)
            if self.feed:
                self.feed.subscribe(self.feed_key(item))
        self.app.push_screen(SymbolSearch(), done)

    def action_remove(self) -> None:
        item = self.selected("watch") if self.active_tab() == "watch" else None
        if not item:
            return
        k          = self.feed_key(item)
        self.watch = [w for w in self.watch if self.feed_key(w) != k]
        write_private(WATCH_FILE, self.watch)
        self.query_one("#t-watch", DataTable).remove_row(k)
        if self.feed:
            self.feed.unsubscribe(k)

    def action_trade(self, side: str) -> None:
        item = self.selected("watch") if self.active_tab() == "watch" else None
        if not item:
            self.status(
                "Select a symbol in the Watchlist first  "
                "(press 'a' to add one, or /watchlist)", True)
            return
        info = dict(item, side=side)
        ltp  = getattr(self.app, "raw_ticks", {}).get(
            self.feed_key(item), {}).get("ltp")
        if ltp:
            info["price"] = ltp
        self.open_ticket(info, "NEW")

    @staticmethod
    def row_to_info(r: dict) -> dict:
        t    = str(get(r, "buySell", "transactionType", default="B")).upper()[:1]
        prod = get(r, "productType", default="")
        opt  = str(get(r, "optionType", default="")).upper()
        return {
            "orderId":       get(r, "orderId"),
            "scripCode":     get(r, "scripCode",    default=None),
            "tradingSymbol": get(r, "tradingSymbol"),
            "exchange":      get(r, "exchange",      default="NC"),
            "side":          "S" if t == "S" else "B",
            "quantity":      get(r, "orderQty", "quantity", default=1),
            "executedQty":   get(r, "execQty",       default=0),
            "price":         get(r, "orderPrice", "price", default="0"),
            "triggerPrice":  get(r, "trigPrice", "triggerPrice",
                                 "orderTriggerPrice", default="0"),
            "rmsCode":       get(r, "rmsCode",        default="ANY"),
            "afterHour":     get(r, "afterHour",      default="N"),
            "validity":      get(r, "goodTill",       default="GFD"),
            "productType":   prod,
            "instType":      get(r, "instrumentType", default=""),
            "optionType":    opt,
            "strike":        get(r, "strikePrice",    default=0),
            "expiry":        norm_expiry(get(r, "expiryDate", default="")),
        }

    def action_modify(self) -> None:
        row = self.selected("orders") if self.active_tab() == "orders" else None
        if row:
            self.open_ticket(self.row_to_info(row), "MODIFY")

    def open_ticket(self, info: dict, mode: str) -> None:
        def done(res: Any) -> None:
            if res:
                params, warns = res
                self.confirm(
                    f"Confirm {params['requestType']}",
                    order_summary(params, warns),
                    lambda: self.send(params))
        self.app.push_screen(OrderTicket(info, mode), done)

    def confirm(self, title: str, body: Text, action: Any) -> None:
        self.app.push_screen(
            Confirm(title, body, self.app.client.paper),
            lambda ok: action() if ok else None)

    def action_cancel_order(self) -> None:
        row = self.selected("orders") if self.active_tab() == "orders" else None
        if not row:
            return
        oid = get(row, "orderId")
        if not is_open_order(row):
            self.status(
                f"Order {oid} is already "
                f"{get(row, 'orderStatus')} \u2014 nothing to cancel", True)
            return
        body = Text()
        body.append(f"Order ID: {oid}\n", style=f"bold {C_CYAN}")
        body.append(f"{get(row, 'tradingSymbol')}  ({get(row, 'exchange')})\n")
        body.append(
            f"{get(row, 'buySell')}  {get(row, 'orderQty')} units"
            f"  @  \u20b9{get(row, 'orderPrice')}")
        self.confirm("Cancel Order", body, lambda: self.cancel_ids([str(oid)]))

    def action_cancel_all(self) -> None:
        ids = [str(get(r, "orderId"))
               for r in self.data.get("orders", []) if is_open_order(r)]
        if not ids:
            self.status("No open orders to cancel", True)
            return
        body = Text()
        body.append(f"{len(ids)} open order(s) will be cancelled:\n",
                    style=f"bold {C_AMBER}")
        body.append(", ".join(ids), style=C_MUTED)
        self.confirm("Cancel ALL Open Orders", body,
                     lambda: self.cancel_ids(ids))

    @work(thread=True)
    def cancel_ids(self, ids: list[str]) -> None:
        for oid in ids:
            try:
                r = self.app.client.cancel_by_id(oid)
                self.post(self.log_activity, f"\u2713  CANCEL {oid}: {r}")
            except Exception as e:
                self.post(self.log_activity, f"\u2717  CANCEL {oid} FAILED: {e}")
                self.post(self.app.notify, f"Cancel {oid}: {e}", "error")
        self.post(self.load, "orders")

    @work(thread=True)
    def send(self, p: dict) -> None:
        side = "\u25b2 BUY" if p.get("transactionType") == "B" else "\u25bc SELL"
        desc = f"{side} {p['quantity']} \u00d7 {p['tradingSymbol']}"
        try:
            r = self.app.client.submit(p)
            self.post(self.log_activity,
                      f"\u2713  {p['requestType']}  {desc}  \u2192  {r}")
            self.post(self.app.notify,
                      f"\u2713 {p['requestType']} submitted: {str(r)[:120]}")
        except Exception as e:
            self.post(self.log_activity,
                      f"\u2717  {p['requestType']}  {desc}  FAILED: {e}")
            self.post(self.app.notify, f"Order failed: {e}", "error")
        self.post(self.load, "orders")

    def action_chart(self) -> None:
        item = self.selected("watch") if self.active_tab() == "watch" else None
        if not item and self.active_tab() == "orders":
            row  = self.selected("orders")
            item = self.row_to_info(row) if row else None
        if item:
            self.app.push_screen(HistoryScreen(item))
        else:
            self.status("Select a watchlist symbol or an order first", True)

    def action_detail(self) -> None:
        row = self.selected("orders") if self.active_tab() == "orders" else None
        if row:
            self.app.push_screen(DetailScreen(row))

    def action_quote(self) -> None:
        item = self.selected("watch") if self.active_tab() == "watch" else None
        if item:
            self.app.push_screen(QuoteScreen(self.feed_key(item), scrip_label(item)))

    def action_logout(self) -> None:
        if self.feed:
            self.feed.stop()
        self.app.client.logout()
        SESSION_FILE.unlink(missing_ok=True)
        self.app.client = None
        self.app.switch_screen(LoginScreen())

    def on_ws(self, msg: dict) -> None:
        log = self.query_one("#feedlog", RichLog)
        if log.display:
            log.write(json.dumps(msg)[:500])
        data = msg.get("data") if isinstance(msg, dict) else None
        if isinstance(data, dict):
            if "AckState" in data or "SharekhanOrderID" in data:
                return self.on_ack(data)
            if "scripCode" in data and "ltp" in data:
                return self.on_tick(data)

    def on_ack(self, d: dict) -> None:
        state    = d.get("AckState", "")
        side_str = d.get("BuySellString", "")
        qty      = d.get("TradeQty") or d.get("OrderQty", "")
        sym      = d.get("TradingSymbol", "")
        price    = (d.get("TradePrice") if d.get("TradeQty")
                    else d.get("OrderPrice", ""))
        oid      = d.get("SharekhanOrderID", "")
        err      = d.get("ErrorMessage") or ""
        bad      = any(x in str(state).lower()
                       for x in ("reject", "fail", "error"))
        icon     = "\u2717" if bad else "\u2713"
        line     = (f"{icon}  {state}  {side_str} {qty} "
                    f"\u00d7 {sym} @ \u20b9{price}  (#{oid})")
        if err:
            line += f"  \u2014 {err}"
        self.log_activity(line)
        self.app.notify(line, severity="error" if bad else "information")
        if not self._ack_pending:
            self._ack_pending = True
            self.set_timer(0.8, self._ack_refresh)

    def _ack_refresh(self) -> None:
        self._ack_pending = False
        self.load("orders")
        self.load("positions")

    def on_tick(self, d: dict) -> None:
        key   = f"{d.get('exchangeCode')}{d.get('scripCode')}"
        table = self.query_one("#t-watch", DataTable)
        if key not in table.rows:
            return
        raw  = self.app.raw_ticks
        prev = raw.get(key, {}).get("ltp")
        raw.setdefault(key, {}).update(d)
        for col, src in TICK_MAP.items():
            if src not in d:
                continue
            v = d[src]
            if col == "ltp" and prev is not None:
                if v > prev:
                    table.update_cell(key, col,
                        Text(f"\u25b2 {fmt(v)}", style=f"bold {C_GREEN}"))
                elif v < prev:
                    table.update_cell(key, col,
                        Text(f"\u25bc {fmt(v)}", style=f"bold {C_RED}"))
                else:
                    table.update_cell(key, col, Text(fmt(v), style=C_MUTED))
            elif col in ("chg", "pct"):
                table.update_cell(key, col, Text(fmt(v), style=sign_style(v)))
            else:
                table.update_cell(key, col, Text(fmt(v)))
