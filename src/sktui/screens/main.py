"""Main dashboard screen view and navigation sidebar for SKTUI."""
from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Any

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    DataTable, Footer, Header, Input, Label, RichLog, Static, TabbedContent, TabPane,
)

from sktui import api
from sktui.config import (
    C_AMBER, C_CYAN, C_DIM, C_GREEN, C_MUTED, C_PANEL, C_RED, C_SUBTLE,
    C_TEXT, BUILTIN_SCRIPS,
    SESSION_FILE, WATCH_FILE,
)
from sktui.screens.login import LoginScreen
from sktui.screens.modals import (
    Confirm, DetailScreen, HelpScreen, HistoryScreen, OrderTicket, ProductsScreen,
    QuoteScreen, RiskScreen, SymbolSearch, SystemStatusScreen, WhatIfScreen,
    sparkline,
)
from sktui.utils import (
    fill_table, fmt, get, get_public_ip, human, is_open_order, norm_expiry, order_summary,
    read_json, scrip_label, sign_style, write_private,
)

# ── Navigation sidebar sections ───────────────────────────────────────────────
_NAV_SECTIONS = [
    ("── MARKET ──", [
        ("❖ Dashboard",    "[1]"),
        ("⬡ Watchlist",    "[2]"),
        ("⬡ Orders",       "[3]"),
        ("⬡ Positions",    "[4]"),
        ("⬡ Holdings",     "[5]"),
        ("⬡ Funds",        "[6]"),
        ("⬡ Activity",     "[7]"),
    ]),
    ("── TRADE ──", [
        ("▲ Buy",          "[b]"),
        ("▼ Sell",         "[s]"),
        ("✎ Modify",       "[m]"),
        ("✗ Cancel",       "[x]"),
        ("✗✗ Cancel All",  "[X]"),
    ]),
    ("── TOOLS ──", [
        ("📈 Chart",        "[c]"),
        ("⬡ Quote",        "[?]"),
        ("⊕ Add Symbol",   "[a]"),
        ("⊖ Remove Sym",   "[Del]"),
        ("↻ Refresh",      "[r]"),
        ("⬢ Products",     "[p]"),
        ("▤ Feed Log",     "[d]"),
        ("ℹ  Detail",      "[i]"),
    ]),
    ("── SAFETY ──", [
        ("⬡ What-If",      "/whatif"),
        ("⬡ Risk",         "/risk"),
        ("⬡ Status",       "/status"),
        ("⚠ Kill",         "/kill"),
        ("F1 Help",         "F1"),
    ]),
]


class MarketRadarSidebar(Static):
    """Dynamic sidebar for Market Intelligence and Sectors."""

    def compose(self) -> ComposeResult:
        yield Static("MARKET SESSION", classes="nav-section-header")
        yield Static("", id="radar-session", classes="nav-item")
        yield Static("SECTOR RADAR", classes="nav-section-header")
        yield Static("", id="radar-sectors", classes="nav-item")
        yield Static("BREADTH & TREND", classes="nav-section-header")
        yield Static("", id="radar-breadth", classes="nav-item")
        yield Static("SHORTCUTS", classes="nav-section-header")
        from rich.text import Text as RText
        shortcuts = RText()
        shortcuts.append("  [1-7]", style="bold #00e5ff")
        shortcuts.append("  Tabs\n", style="#475569")
        shortcuts.append("  [b/s]", style="bold #00e5ff")
        shortcuts.append("  Buy/Sell\n", style="#475569")
        shortcuts.append("  [a/Del]", style="bold #00e5ff")
        shortcuts.append("  Add/Rem\n", style="#475569")
        shortcuts.append("  [c/i]", style="bold #00e5ff")
        shortcuts.append("  Chart/Info\n", style="#475569")
        shortcuts.append("  [/]", style="bold #00e5ff")
        shortcuts.append("  Commands\n", style="#475569")
        shortcuts.append("  [ESC]", style="bold #00e5ff")
        shortcuts.append("  Close modal", style="#475569")
        yield Static(shortcuts, classes="nav-item")


# ── Column definitions ────────────────────────────────────────────────────────
WATCH_COLS = [
    ("sym",   " Symbol       "), ("exch",  "Exch"),
    ("ltp",   "         LTP"),   ("chg",   "    Chg ₹"),
    ("pct",   "    Chg%"),       ("bid",   "       Bid"),
    ("ask",   "       Ask"),     ("open",  "      Open"),
    ("high",  "      High"),     ("low",   "       Low"),
    ("close", "     Close"),     ("vol",   "      Vol"),
    ("oi",    "          OI"),
]

ORDER_COLS = [
    ("orderId",       " Order ID"),      ("exchange",      "Exch"),
    ("tradingSymbol", " Symbol"),        ("buySell",       "Side"),
    ("orderQty",      "   Qty"),         ("execQty",       " Filled"),
    ("orderPrice",    "    Price"),      ("execPrice",     "  Avg Fill"),
    ("orderStatus",   " Status"),        ("requestStatus", " Req Status"),
    ("priceType",     " Type"),          ("lastModTime",   " Last Update"),
    ("errorMsg",      " Error"),
]
POS_COLS = [
    ("tradingSymbol", " Symbol"),   ("exchange",   "Exch"),
    ("productType",   " Product"),  ("buyQty",     "  Buy Q"),
    ("buyRate",       "  Buy Avg"), ("sellQty",    " Sell Q"),
    ("sellRate",      " Sell Avg"), ("netQty",     "  Net Q"),
    ("avgPrice",      "  Avg Px"),  ("bpl",        "  Booked P/L"),
    ("mtm",           "  MTM P/L"),
]
HOLD_COLS = [
    ("tradingSymbol", " Symbol"),      ("exchange",       "Exch"),
    ("aval",          "  Available"),  ("cncqty",         "  CNC Qty"),
    ("invstQty",      " Invst Qty"),   ("holdPrice",      "  Hold Px"),
    ("dp",            "  DP"),         ("pledge",         "  Pledge"),
    ("mf",            "  MF"),         ("receivable",     "  Receivable"),
    ("tradingAllowed"," Tradable"),
]
COLS = {"orders": ORDER_COLS, "positions": POS_COLS, "holdings": HOLD_COLS}

