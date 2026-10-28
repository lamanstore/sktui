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
    C_AMBER, C_CYAN, C_GREEN, C_MUTED, C_RED, C_SUBTLE, C_TEXT,
    ALERTS_FILE, DATA, SESSION_FILE, WATCH_FILE,
)
from sktui.screens.login import LoginScreen
from sktui.screens.modals import (
    AlertsModal, AuditTrailModal, Confirm, DetailScreen, FocusModal, HelpScreen, HistoryScreen, OrderTicket,
    PortfolioAnalyticsModal, ProductsScreen, QuoteScreen, ReplayModal, RiskScreen, ScannerModal, SymbolSearch,
    SystemStatusScreen, WhatIfScreen, sparkline,
)
from sktui.services.alert_engine import AlertEngine, parse_alert_command
from sktui.services.market import MarketService
from sktui.services.order_service import OrderService
from sktui.services.portfolio_analytics import PortfolioAnalytics
from sktui.services.replay_engine import ReplayEngine
from sktui.services.scanner import MarketScanner
from sktui.services.status_service import StatusService
from sktui.services.watchlist import WatchlistService
from sktui.state.quote_store import QuoteStore
from sktui.state.watchlist_store import DEFAULT_WATCH, WatchlistStore
from sktui.ui.widgets.dashboard_cards import update_dashboard, update_pnl_strip
from sktui.ui.widgets.market_radar import MarketRadarSidebar
from sktui.ui.widgets.watchlist_table import WATCH_COLS, add_watch_row, update_watch_row
from sktui.utils import fill_table, get, get_public_ip, human, is_open_order, scrip_label

# ── Re-exports for backward compatibility ────────────────────────────────────
__all__ = ["MainScreen", "MarketRadarSidebar", "WATCH_COLS", "DEFAULT_WATCH"]

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