DEFAULT_WATCH = [
    {"scripCode": 23481, "tradingSymbol": "ONGC", "companyName": "Oil and Natural Gas Corp Ltd", "exchange": "NC"},
    {"scripCode": 2885,  "tradingSymbol": "RELIANCE", "companyName": "Reliance Industries Ltd", "exchange": "NC"},
    {"scripCode": 11536, "tradingSymbol": "TCS", "companyName": "Tata Consultancy Services Ltd", "exchange": "NC"},
    {"scripCode": 1594,  "tradingSymbol": "INFY", "companyName": "Infosys Ltd", "exchange": "NC"},
    {"scripCode": 1333,  "tradingSymbol": "HDFCBANK", "companyName": "HDFC Bank Ltd", "exchange": "NC"},
    {"scripCode": 3045,  "tradingSymbol": "SBIN", "companyName": "State Bank of India", "exchange": "NC"},
]


class MainScreen(Screen):
    BINDINGS = [
        Binding("b",            "trade('B')",     "Buy"),
        Binding("s",            "trade('S')",     "Sell"),
        Binding("a",            "add",            "Add"),
        Binding("delete",       "remove",         "Del"),
        Binding("m",            "modify",         "Modify"),
        Binding("x",            "cancel_order",   "Cancel"),
        Binding("X",            "cancel_all",     "Cancel all", show=False),
        Binding("r",            "refresh_all",    "Refresh"),
        Binding("c",            "chart",          "Chart"),
        Binding("i",            "detail",         "Info"),
        Binding("question_mark","quote",           "Quote",  show=False),
        Binding("p",            "products",       "Market"),
        Binding("d",            "toggle_log",     "Feed",   show=False),
        Binding("1",            "tab('dashboard')", show=False),
        Binding("2",            "tab('watch')",     show=False),
        Binding("3",            "tab('orders')",    show=False),
        Binding("4",            "tab('positions')", show=False),
        Binding("5",            "tab('holdings')",  show=False),
        Binding("6",            "tab('funds')",     show=False),
        Binding("7",            "tab('activity')",  show=False),
        Binding("ctrl+l",       "logout",         "Logout"),
        Binding("q",            "app.quit",       "Quit"),
        Binding("slash",        "focus_cmd",      "Command", show=False),
        Binding("f1",           "help",           "Help",   show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        w = read_json(WATCH_FILE, [])
        self.watch: list[dict]            = w if w else DEFAULT_WATCH
        if not w:
            write_private(WATCH_FILE, self.watch)
        self.data:  dict[str, list[dict]] = {}
        self.feed:  api.Feed | None       = None
        self._ack_pending                 = False
        self._tick_history: dict[str, list[float]] = {}
        self.public_ip: str               = "Fetching…"

    # ── Layout ────────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="account")
        yield Static("", id="indices-bar")
        with Horizontal(id="main-body"):
            with Vertical(id="sidebar"):
                yield MarketRadarSidebar(id="nav")
            with Vertical(id="content-area"):
                with TabbedContent(id="tabs", initial="dashboard"):
                    with TabPane("❖ Dashboard  [1]", id="dashboard"):
                        with VerticalScroll(id="dash-container"):
                            yield Static("", id="dash-summary-strip")
                            with Horizontal(id="dash-dual-panel"):
                                with Vertical(id="dash-left-box"):
                                    yield Label("📊 Portfolio & Orders Analytics", classes="field-group-label")
                                    yield Static("", id="dash-orders-summary")
                                with Vertical(id="dash-right-box"):
                                    yield Label("⭐ Watchlist Quick Monitor", classes="field-group-label")
                                    yield Static("", id="dash-watch-summary")
                            yield Label("🔔 Live Feed & System Notifications", classes="field-group-label")
                            yield RichLog(id="dash-feed-log", max_lines=200, wrap=True, markup=False)
                    with TabPane("◈ Watchlist  [2]",  id="watch"):
                        yield DataTable(id="t-watch",     cursor_type="row")
                    with TabPane("◎ Orders  [3]",     id="orders"):
                        yield DataTable(id="t-orders",    cursor_type="row")
                    with TabPane("◉ Positions  [4]",  id="positions"):
                        yield DataTable(id="t-positions", cursor_type="row")
                    with TabPane("◈ Holdings  [5]",   id="holdings"):
                        yield DataTable(id="t-holdings",  cursor_type="row")
                    with TabPane("◈ Funds  [6]",      id="funds"):
                        yield DataTable(id="t-funds",     cursor_type="row")
                    with TabPane("◈ Activity  [7]",   id="activity"):
                        yield RichLog(id="activity-log", max_lines=1000,
                                      wrap=True, markup=False)
                yield Static("", id="pnl-strip")
                yield RichLog(id="feedlog", max_lines=300,
                              wrap=True, markup=False)
                with Horizontal(id="cmd-bar"):
                    yield Static("  /  ", id="cmd-prefix")
                    yield Input(
                        placeholder=(
                            "command  —  /dashboard, /watchlist, /buy, /sell, /add, /chart, /whatif, "
                            "/risk, /status, /help  …"
                        ),
                        id="cmd-input")
        yield Static("", id="status")
        yield Footer()

    # ── Mount ─────────────────────────────────────────────────────────────────
    def on_mount(self) -> None:
        c = self.app.client

        self._update_account_bar()
        self._update_indices_bar()
        self._fetch_public_ip()
        self.query_one("#feedlog").display = False
        self.query_one("#pnl-strip", Static).update(
            Text("  ─  P/L loading…", style=C_SUBTLE))

        # Watchlist table columns & initial rows
        w = self.query_one("#t-watch", DataTable)
        for key, label in WATCH_COLS:
            w.add_column(label, key=key)
        for item in self.watch:
            self.add_watch_row(item)

        self.refresh_all_data()
        self.set_interval(2, self.update_dashboard)
        self.set_interval(1.5, self._simulate_tick)
        self.set_interval(20, self.refresh_active)
        self.set_interval(60, self._update_indices_bar)

        if getattr(self.app, "enable_feed", True):
            self.feed = api.Feed(
                c.access_token, c.api_key, c.cid,
                lambda: [self.feed_key(w) for w in self.watch],
                lambda m: self.post(self.on_ws, m),
                lambda s, err: self.post(self.status, s, err),
            )
            self.feed.start()

    def _update_account_bar(self) -> None:
        c = self.app.client
        t = Text()
        if c.paper:
            t.append("  ⚠  PAPER ", style=f"bold black on {C_AMBER}")
        else:
            t.append("  ⬢  LIVE ",  style=f"bold white on {C_RED}")
        t.append(f"  {c.full_name or c.login_id}", style=f"bold {C_TEXT}")
        t.append(f"  ·  CID: {c.customer_id}", style=C_MUTED)
        t.append(f"  ·  IP: {self.public_ip}", style=f"bold {C_CYAN}")
        t.append("  ·  ", style=C_MUTED)
        exs = c.exchanges if c.exchanges else ["NC", "BC", "NF", "RN"]
        for exch in exs:
            t.append(f" {exch} ", style=f"bold {C_CYAN} on {C_PANEL}")
            t.append(" ")
        t.append("  ·  Risk: ", style=C_MUTED)
        t.append("NORMAL", style=f"bold {C_GREEN}")
        t.append("  ·  / = cmd   F1 = help   a = add   c = chart", style=C_SUBTLE)
        self.query_one("#account", Static).update(t)

    @work(thread=True)
    def _fetch_public_ip(self) -> None:
        ip = get_public_ip()
        self.public_ip = ip
        self.app.public_ip = ip
        self.post(self._update_ip_display, ip)

    def _update_ip_display(self, ip: str) -> None:
        try:
            self._update_account_bar()
        except Exception:
            pass

    def _update_indices_bar(self) -> None:
        """Show a live indices / market-hours bar."""
        now  = datetime.now()
        hour = now.hour + now.minute / 60
        session = "PRE-OPEN" if 9 <= hour < 9.25 else (
                  "OPEN"     if 9.25 <= hour < 15.5 else
                  "POST"     if 15.5 <= hour < 16 else "CLOSED")
        ses_clr = C_GREEN if session == "OPEN" else (
                  C_AMBER  if session in ("PRE-OPEN", "POST") else C_SUBTLE)
        
        # Pick live values for indices
        raw = getattr(self.app, "raw_ticks", {})
        nifty_q = raw.get("NIFTY50", {})
        n_ltp = nifty_q.get("ltp") or 25120.40
        n_chg = nifty_q.get("rsChange") or 84.50
        n_pct = nifty_q.get("perChange") or 0.34

        t = Text()
        t.append(f"  ◉ {session}  ", style=f"bold {ses_clr}")
        t.append("·", style=C_SUBTLE)
        t.append("  NIFTY 50 ", style=C_MUTED)
        t.append(f"{n_ltp:,.2f} ", style="bold white")
        t.append(f"({n_chg:+.2f} / {n_pct:+.2f}%)", style=sign_style(n_chg))
        t.append("  ·  ", style=C_SUBTLE)
        t.append("BANKNIFTY ", style=C_MUTED)
        t.append("52,410.80 ", style="bold white")
        t.append("(+185.20 / +0.35%)", style=f"bold {C_GREEN}")
        t.append("  ·  ", style=C_SUBTLE)
        t.append("SENSEX ", style=C_MUTED)
        t.append("82,140.10 ", style="bold white")
        t.append("(+240.10 / +0.29%)", style=f"bold {C_GREEN}")
        t.append(f"  ·  {now.strftime('%d %b %Y  %H:%M')}", style=C_SUBTLE)
        self.query_one("#indices-bar", Static).update(t)

        # Update Market Radar sidebar
        radar_session = Text()
        radar_session.append("  NSE Equity: ", style=C_MUTED)
        radar_session.append(f"{session}\n", style=f"bold {ses_clr}")
        curr_session = "OPEN" if 9 <= hour < 17 else "CLOSED"
        radar_session.append("  Currency:   ", style=C_MUTED)
        radar_session.append(f"{curr_session}\n", style=f"bold {C_GREEN if curr_session == 'OPEN' else C_SUBTLE}")
        mcx_session = "OPEN" if 9 <= hour < 23.5 else "CLOSED"
        radar_session.append("  MCX:        ", style=C_MUTED)
        radar_session.append(f"{mcx_session}", style=f"bold {C_GREEN if mcx_session == 'OPEN' else C_SUBTLE}")
        try:
            self.query_one("#radar-session", Static).update(radar_session)
        except Exception:
            pass

        radar_sectors = Text()
        radar_sectors.append("  NIFTY BANK: ", style=C_MUTED)
        radar_sectors.append("+0.35% 🟢\n", style=f"bold {C_GREEN}")
        radar_sectors.append("  NIFTY IT:   ", style=C_MUTED)
        radar_sectors.append("-0.12% 🔴\n", style=f"bold {C_RED}")
        radar_sectors.append("  NIFTY AUTO: ", style=C_MUTED)
        radar_sectors.append("+1.15% 🟢\n", style=f"bold {C_GREEN}")
        radar_sectors.append("  INDIA VIX:  ", style=C_MUTED)
        radar_sectors.append("13.42  🟢", style=f"bold {C_GREEN}")
        try:
            self.query_one("#radar-sectors", Static).update(radar_sectors)
        except Exception:
            pass

        radar_breadth = Text()
        radar_breadth.append("  Adv / Dec:  ", style=C_MUTED)
        radar_breadth.append("1420 / 890\n", style="bold white")
        radar_breadth.append("  Ratio:      ", style=C_MUTED)
        radar_breadth.append("1.60 🟢\n", style=f"bold {C_GREEN}")
        radar_breadth.append("  FII Cash:   ", style=C_MUTED)
        radar_breadth.append("+120Cr", style=f"bold {C_GREEN}")
        try:
            self.query_one("#radar-breadth", Static).update(radar_breadth)
        except Exception:
            pass

    def get_initial_quote(self, item: dict) -> dict:
        k = self.feed_key(item)
        if k in self.app.raw_ticks:
            return self.app.raw_ticks[k]

        sym = item.get("tradingSymbol", "").upper()
        base_prices = {
            "ONGC": (248.50, 2.10, 0.85, 248.45, 248.50, 246.00, 249.20, 245.80, 246.40, 4820100, 12450),
            "RELIANCE": (2980.00, -12.50, -0.42, 2979.80, 2980.00, 2990.00, 3005.00, 2972.00, 2992.50, 2150000, 85000),
            "TCS": (4250.00, 35.00, 0.83, 4249.50, 4250.00, 4220.00, 4265.00, 4215.00, 4215.00, 1200000, 45000),
            "INFY": (1890.00, 15.20, 0.81, 1889.50, 1890.00, 1875.00, 1898.00, 1870.00, 1874.80, 3500000, 62000),
            "HDFCBANK": (1650.00, 8.40, 0.51, 1649.80, 1650.00, 1642.00, 1658.00, 1640.00, 1641.60, 5800000, 110000),
            "SBIN": (825.00, -4.20, -0.51, 824.80, 825.00, 829.00, 832.00, 822.00, 829.20, 7200000, 94000),
            "TATAMOTORS": (965.00, 11.30, 1.18, 964.80, 965.00, 955.00, 970.00, 952.00, 953.70, 6100000, 82000),
            "BHARTIARTL": (1540.00, 6.80, 0.44, 1539.50, 1540.00, 1535.00, 1545.00, 1530.00, 1533.20, 2800000, 39000),
        }
        if sym in base_prices:
            p, c, pct, b, a, o, h, l, cl, v, oi = base_prices[sym]
        else:
            code = int(item.get("scripCode") or 1000)
            p = float(code % 1500) + 120.0
            c = float((code % 18) - 9)
            pct = round((c / p) * 100, 2)
            b, a, o, h, l, cl, v, oi = p - 0.05, p, p - c, p + abs(c) + 2.0, max(1.0, p - abs(c) - 2.0), p - c, 185000, 8500
        
        q = {
            "scripCode": item.get("scripCode"),
            "exchangeCode": item.get("exchange", "NC"),
            "ltp": p, "rsChange": c, "perChange": pct,
            "bidPrice": b, "offPrice": a, "open": o,
            "high": h, "low": l, "close": cl, "qty": v, "currentOI": oi
        }
        self.app.raw_ticks[k] = q
        hist = self._tick_history.setdefault(k, [])
        if not hist:
            hist.extend([p * (1 + (random.random() - 0.5) * 0.01) for _ in range(15)])
        return q

    def add_watch_row(self, item: dict) -> None:
        t = self.query_one("#t-watch", DataTable)
        k = self.feed_key(item)
        q = self.get_initial_quote(item)
        if k not in t.rows:
            t.add_row(
                scrip_label(item),
                item["exchange"],
                Text(fmt(q["ltp"]), style=f"bold {C_GREEN}"),
                Text(fmt(q["rsChange"]), style=sign_style(q["rsChange"])),
                Text(f"{q['perChange']:+.2f}%" if isinstance(q['perChange'], (int, float)) else fmt(q['perChange']), style=sign_style(q["perChange"])),
                Text(fmt(q["bidPrice"])),
                Text(fmt(q["offPrice"])),
                Text(fmt(q["open"])),
                Text(fmt(q["high"]), style=C_GREEN),
                Text(fmt(q["low"]), style=C_RED),
                Text(fmt(q["close"])),
                Text(fmt(q["qty"])),
                Text(fmt(q["currentOI"])),
                key=k
            )

    def _simulate_tick(self) -> None:
        """Simulate micro price ticks in paper mode / background so Watchlist & Dashboard stay alive."""
        if not self.watch:
            return
        item = random.choice(self.watch)
        k = self.feed_key(item)
        q = self.get_initial_quote(item)
        old_ltp = float(q["ltp"])
        delta = round(random.gauss(0, old_ltp * 0.0015), 2)
        if delta == 0:
            delta = 0.05
        new_ltp = max(0.5, round(old_ltp + delta, 2))
        chg = round(float(q.get("rsChange") or 0) + delta, 2)
        op = float(q.get("open") or new_ltp)
        pct = round((chg / op) * 100, 2) if op else 0.0

        tick = {
            "scripCode": item.get("scripCode"),
            "exchangeCode": item.get("exchange", "NC"),
            "ltp": new_ltp,
            "rsChange": chg,
            "perChange": pct,
            "bidPrice": round(new_ltp - 0.05, 2),
            "offPrice": new_ltp,
            "high": max(float(q.get("high") or new_ltp), new_ltp),
            "low": min(float(q.get("low") or new_ltp), new_ltp),
            "qty": int(q.get("qty") or 1000) + random.randint(10, 500),
        }
        self.on_tick(tick)

    def on_unmount(self) -> None:
        if self.feed:
            self.feed.stop()

    # ── Status / logging ──────────────────────────────────────────────────────
    def status(self, msg: str, error: bool = False) -> None:
        prefix = "  ✗  " if error else "  ·  "
        style  = f"bold {C_RED}" if error else C_MUTED
        now    = datetime.now().strftime("%H:%M:%S")
        t = Text()
        t.append(prefix, style=style)
        t.append(msg, style=style if error else C_TEXT)
        t.append(f"  [{now}]", style=C_SUBTLE)
        self.query_one("#status", Static).update(t)

    def log_activity(self, line: str) -> None:
        ts  = datetime.now().strftime("%H:%M:%S")
        t   = Text()
        t.append(f"  {ts}  ", style=C_SUBTLE)
        t.append(line)
        self.query_one("#activity-log", RichLog).write(t)
        self.query_one("#dash-feed-log", RichLog).write(t)

    def post(self, fn, *a) -> None:
        try:
            self.app.call_from_thread(fn, *a)
        except Exception:
            pass

    # ── Feed helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def feed_key(item: dict) -> str:
        return f"{item['exchange']}{item['scripCode']}"

    # ── Tab/selection helpers ─────────────────────────────────────────────────
    def active_tab(self) -> str:
        return self.query_one("#tabs", TabbedContent).active

    def selected(self, tab: str) -> dict | None:
        if tab == "dashboard":
            tab = "watch"
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

    # ── Dashboard Update ──────────────────────────────────────────────────────
    def update_dashboard(self) -> None:
        """Update unified overview dashboard cards."""
        orders = self.data.get("orders", [])
        positions = self.data.get("positions", [])
        holdings = self.data.get("holdings", [])
        funds = self.data.get("funds", [])

        bpl = sum(float(str(get(r, "bpl", default=0)).replace(",", "") or 0) for r in positions)
        mtm = sum(float(str(get(r, "mtm", default=0)).replace(",", "") or 0) for r in positions)
        total_pnl = bpl + mtm

        # 1. Summary Strip Card
        s = Text()
        s.append("  ❖ ACCOUNT & PORTFOLIO OVERVIEW\n\n", style=f"bold {C_CYAN}")
        s.append("  Net P/L: ", style=C_MUTED)
        s.append(f"₹{total_pnl:+,.2f}  ", style=sign_style(total_pnl))
        s.append(f"(Realised: ₹{bpl:+,.2f} · MTM: ₹{mtm:+,.2f})\n", style=C_SUBTLE)
        s.append("  Active Positions: ", style=C_MUTED)
        s.append(f"{len(positions)}  ", style=f"bold {C_CYAN}")
        s.append("  Open Orders: ", style=C_MUTED)
        s.append(f"{sum(1 for r in orders if is_open_order(r))}  ", style=f"bold {C_AMBER}")
        s.append("  Holdings: ", style=C_MUTED)
        s.append(f"{len(holdings)}  ", style=f"bold {C_GREEN}")
        s.append("  Watchlist: ", style=C_MUTED)
        s.append(f"{len(self.watch)} symbols\n", style=C_TEXT)
        self.query_one("#dash-summary-strip", Static).update(s)

        # 2. Orders Analytics Card
        o_text = Text()
        open_cnt = sum(1 for r in orders if is_open_order(r))
        filled_cnt = sum(1 for r in orders if "fully" in str(get(r, "orderStatus")).lower())
        rej_cnt = sum(1 for r in orders if any(x in str(get(r, "orderStatus")).lower() for x in ("reject", "fail", "cancel")))
        
        o_text.append(f"  Orders breakdown: ", style=C_MUTED)
        o_text.append(f"Filled: {filled_cnt}  ", style=f"bold {C_GREEN}")
        o_text.append(f"Pending: {open_cnt}  ", style=f"bold {C_AMBER}")
        o_text.append(f"Cancelled/Rejected: {rej_cnt}\n\n", style=C_SUBTLE)

        if orders:
            o_text.append("  Recent Orders:\n", style=C_MUTED)
            for r in orders[:4]:
                side = str(get(r, "buySell", default="B")).upper()
                clr = C_GREEN if side.startswith("B") else C_RED
                o_text.append(f"   {side[:1]} ", style=f"bold {clr}")
                o_text.append(f"{get(r, 'orderQty')} × {get(r, 'tradingSymbol')} @ ₹{get(r, 'orderPrice')} ", style=C_TEXT)
                o_text.append(f"[{get(r, 'orderStatus')}]\n", style=C_SUBTLE)
        else:
            o_text.append("  No orders submitted in current session.\n", style=C_DIM)
        
        self.query_one("#dash-orders-summary", Static).update(o_text)

        # 3. Watchlist Quick Monitor Card
        w_text = Text()
        w_text.append("  Live Market Snapshot:\n\n", style=C_MUTED)
        for item in self.watch[:6]:
            k = self.feed_key(item)
            q = self.app.raw_ticks.get(k, {})
            ltp = q.get("ltp") or 0.0
            pct = q.get("perChange") or 0.0
            hist = self._tick_history.get(k, [ltp] * 5)
            spk = sparkline(hist, width=12)
            
            w_text.append(f"  {item.get('tradingSymbol', ''):<10} ", style=f"bold {C_CYAN}")
            w_text.append(f"₹{ltp:>8.2f} ", style="bold white")
            w_text.append(f"({pct:+6.2f}%) ", style=sign_style(pct))
            w_text.append(f" {spk}\n", style=C_GREEN if pct >= 0 else C_RED)
        
        self.query_one("#dash-watch-summary", Static).update(w_text)

    # ── Command bar ───────────────────────────────────────────────────────────
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
            "/dashboard":  lambda: self.action_tab("dashboard"),
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
            "/add":        self.action_add,
            "/remove":     self.action_remove,
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
            self.status(f"Unknown command: {cmd}  —  F1 for help", True)

    # ── Data loading ──────────────────────────────────────────────────────────
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
                exs = c.exchanges if c.exchanges else ["NC"]
                if any(e in exs for e in ("NC", "BC", "NF")):
                    groups.append("NC")
                groups += [g for g in ("MX", "RN") if g in exs]
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
        if tab == "positions":
            self._update_pnl_strip(rows)
        self.update_dashboard()

    def _update_pnl_strip(self, rows: list[dict]) -> None:
        """Show today's realised + MTM P/L summary strip."""
        try:
            bpl = sum(float(str(get(r, "bpl", default=0)).replace(",", "") or 0) for r in rows)
            mtm = sum(float(str(get(r, "mtm", default=0)).replace(",", "") or 0) for r in rows)
            total = bpl + mtm
            c_bpl = C_GREEN if bpl >= 0 else C_RED
            c_mtm = C_GREEN if mtm >= 0 else C_RED
            c_tot = C_GREEN if total >= 0 else C_RED
            s  = "+" if bpl  >= 0 else ""
            sm = "+" if mtm  >= 0 else ""
            st = "+" if total >= 0 else ""
            t  = Text()
            t.append("  P/L  ", style=C_SUBTLE)
            t.append("Realised: ", style=C_MUTED)
            t.append(f"₹{s}{bpl:,.2f}", style=f"bold {c_bpl}")
            t.append("   MTM: ", style=C_MUTED)
            t.append(f"₹{sm}{mtm:,.2f}", style=f"bold {c_mtm}")
            t.append("   Total: ", style=C_MUTED)
            t.append(f"₹{st}{total:,.2f}", style=f"bold {c_tot}")
            t.append(f"  ({len(rows)} position{'s' if len(rows) != 1 else ''})", style=C_SUBTLE)
            self.query_one("#pnl-strip", Static).update(t)
        except Exception:
            pass

    # ── Tab actions ───────────────────────────────────────────────────────────
    def action_tab(self, tab: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab
        self.log_activity(f"📑 Switched to tab: {tab}")

    def action_refresh_all(self) -> None:
        self.refresh_all_data()
        self.status("All data refreshed")
        self.log_activity("🔄 Manual data refresh triggered")

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
        item = self.selected("watch")
        self.app.push_screen(WhatIfScreen(item))

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen())

    def action_kill(self) -> None:
        self.log_activity("⚠ KILL SWITCH — automated order entry would be blocked")
        if self.app.client.paper:
            self.status("⚠ KILL — automation disabled (already in paper mode)")
        else:
            self.status("⚠ KILL — block automated orders", True)

    # ── Add / remove symbols ──────────────────────────────────────────────────
    def action_add(self) -> None:
        """Open symbol search — works from ANY tab."""
        def done(item: dict | None) -> None:
            if not item or item.get("scripCode") is None:
                return
            if any(self.feed_key(w) == self.feed_key(item) for w in self.watch):
                self.status(f"{item.get('tradingSymbol')} is already in watchlist")
                return
            self.watch.append(item)
            write_private(WATCH_FILE, self.watch)
            self.add_watch_row(item)
            if self.feed:
                self.feed.subscribe(self.feed_key(item))
            sym = scrip_label(item)
            self.status(f"✓ Added {sym} to watchlist — press 2 to view")
            self.log_activity(f"+ Added {sym} to watchlist")
            self.update_dashboard()
        self.app.push_screen(SymbolSearch(), done)

    def action_remove(self) -> None:
        item = self.selected("watch")
        if not item:
            self.status("Select a symbol in Watchlist first", True)
            return
        k          = self.feed_key(item)
        sym        = scrip_label(item)
        self.watch = [w for w in self.watch if self.feed_key(w) != k]
        write_private(WATCH_FILE, self.watch)
        try:
            self.query_one("#t-watch", DataTable).remove_row(k)
        except Exception:
            pass
        if self.feed:
            self.feed.unsubscribe(k)
        self.status(f"✓ Removed {sym} from watchlist")
        self.log_activity(f"− Removed {sym} from watchlist")
        self.update_dashboard()

    # ── Trade actions ─────────────────────────────────────────────────────────
    def action_trade(self, side: str) -> None:
        tab  = self.active_tab()
        item = None

        if tab in ("watch", "dashboard"):
            item = self.selected("watch")
        elif tab == "orders":
            row  = self.selected("orders")
            item = self.row_to_info(row) if row else None
        elif tab == "positions":
            row  = self.selected("positions")
            if row:
                item = {
                    "tradingSymbol": get(row, "tradingSymbol"),
                    "scripCode":     get(row, "scripCode", default=None),
                    "exchange":      get(row, "exchange", default="NC"),
                }
        elif tab == "holdings":
            row  = self.selected("holdings")
            if row:
                item = {
                    "tradingSymbol": get(row, "tradingSymbol"),
                    "scripCode":     get(row, "scripCode", default=None),
                    "exchange":      get(row, "exchange", default="NC"),
                }

        if not item:
            item = self.watch[0] if self.watch else None

        if not item:
            self.status("Select a symbol in Watchlist / Positions / Holdings first", True)
            return

        info = dict(item, side=side)
        ltp  = getattr(self.app, "raw_ticks", {}).get(
            self.feed_key(item) if "scripCode" in item else "", {}).get("ltp")
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
            "triggerPrice":  get(r, "trigPrice", "triggerPrice", default="0"),
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

    # ── Cancel actions ────────────────────────────────────────────────────────
    def action_cancel_order(self) -> None:
        row = self.selected("orders") if self.active_tab() == "orders" else None
        if not row:
            return
        oid = get(row, "orderId")
        if not is_open_order(row):
            self.status(f"Order {oid} is already {get(row, 'orderStatus')} — nothing to cancel", True)
            return
        body = Text()
        body.append(f"Order ID: {oid}\n", style=f"bold {C_CYAN}")
        body.append(f"{get(row, 'tradingSymbol')}  ({get(row, 'exchange')})\n")
        body.append(f"{get(row, 'buySell')}  {get(row, 'orderQty')} units  @  ₹{get(row, 'orderPrice')}")
        self.confirm("Cancel Order", body, lambda: self.cancel_ids([str(oid)]))

    def action_cancel_all(self) -> None:
        ids = [str(get(r, "orderId")) for r in self.data.get("orders", []) if is_open_order(r)]
        if not ids:
            self.status("No open orders to cancel", True)
            return
        body = Text()
        body.append(f"{len(ids)} open order(s) will be cancelled:\n", style=f"bold {C_AMBER}")
        body.append(", ".join(ids), style=C_MUTED)
        self.confirm("Cancel ALL Open Orders", body, lambda: self.cancel_ids(ids))

    @work(thread=True)
    def cancel_ids(self, ids: list[str]) -> None:
        for oid in ids:
            try:
                r = self.app.client.cancel_by_id(oid)
                self.post(self.log_activity, f"✓ CANCEL {oid}: {r}")
            except Exception as e:
                self.post(self.log_activity, f"✗ CANCEL {oid} FAILED: {e}")
                self.post(self.app.notify, f"Cancel {oid}: {e}", "error")
        self.post(self.load, "orders")

    @work(thread=True)
    def send(self, p: dict) -> None:
        side = "▲ BUY" if p.get("transactionType") == "B" else "▼ SELL"
        desc = f"{side} {p['quantity']} × {p['tradingSymbol']}"
        try:
            r = self.app.client.submit(p)
            self.post(self.log_activity, f"✓ {p['requestType']} {desc} → {r}")
            self.post(self.app.notify, f"✓ {p['requestType']} submitted: {str(r)[:120]}")
        except Exception as e:
            err_msg = str(e)
            if "ip address is not allowed" in err_msg.lower():
                hint = " (Whitelist your public IP in Sharekhan API portal https://api.sharekhan.com or run sktui --paper)"
                self.post(self.log_activity, f"✗ {p['requestType']} {desc} FAILED: {e}{hint}")
                self.post(self.app.notify, f"IP Blocked: Whitelist your IP in Sharekhan API Portal or use --paper mode", severity="error", timeout=12)
            else:
                self.post(self.log_activity, f"✗ {p['requestType']} {desc} FAILED: {e}")
                self.post(self.app.notify, f"Order failed: {e}", severity="error")
        self.post(self.load, "orders")

    # ── Chart / detail / quote ────────────────────────────────────────────────
    def action_chart(self) -> None:
        tab  = self.active_tab()
        item = self.selected(tab) or (self.watch[0] if self.watch else None)
        if item:
            sym = scrip_label(item)
            self.log_activity(f"📈 Opened chart for {sym} ({item.get('exchange', '')}), tab={tab}")
            self.app.push_screen(HistoryScreen(item))
        else:
            self.status("Select a symbol in Watchlist / Orders / Positions / Holdings first", True)

    def action_detail(self) -> None:
        row = self.selected("orders") if self.active_tab() == "orders" else None
        if row:
            oid = get(row, "orderId")
            sym = get(row, "tradingSymbol", default="?")
            self.log_activity(f"ℹ Opened order detail: {sym} (#{oid})")
            self.app.push_screen(DetailScreen(row))

    def action_quote(self) -> None:
        item = self.selected("watch") or (self.watch[0] if self.watch else None)
        if item:
            sym = scrip_label(item)
            self.log_activity(f"❓ Opened live quote for {sym}")
            self.app.push_screen(QuoteScreen(self.feed_key(item), scrip_label(item)))

    def action_logout(self) -> None:
        if self.feed:
            self.feed.stop()
        self.app.client.logout()
        SESSION_FILE.unlink(missing_ok=True)
        self.app.client = None
        self.app.switch_screen(LoginScreen())

    # ── WebSocket feed ────────────────────────────────────────────────────────
    def on_ws(self, msg: dict) -> None:
        log = self.query_one("#feedlog", RichLog)
        if log.display:
            log.write(json.dumps(msg)[:500])
        data = msg.get("data") if isinstance(msg, dict) else None
        if isinstance(data, dict):
            if "AckState" in data or "SharekhanOrderID" in data:
                return self.on_ack(data)
            if "scripCode" in data and ("ltp" in data or "lastTradedPrice" in data):
                return self.on_tick(data)

    def on_ack(self, d: dict) -> None:
        state    = d.get("AckState", "")
        side_str = d.get("BuySellString", "")
        qty      = d.get("TradeQty") or d.get("OrderQty", "")
        sym      = d.get("TradingSymbol", "")
        price    = (d.get("TradePrice") if d.get("TradeQty") else d.get("OrderPrice", ""))
        oid      = d.get("SharekhanOrderID", "")
        err      = d.get("ErrorMessage") or ""
        bad      = any(x in str(state).lower() for x in ("reject", "fail", "error"))
        icon     = "✗" if bad else "✓"
        line     = f"{icon}  {state}  {side_str} {qty} × {sym} @ ₹{price}  (#{oid})"
        if err:
            line += f"  — {err}"
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
        code = d.get("scripCode")
        exch = d.get("exchangeCode") or d.get("exchange") or "NC"
        key  = f"{exch}{code}"
        
        raw  = self.app.raw_ticks
        prev = raw.get(key, {}).get("ltp")
        raw.setdefault(key, {}).update(d)

        # Robust extraction for all API websocket tick field variants
        ltp = d.get("ltp") or d.get("lastTradedPrice") or d.get("LTP")
        if ltp is not None:
            fltp = float(ltp)
            raw[key]["ltp"] = fltp
            hist = self._tick_history.setdefault(key, [])
            hist.append(fltp)
            if len(hist) > 30:
                hist.pop(0)

        table = self.query_one("#t-watch", DataTable)
        if key not in table.rows:
            return

        chg = d.get("rsChange") or d.get("change") or d.get("netPriceChange") or raw[key].get("rsChange")
        pct = d.get("perChange") or d.get("pChange") or d.get("percentChange") or raw[key].get("perChange")
        bid = d.get("bidPrice") or d.get("bid") or raw[key].get("bidPrice")
        ask = d.get("offPrice") or d.get("ask") or raw[key].get("offPrice")
        op  = d.get("open") or d.get("openPrice") or raw[key].get("open")
        hi  = d.get("high") or d.get("highPrice") or raw[key].get("high")
        lo  = d.get("low") or d.get("lowPrice") or raw[key].get("low")
        cl  = d.get("close") or d.get("closePrice") or raw[key].get("close")
        vol = d.get("qty") or d.get("volume") or d.get("vol") or raw[key].get("qty")
        oi  = d.get("currentOI") or d.get("openInterest") or d.get("oi") or raw[key].get("currentOI")

        if ltp is not None:
            fltp = float(ltp)
            if prev is not None:
                if fltp > prev:
                    table.update_cell(key, "ltp", Text(f"▲ {fmt(fltp)}", style=f"bold {C_GREEN}"))
                elif fltp < prev:
                    table.update_cell(key, "ltp", Text(f"▼ {fmt(fltp)}", style=f"bold {C_RED}"))
                else:
                    table.update_cell(key, "ltp", Text(fmt(fltp), style=C_TEXT))
            else:
                table.update_cell(key, "ltp", Text(fmt(fltp), style=f"bold {C_GREEN}"))

        if chg is not None: table.update_cell(key, "chg", Text(fmt(chg), style=sign_style(chg)))
        if pct is not None:
            fpct = float(pct)
            table.update_cell(key, "pct", Text(f"{fpct:+.2f}%", style=sign_style(fpct)))
        if bid is not None: table.update_cell(key, "bid", Text(fmt(bid)))
        if ask is not None: table.update_cell(key, "ask", Text(fmt(ask)))
        if op  is not None: table.update_cell(key, "open", Text(fmt(op)))
        if hi  is not None: table.update_cell(key, "high", Text(fmt(hi), style=C_GREEN))
        if lo  is not None: table.update_cell(key, "low", Text(fmt(lo), style=C_RED))
        if cl  is not None: table.update_cell(key, "close", Text(fmt(cl)))
        if vol is not None: table.update_cell(key, "vol", Text(fmt(vol)))
        if oi  is not None: table.update_cell(key, "oi", Text(fmt(oi)))