class MainScreen(Screen):
    BINDINGS = [
        Binding("b",            "trade('B')",     "Buy"),
        Binding("s",            "trade('S')",     "Sell"),
        Binding("a",            "add",            "Add"),
        Binding("delete",       "remove",         "Del"),
        Binding("m",            "modify",         "Modify"),
        Binding("x",            "cancel_order",   "Cancel"),
        Binding("X",            "cancel_all",     "Cancel all", show=False),
        Binding("K",            "panic_flatten",  "Flatten"),
        Binding("f",            "toggle_focus",   "Focus"),
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
        self.watchlist_store = WatchlistStore(WATCH_FILE)
        self.watchlist_service = WatchlistService(self.watchlist_store)
        self.watch: list[dict] = self.watchlist_store.items
        self.quotes = QuoteStore()
        self.market_service = MarketService(self.quotes, self.watchlist_store)
        self.alert_engine = AlertEngine(ALERTS_FILE)
        self.focus_mode: bool = False
        self.order_service: OrderService | None = None
        self.status_service: StatusService | None = None

        self.data: dict[str, list[dict]] = {}
        self.feed: api.Feed | None = None
        self._ack_pending = False
        self.public_ip: str = "Fetching…"

    @property
    def _tick_history(self) -> dict[str, list[float]]:
        return self.quotes.tick_history

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
                yield Static("", id="cmd-suggestions")
                with Horizontal(id="cmd-bar"):
                    yield Static("  /  ", id="cmd-prefix")
                    yield Input(
                        placeholder=(
                            "command  —  /dashboard, /watchlist, /buy, /sell, /chart, /alert, "
                            "/alerts, /flatten, /risk, /status, /help  …"
                        ),
                        id="cmd-input")
        yield Static("", id="status")
        yield Footer()

    # ── Mount ─────────────────────────────────────────────────────────────────
    def on_mount(self) -> None:
        c = self.app.client
        self.order_service = OrderService(c)
        # Restore order history from persisted audit trail
        self.order_service.order_store.load_from_audit()
        self.status_service = StatusService(c)
        self.watchlist_service.set_feed(self.feed)

        # Share raw_ticks dictionary reference with app
        if hasattr(self.app, "raw_ticks"):
            if self.app.raw_ticks:
                self.quotes.raw_ticks.update(self.app.raw_ticks)
            self.app.raw_ticks = self.quotes.raw_ticks

        # Wire MarketService callbacks
        self.market_service.on_tick_update = self._on_tick_update
        self.market_service.on_ack_update = self.on_ack

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
        self.set_interval(1.0, self._update_account_bar)
        self.set_interval(2, self.update_dashboard)
        self.set_interval(1.5, self._simulate_tick)
        self.set_interval(20, self.refresh_active)
        self.set_interval(60, self._update_indices_bar)

        if getattr(self.app, "enable_feed", True):
            self.feed = api.Feed(
                c.access_token, c.api_key, c.cid,
                lambda: self.watchlist_service.feed_keys(),
                lambda m: self.post(self.on_ws, m),
                lambda s, err: self.post(self.status, s, err),
            )
            self.watchlist_service.set_feed(self.feed)
            self.feed.start()

        self.alert_engine.add_listener(lambda a, ltp: self.post(self._on_alert_triggered, a, ltp))

    def _on_alert_triggered(self, alert: Any, ltp: float) -> None:
        self.app.notify(
            f"🔔 ALERT TRIGGERED: {alert.symbol} {alert.condition} {alert.target_value:,.2f} (LTP: ₹{ltp:,.2f})",
            severity="warning",
            timeout=10,
        )
        self.log_activity(f"🔔 ALERT TRIGGERED: {alert.symbol} reached ₹{ltp:,.2f} (Target: {alert.target_value:,.2f})")

    # ── Status and Indices Bars ───────────────────────────────────────────────
    def _update_account_bar(self) -> None:
        if self.status_service:
            t = self.status_service.render_account_bar(
                self.public_ip, quote_store=self.quotes
            )
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
        if not self.status_service:
            return
        raw = getattr(self.app, "raw_ticks", {})
        self.query_one("#indices-bar", Static).update(
            self.status_service.render_indices_bar(raw)
        )
        try:
            self.query_one("#radar-session", Static).update(
                self.status_service.render_radar_session()
            )
            self.query_one("#radar-sectors", Static).update(
                self.status_service.render_radar_sectors()
            )
            self.query_one("#radar-breadth", Static).update(
                self.status_service.render_radar_breadth()
            )
        except Exception:
            pass

    # ── Watchlist / Market data wiring ────────────────────────────────────────
    def get_initial_quote(self, item: dict) -> dict:
        return self.market_service.initial_quote(item)

    def add_watch_row(self, item: dict) -> None:
        t = self.query_one("#t-watch", DataTable)
        q = self.market_service.initial_quote(item)
        add_watch_row(t, item, q)

    def _simulate_tick(self) -> None:
        if not self.watch:
            return
        item = random.choice(self.watch)
        self.market_service.simulate_tick(item)

    def on_unmount(self) -> None:
        if self.feed:
            self.feed.stop()

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
        ts = datetime.now().strftime("%H:%M:%S")
        t = Text()
        t.append(f"  {ts}  ", style=C_SUBTLE)
        t.append(line)
        self.query_one("#activity-log", RichLog).write(t)
        self.query_one("#dash-feed-log", RichLog).write(t)

    def post(self, fn, *a) -> None:
        try:
            self.app.call_from_thread(fn, *a)
        except Exception:
            pass

    @staticmethod
    def feed_key(item: dict) -> str:
        return WatchlistStore.feed_key(item)

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
        """Update unified overview dashboard cards via dashboard_cards module."""
        try:
            update_dashboard(
                dash_summary=self.query_one("#dash-summary-strip", Static),
                dash_orders=self.query_one("#dash-orders-summary", Static),
                dash_watch=self.query_one("#dash-watch-summary", Static),
                orders=self.data.get("orders", []),
                positions=self.data.get("positions", []),
                holdings=self.data.get("holdings", []),
                watch=self.watch,
                raw_ticks=getattr(self.app, "raw_ticks", {}),
                tick_history=self.quotes.tick_history,
                sparkline_fn=sparkline,
            )
        except Exception:
            pass

    # ── Command bar ───────────────────────────────────────────────────────────
    ALL_COMMANDS = [
        "/dashboard", "/watchlist", "/orders", "/positions", "/holdings",
        "/funds", "/activity", "/buy", "/sell", "/cancel", "/modify",
        "/chart", "/quote", "/add", "/remove", "/products", "/alert",
        "/alerts", "/flatten", "/risk", "/whatif", "/audit", "/analytics",
        "/portfolio", "/status", "/refresh", "/scanner", "/focus", "/replay",
        "/help", "/kill", "/logout",
    ]

    def action_focus_cmd(self) -> None:
        self.query_one("#cmd-input", Input).focus()

    @on(Input.Changed, "#cmd-input")
    def _cmd_changed(self, e: Input.Changed) -> None:
        val = e.value.strip().lower()
        if not val or len(val) < 2:
            self.query_one("#cmd-suggestions", Static).update("")
            return
        prefix = val if val.startswith("/") else f"/{val}"
        matches = [c for c in self.ALL_COMMANDS if prefix in c or c.startswith(prefix)][:6]
        if matches:
            t = Text()
            t.append("  Suggestions: ", style=C_MUTED)
            for m in matches:
                t.append(f" {m} ", style=f"bold {C_CYAN} on #0a1f36")
                t.append(" ")
            self.query_one("#cmd-suggestions", Static).update(t)
        else:
            self.query_one("#cmd-suggestions", Static).update("")

    @on(Input.Submitted, "#cmd-input")
    def _cmd_submitted(self, e: Input.Submitted) -> None:
        raw = e.value.strip()
        e.input.value = ""
        self.query_one("#cmd-suggestions", Static).update("")
        if not raw:
            return

        # Handle parameterized /alert command
        if raw.lower().startswith("/alert ") or raw.lower().startswith("alert "):
            parsed = parse_alert_command(raw)
            if parsed:
                sym, cond, val = parsed
                alert = self.alert_engine.add_alert(sym, cond, val)
                self.status(f"✓ Alert active: {sym} {cond} {val:,.2f}")
                self.app.notify(f"✓ Alert registered: {sym} {cond} {val:,.2f}")
                self.log_activity(f"+ Alert: {sym} {cond} {val:,.2f}")
            else:
                self.status("Usage: /alert <SYM> > <VAL> (e.g. /alert RELIANCE > 3000)", True)
            return

        cmd = raw.split()[0].lower()
        if not cmd.startswith("/"):
            cmd = "/" + cmd
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
            "/audit":      self.action_show_audit,
            "/analytics":  self.action_show_analytics,
            "/portfolio":  self.action_show_analytics,
            "/alert":      self.action_show_alerts,
            "/alerts":     self.action_show_alerts,
            "/scanner":    self.action_scanner,
            "/focus":      self.action_focus_view,
            "/replay":     self.action_replay,
            "/flatten":    self.action_panic_flatten,
            "/feed":       self.action_toggle_log,
            "/refresh":    self.action_refresh_all,
            "/logout":     self.action_logout,
            "/help":       self.action_help,
            "/kill":       self.action_kill,
            "/export":     self.action_export_csv,
        }
        fn = dispatch.get(cmd)
        if fn:
            fn()
        else:
            self.status(f"Unknown command: {cmd}  —  F1 for help", True)

    def action_scanner(self) -> None:
        scanner = MarketScanner(self.quotes, self.watch)
        def on_result(res: Any) -> None:
            if not res:
                return
            action_type = res[0]
            if action_type == "trade":
                side, candidate = res[1], res[2]
                self.action_trade(side, candidate)
            elif action_type == "chart":
                candidate = res[1]
                self.app.push_screen(DetailScreen(candidate, self.app.client))
        self.app.push_screen(ScannerModal(scanner), on_result)

    def action_focus_view(self) -> None:
        item = self.selected(self.active_tab()) or (self.watch[0] if self.watch else None)
        if not item:
            self.status("Select a symbol to inspect focus & depth", True)
            return
        feed_key = self.feed_key(item)
        quote = self.quotes.get(feed_key) or {}
        def on_result(res: Any) -> None:
            if not res:
                return
            action_type = res[0]
            if action_type == "trade":
                side, it = res[1], res[2]
                self.action_trade(side, it)
            elif action_type == "chart":
                it = res[1]
                self.app.push_screen(DetailScreen(it, self.app.client))
            elif action_type == "alert":
                self.app.push_screen(AlertsModal(self.alert_engine))
        self.app.push_screen(FocusModal(item, quote), on_result)

    def action_replay(self) -> None:
        item = self.selected(self.active_tab()) or (self.watch[0] if self.watch else None)
        sym = scrip_label(item) if item else "NIFTY"
        exch = str(item.get("exchange", "NC")) if item else "NC"
        from sktui.chart import aggregate_to_candles
        base_p = float(item.get("price") or 1000.0) if item else 1000.0
        prices = [base_p + (i * 1.5) - (0.5 * (i % 3)) for i in range(40)]
        candles = aggregate_to_candles(prices, bar_size=4)
        engine = ReplayEngine(on_tick=lambda t: self.post(self.market_service._process_tick, t))
        scrip_cd = int(item.get("scripCode") or 2475) if item else 2475
        engine.load_candles(sym, exch, candles, scrip_code=scrip_cd)
        self.app.push_screen(ReplayModal(engine))

    def action_show_alerts(self) -> None:
        self.app.push_screen(AlertsModal(self.alert_engine))

    def action_export_csv(self) -> None:
        """Export session trades, positions, orders, and P/L analytics to CSV."""
        positions = self.data.get("positions", [])
        orders = self.data.get("orders", [])
        ticks = getattr(self.app, "raw_ticks", {})
        summary = PortfolioAnalytics.analyze(positions, ticks)

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = DATA / f"session_{now_str}.csv"
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            with open(export_file, "w", encoding="utf-8") as f:
                f.write("# SKTUI SESSION REPORT\n")
                f.write(f"# Timestamp: {datetime.now().isoformat()}\n")
                f.write("# Realized PnL,Unrealized PnL,Total PnL,Gross Exposure,Net Exposure,Win Rate Pct,Profit Factor\n")
                f.write(f"{summary.realized_pnl:.2f},{summary.unrealized_pnl:.2f},{summary.total_pnl:.2f},"
                        f"{summary.total_gross_exposure:.2f},{summary.net_exposure:.2f},{summary.win_rate_pct:.1f},{summary.profit_factor:.2f}\n\n")

                f.write("# OPEN & CLOSED POSITIONS\n")
                f.write("Symbol,Exchange,Product,NetQty,AvgPrice,BookedPnL,MtmPnL\n")
                for p in positions:
                    f.write(f"{get(p, 'tradingSymbol')},{get(p, 'exchange')},{get(p, 'productType')},"
                            f"{get(p, 'netQty')},{get(p, 'avgPrice')},{get(p, 'bpl')},{get(p, 'mtm')}\n")

                f.write("\n# ORDERS AUDIT\n")
                f.write("OrderID,Symbol,Exchange,Side,Qty,ExecQty,Price,ExecPrice,Status,Reason\n")
                for o in orders:
                    f.write(f"{get(o, 'orderId')},{get(o, 'tradingSymbol')},{get(o, 'exchange')},"
                            f"{get(o, 'buySell')},{get(o, 'orderQty')},{get(o, 'execQty')},"
                            f"{get(o, 'orderPrice')},{get(o, 'execPrice')},{get(o, 'orderStatus')},\"{get(o, 'errorMsg')}\"\n")

            msg = f"✓ Exported session analytics to: {export_file.name}"
            self.status(msg)
            self.app.notify(msg, timeout=8)
            self.log_activity(f"+ Export: {export_file.name}")
        except Exception as e:
            self.status(f"Export failed: {e}", True)
            self.app.notify(f"Export failed: {e}", severity="error")

    def action_toggle_focus(self) -> None:
        """Toggle Focus Mode: hide/show sidebar and indices bar for distraction-free trading."""
        self.focus_mode = not self.focus_mode
        try:
            self.query_one("#sidebar").display = not self.focus_mode
            self.query_one("#indices-bar").display = not self.focus_mode
        except Exception:
            pass
        if self.focus_mode:
            self.status("⚡ Focus Mode Enabled — Sidebar hidden (Press 'f' to restore standard layout)")
        else:
            self.status("✓ Standard Workstation Layout Restored")

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
        try:
            update_pnl_strip(self.query_one("#pnl-strip", Static), rows)
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
        log = self.query_one("#feedlog")
        log.display = not log.display

    def action_products(self) -> None:
        self.app.push_screen(ProductsScreen())

    def action_system_status(self) -> None:
        self.app.push_screen(SystemStatusScreen())

    def action_show_risk(self) -> None:
        self.app.push_screen(RiskScreen())

    def action_show_audit(self) -> None:
        self.app.push_screen(AuditTrailModal())

    def action_show_analytics(self) -> None:
        self.app.push_screen(PortfolioAnalyticsModal())

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

    # ── Watchlist mutations ───────────────────────────────────────────────────
    def action_add(self) -> None:
        """Open symbol search — works from ANY tab."""
        def done(item: dict | None) -> None:
            if not item or item.get("scripCode") is None:
                return
            self.watchlist_service.add(
                item,
                on_success=lambda it, sym: self._on_watch_added(it, sym),
                on_duplicate=lambda sym: self.status(f"{sym} is already in watchlist"),
            )
        self.app.push_screen(SymbolSearch(), done)

    def _on_watch_added(self, item: dict, sym: str) -> None:
        self.add_watch_row(item)
        self.status(f"✓ Added {sym} to watchlist — press 2 to view")
        self.log_activity(f"+ Added {sym} to watchlist")
        self.update_dashboard()

    def action_remove(self) -> None:
        item = self.selected("watch")
        if not item:
            self.status("Select a symbol in Watchlist first", True)
            return
        k = self.feed_key(item)
        self.watchlist_service.remove(
            item,
            on_success=lambda sym: self._on_watch_removed(k, sym),
            on_missing=lambda sym: self.status(f"{sym} not found in watchlist", True),
        )

    def _on_watch_removed(self, key: str, sym: str) -> None:
        try:
            self.query_one("#t-watch", DataTable).remove_row(key)
        except Exception:
            pass
        self.status(f"✓ Removed {sym} from watchlist")
        self.log_activity(f"− Removed {sym} from watchlist")
        self.update_dashboard()

    # ── Order actions ─────────────────────────────────────────────────────────
    def action_trade(self, side: str) -> None:
        tab  = self.active_tab()
        item = None

        if tab in ("watch", "dashboard"):
            item = self.selected("watch")
        elif tab in ("orders", "positions", "holdings"):
            row = self.selected(tab)
            if row:
                item = self.row_to_info(row) if tab == "orders" else {
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
        return OrderService.row_to_info(r)

    def action_modify(self) -> None:
        row = self.selected("orders") if self.active_tab() == "orders" else None
        if row:
            self.open_ticket(self.row_to_info(row), "MODIFY")

    def open_ticket(self, info: dict, mode: str) -> None:
        if not self.order_service:
            self.order_service = OrderService(self.app.client)
        self.order_service.open_ticket(
            self,
            info,
            mode,
            on_activity=lambda m: self.post(self.log_activity, m),
            on_done=lambda: self.post(self.load, "orders"),
        )

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
        body = Text(f"{len(ids)} open order(s) will be cancelled:\n", style=f"bold {C_AMBER}")
        body.append(", ".join(ids), style=C_MUTED)
        self.confirm("Cancel ALL Open Orders", body, lambda: self.cancel_ids(ids))

    def action_panic_flatten(self) -> None:
        """Emergency Panic Flatten: Cancel ALL open orders and square off open intraday positions."""
        open_orders = [str(get(r, "orderId")) for r in self.data.get("orders", []) if is_open_order(r)]
        open_positions = [
            r for r in self.data.get("positions", [])
            if int(get(r, "netQty", default=0)) != 0
        ]
        if not open_orders and not open_positions:
            self.status("No active orders or open positions to flatten", True)
            return

        body = Text()
        body.append("🚨 EMERGENCY PANIC FLATTEN REQUESTED\n\n", style=f"bold {C_RED}")
        if open_orders:
            body.append(f"• Open Orders to Cancel ({len(open_orders)}): ", style=f"bold {C_AMBER}")
            body.append(f"{', '.join(open_orders[:6])}{'...' if len(open_orders) > 6 else ''}\n", style=C_MUTED)
        if open_positions:
            body.append(f"• Open Positions to Square Off ({len(open_positions)}):\n", style=f"bold {C_RED}")
            for pos in open_positions[:5]:
                sym = get(pos, "tradingSymbol")
                net_q = int(get(pos, "netQty", default=0))
                side = "SELL" if net_q > 0 else "BUY"
                body.append(f"   {sym}: Net {net_q:+d} → {side} {abs(net_q)} @ MKT\n", style=C_MUTED)
        body.append("\nAre you ABSOLUTELY SURE you want to execute panic flatten?", style="bold white")

        def do_flatten() -> None:
            self.log_activity("🚨 PANIC FLATTEN EXECUTED — Cancelling all orders & squaring off positions")
            self._execute_panic_flatten(open_orders, open_positions)

        self.confirm("🚨 PANIC FLATTEN CONFIRMATION", body, do_flatten)

    @work(thread=True)
    def _execute_panic_flatten(self, order_ids: list[str], positions: list[dict]) -> None:
        if not self.order_service:
            self.order_service = OrderService(self.app.client)
        # 1. Cancel all open orders
        if order_ids:
            self.order_service.cancel_many(
                self,
                order_ids,
                on_activity=lambda m: self.post(self.log_activity, m),
            )
        # 2. Square off each open position
        for pos in positions:
            net_q = int(get(pos, "netQty", default=0))
            if net_q == 0:
                continue
            opp_side = "S" if net_q > 0 else "B"
            close_qty = abs(net_q)
            sq_params = {
                "tradingSymbol": get(pos, "tradingSymbol"),
                "exchange": get(pos, "exchange", default="NC"),
                "scripCode": get(pos, "scripCode"),
                "transactionType": opp_side,
                "quantity": close_qty,
                "price": 0.0,
                "priceType": "MARKET",
                "productType": get(pos, "productType", default="INVESTMENT"),
                "requestType": "NEW",
            }
            try:
                self.order_service._submit(
                    self,
                    sq_params,
                    on_activity=lambda m: self.post(self.log_activity, m),
                )
            except Exception as e:
                self.post(self.log_activity, f"✗ Square-off failed for {get(pos, 'tradingSymbol')}: {e}")
        self.post(self.refresh_all_data)
        self.post(self.status, "✓ Panic flatten completed — all orders cancelled, square-off submitted")

    @work(thread=True)
    def cancel_ids(self, ids: list[str]) -> None:
        if not self.order_service:
            self.order_service = OrderService(self.app.client)
        self.order_service.cancel_many(
            self,
            ids,
            on_activity=lambda m: self.post(self.log_activity, m),
            on_done=lambda: self.post(self.load, "orders"),
        )

    @work(thread=True)
    def send(self, p: dict) -> None:
        if not self.order_service:
            self.order_service = OrderService(self.app.client)
        self.order_service._submit(
            self,
            p,
            on_activity=lambda m: self.post(self.log_activity, m),
            on_done=lambda: self.post(self.load, "orders"),
        )

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
        self.market_service.handle_ws(msg)

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

    def _on_tick_update(
        self, key: str, tick: dict, prev_ltp: float | None, new_ltp: float | None
    ) -> None:
        try:
            table = self.query_one("#t-watch", DataTable)
            st_label, _ = self.quotes.staleness_status(key)
            is_stale = st_label.startswith("STALE")
            sym = str(tick.get("tradingSymbol") or tick.get("tsym") or "")
            if not sym:
                it = next((w for w in self.watch if self.feed_key(w) == key), None)
                if it:
                    sym = scrip_label(it)
            update_watch_row(
                table, key, tick, prev_ltp, new_ltp,
                is_stale=is_stale, symbol_name=sym if sym else None
            )
            # Evaluate price alerts
            if sym and new_ltp is not None and new_ltp > 0:
                self.alert_engine.evaluate_quote(sym, new_ltp)
        except Exception:
            pass

    def on_tick(self, d: dict) -> None:
        self.market_service._process_tick(d)
