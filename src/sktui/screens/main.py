"""Redesigned professional trading terminal screen for SKTUI.

Clean, terminal-first, keyboard-driven workspace layout:
- TopStatusBar: Operational context, account, feed health, alerts, session, indices
- LeftPanel: Watchlist table + Market Scanner (compact, high-priority columns)
- CenterPanel: Symbol Focus hero, metrics, live braille chart, day stats
- RightPanel: Order ticket preview, open positions, active orders, risk governance
- BottomRow: Feed & audit status log + Command bar with slash dispatch
"""
from __future__ import annotations

import json
import random
import time
from datetime import datetime
from typing import Any

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    DataTable, Footer, Header, Input, RichLog, Static,
)

from sktui import api
from sktui.chart import render_chart
from sktui.config import (
    ALERTS_FILE, C_AMBER, C_CYAN, C_DIM, C_GREEN, C_MUTED, C_PANEL, C_RED,
    C_SUBTLE, C_TEXT, DATA, PANE_KEYS, SESSION_FILE, WATCH_FILE,
)
from sktui.screens.login import LoginScreen
from sktui.screens.modals import (
    AlertsModal, AuditTrailModal, Confirm, DetailScreen, FocusModal, HelpScreen,
    HistoryScreen, OrderTicket, PortfolioAnalyticsModal, ProductsScreen, QuoteScreen,
    ReplayModal, RiskScreen, ScannerModal, SymbolSearch, SystemStatusScreen, WhatIfScreen,
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
from sktui.ui.widgets.market_radar import MarketRadarSidebar
from sktui.ui.widgets.market_scanner import MarketScannerWidget
from sktui.ui.widgets.order_action import OrderActionWidget
from sktui.ui.widgets.risk_summary import RiskSummaryWidget
from sktui.ui.widgets.symbol_focus import SymbolFocusPanel
from sktui.ui.widgets.watchlist_table import WATCH_COLS, add_watch_row, update_watch_row
from sktui.utils import (
    compact_number, compact_price, fill_table, format_change, format_volume,
    get, get_public_ip, human, is_open_order, render_alert_badge, safe_float,
    scrip_label, sign_style, status_text, truncate_symbol,
)

# ── Re-exports for backward compatibility ────────────────────────────────────
__all__ = [
    "MainScreen",
    "TopStatusBar",
    "WatchlistPanel",
    "SymbolFocusPanel",
    "TradeRiskPanel",
    "StatusLogPanel",
    "CommandBar",
    "MarketRadarSidebar",
    "MarketScannerWidget",
    "OrderActionWidget",
    "RiskSummaryWidget",
    "WATCH_COLS",
    "DEFAULT_WATCH",
]

ORDER_COLS = [
    ("orderId",       " Order ID"),      ("exchange",      "Exch"),
    ("tradingSymbol", " Symbol"),        ("buySell",       "Side"),
    ("orderQty",      "   Qty"),         ("execQty",       " Filled"),
    ("orderPrice",    "    Price"),      ("execPrice",     "  Avg Fill"),
    ("orderStatus",   " Status"),        ("priceType",     " Type"),
]
POS_COLS = [
    ("tradingSymbol", " Symbol"),   ("exchange",   "Exch"),
    ("productType",   " Product"),  ("netQty",     "  Net Q"),
    ("avgPrice",      "  Avg Px"),  ("bpl",        "  Booked P/L"),
    ("mtm",           "  MTM P/L"),
]
HOLD_COLS = [
    ("tradingSymbol", " Symbol"),      ("exchange",       "Exch"),
    ("aval",          "  Available"),  ("holdPrice",      "  Hold Px"),
]
COLS = {"orders": ORDER_COLS, "positions": POS_COLS, "holdings": HOLD_COLS}


# ── Top Status Bar ────────────────────────────────────────────────────────────
class TopStatusBar(Static):
    """Compact operational header: session, market status, feed health, whitelisting IP, alerts."""

    def compose(self) -> ComposeResult:
        yield Static("", id="account")
        yield Static("", id="indices-bar")
        yield Static("", id="top-status-text")


# ── Left Panel: Watchlist & Scanner ───────────────────────────────────────────
class WatchlistPanel(Static):
    """Left pane: Watchlist table and compact market scanner."""

    def compose(self) -> ComposeResult:
        yield Static("  WATCHLIST  [1]", classes="panel-header", markup=False)
        yield DataTable(id="t-watch", cursor_type="row")
        yield Static("  MARKET SCANNER  [4]", classes="panel-header", markup=False)
        yield DataTable(id="t-scanner", cursor_type="row")
        # Legacy widget reference for compatibility
        yield MarketScannerWidget(id="market-scanner-box", classes="hidden-data")


# ── Center Panel: Selected Symbol Focus & Chart ───────────────────────────────
# (SymbolFocusPanel imported from sktui.ui.widgets.symbol_focus)



# ── Right Panel: Trade Execution & Risk Governance ───────────────────────────
class TradeRiskPanel(Static):
    """Right pane: Order ticket summary, desk execution tables (Orders, Positions, Holdings, Funds), risk governance."""

    def compose(self) -> ComposeResult:
        yield Static("  ORDER TICKET PREVIEW", classes="panel-header", markup=False)
        yield Static("", id="order-preview")
        yield Static(
            "  DESK:  ● Orders [3]  │  Positions [4]  │  Holdings [5]  │  Funds [6]",
            classes="panel-header", id="desk-header", markup=False,
        )
        yield DataTable(id="t-orders", cursor_type="row")
        yield DataTable(id="t-positions", cursor_type="row")
        yield DataTable(id="t-holdings", cursor_type="row")
        yield DataTable(id="t-funds", cursor_type="row")
        yield Static("  RISK GOVERNANCE", classes="panel-header", markup=False)
        yield Static("", id="risk-summary")
        yield RichLog(id="activity-log", max_lines=500, wrap=True, markup=False, classes="hidden-data")
        yield RiskSummaryWidget(id="risk-summary-box", classes="hidden-data")


# ── Status / Log Panel ────────────────────────────────────────────────────────
class StatusLogPanel(Static):
    """Lower left pane: feed health, latency, stale tick warnings, and audit trail."""

    def compose(self) -> ComposeResult:
        yield Static("  FEED HEALTH & AUDIT STREAM  [7]", classes="panel-header", markup=False)
        yield RichLog(id="status-log", max_lines=200, wrap=True, markup=False)
        yield RichLog(id="feedlog", max_lines=200, wrap=True, markup=False, classes="hidden-data")


# ── Command Bar ───────────────────────────────────────────────────────────────
class CommandBar(Static):
    """Lower right pane: Keyboard command input area and autocomplete chips."""

    def compose(self) -> ComposeResult:
        yield Static("  COMMAND LINE  —  [/]", classes="panel-header", markup=False)
        yield Static("", id="cmd-suggestions")
        with Horizontal(id="cmd-bar"):
            yield Static("  /  ", id="cmd-prefix", markup=False)
            yield Input(
                placeholder="command  —  /buy, /sell, /cancel, /chart, /risk, /status, /help …",
                id="cmd-input",
            )
        yield Static("", id="status")
        yield Static("", id="pnl-strip", classes="hidden-data")



# ── Main Workspace Screen ─────────────────────────────────────────────────────
class MainScreen(Screen):
    BINDINGS = [
        Binding("1",            "tab('watch')",     "Watch [1]"),
        Binding("2",            "tab('symbol')",    "Symbol [2]"),
        Binding("3",            "tab('orders')",    "Orders [3]"),
        Binding("4",            "tab('positions')", "Positions [4]"),
        Binding("5",            "tab('holdings')",  "Holdings [5]"),
        Binding("6",            "tab('funds')",     "Funds [6]"),
        Binding("7",            "tab('activity')",  "Activity [7]"),
        Binding("b",            "trade('B')",       "Buy"),
        Binding("s",            "trade('S')",       "Sell"),
        Binding("m",            "modify",           "Modify"),
        Binding("x",            "cancel_order",     "Cancel"),
        Binding("X",            "cancel_all",       "Cancel all", show=False),
        Binding("K",            "panic_flatten",    "Flatten"),
        Binding("f",            "toggle_focus",     "Focus"),
        Binding("r",            "refresh_all",      "Refresh"),
        Binding("c",            "chart",            "Chart"),
        Binding("i",            "detail",           "Info"),
        Binding("question_mark","quote",            "Quote",  show=False),
        Binding("p",            "products",         "Market"),
        Binding("d",            "toggle_log",       "Feed",   show=False),
        Binding("a",            "add",              "Add"),
        Binding("delete",       "remove",           "Del"),
        Binding("slash",        "focus_cmd",        "Command", show=False),
        Binding("f1",           "help",             "Help",   show=False),
        Binding("ctrl+l",       "logout",           "Logout"),
        Binding("q",            "app.quit",         "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.selected_symbol: dict | None = None
        self._current_desk_tab: str = "orders"
        self.watchlist_store = WatchlistStore(WATCH_FILE)
        self.watchlist_service = WatchlistService(self.watchlist_store)
        self.watch: list[dict] = self.watchlist_store.items
        self.quotes = QuoteStore()
        self.market_state = api.MarketState()
        self.market_service = MarketService(self.quotes, self.watchlist_store)
        self.alert_engine = AlertEngine(ALERTS_FILE)
        self.focus_mode: bool = False
        self.order_service: OrderService | None = None
        self.status_service: StatusService | None = None

        self.data: dict[str, list[dict]] = {"orders": [], "positions": [], "holdings": [], "funds": []}
        self.feed: api.Feed | None = None
        self._ack_pending = False
        self.public_ip: str = "Fetching…"

    @property
    def positions(self) -> list[dict]:
        return self.data.get("positions", [])

    @property
    def orders(self) -> list[dict]:
        return self.data.get("orders", [])

    @property
    def holdings(self) -> list[dict]:
        return self.data.get("holdings", [])

    @property
    def funds(self) -> list[dict]:
        return self.data.get("funds", [])

    @property
    def _tick_history(self) -> dict[str, list[float]]:
        return self.quotes.tick_history

    # ── Composition ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield TopStatusBar(id="top-status")

        with Horizontal(id="workspace"):
            with Vertical(id="left-pane", classes="pane"):
                yield WatchlistPanel(id="watchlist-panel")
            with Vertical(id="center-pane", classes="pane"):
                yield SymbolFocusPanel(id="symbol-focus-panel")
            with Vertical(id="right-pane", classes="pane"):
                yield TradeRiskPanel(id="trade-panel")

        with Horizontal(id="bottom-row"):
            with Vertical(id="status-pane", classes="pane tiny"):
                yield StatusLogPanel(id="status-panel")
            with Vertical(id="command-pane", classes="pane tiny"):
                yield CommandBar(id="command-panel")

        yield Footer()

    # ── Mount & Initialization ────────────────────────────────────────────────
    def on_mount(self) -> None:
        c = self.app.client
        self.order_service = OrderService(c)
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

        # 1. Setup Watchlist Table
        t_watch = self.query_one("#t-watch", DataTable)
        for key, label in WATCH_COLS:
            t_watch.add_column(label, key=key)
        for item in self.watch:
            self.add_watch_row(item)

        # 2. Setup Scanner Table
        t_scan = self.query_one("#t-scanner", DataTable)
        t_scan.add_column("Type", key="type")
        t_scan.add_column("Symbol", key="symbol")
        t_scan.add_column("Value", key="value")
        t_scan.add_column("Trend", key="trend")

        # 3. Setup Positions Table
        t_pos = self.query_one("#t-positions", DataTable)
        for key, label in POS_COLS:
            t_pos.add_column(label, key=key)

        # 4. Setup Orders Table
        t_ord = self.query_one("#t-orders", DataTable)
        for key, label in ORDER_COLS:
            t_ord.add_column(label, key=key)

        # 5. Setup Holdings & Funds Tables (for compatibility)
        t_hold = self.query_one("#t-holdings", DataTable)
        for key, label in HOLD_COLS:
            t_hold.add_column(label, key=key)
        t_funds = self.query_one("#t-funds", DataTable)
        t_funds.add_column("Field", key="field")
        t_funds.add_column("Value", key="value")

        # Initialize active desk tab (Orders visible by default)
        self._switch_desk_tab("orders")

        # Set default selected symbol
        if self.watch:
            self.selected_symbol = self.watch[0]

        # Initial render of panels
        self._update_top_status()
        self._update_symbol_focus(self.selected_symbol)
        self._update_trade_panel(self.selected_symbol)
        self._update_scanner_table()
        self._fetch_public_ip()

        self.refresh_all_data()

        # Recurring background updates
        self.set_interval(1.0, self._update_top_status)
        self.set_interval(2.0, self._update_scanner_table)
        self.set_interval(1.5, self._simulate_tick)
        self.set_interval(20.0, self.refresh_active)

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
        msg = f"🔔 ALERT TRIGGERED: {alert.symbol} {alert.condition} {alert.target_value:,.2f} (LTP: ₹{ltp:,.2f})"
        self.app.notify(msg, severity="warning", timeout=10)
        self.log_activity(msg)

    # ── Top Status Bar Updating ───────────────────────────────────────────────
    def _update_top_status(self) -> None:
        c = getattr(self.app, "client", None)
        mode = "PAPER" if getattr(c, "paper", False) else "LIVE"
        acct_name = getattr(c, "full_name", "") or getattr(c, "login_id", "") or "UNSET"
        badge_text, badge_color = self.quotes.feed_badge() if hasattr(self.quotes, "feed_badge") else ("● LIVE", C_GREEN)
        alerts_count = len(self.alert_engine.alerts) if hasattr(self, "alert_engine") else 0

        # Session calculation (9:15 to 15:30 IST)
        now = datetime.now()
        is_open = (9 <= now.hour < 15) or (now.hour == 15 and now.minute <= 30)
        session_text = "OPEN" if is_open else "CLOSED"
        session_col = C_GREEN if is_open else C_AMBER

        # Update TopStatusBar text
        t = Text()
        t.append(f" {mode} ", style="bold white on #0a1f36" if mode == "LIVE" else f"bold white on #1e293b")
        t.append(f"  Account: {acct_name}", style="bold white")
        t.append("  |  ", style=C_SUBTLE)
        t.append("Session: ", style=C_MUTED)
        t.append(f"{session_text}", style=f"bold {session_col}")
        t.append("  |  ", style=C_SUBTLE)
        t.append(f"IP: {self.public_ip}", style=C_MUTED)
        t.append("  |  ", style=C_SUBTLE)
        t.append(f"Feed: {badge_text}", style=f"bold {badge_color}")
        t.append("  |  ", style=C_SUBTLE)
        t.append(f"Alerts: {alerts_count}", style=f"bold {C_CYAN}" if alerts_count > 0 else C_MUTED)
        t.append("  |  ", style=C_SUBTLE)
        t.append("F1 Help  /  Keys: b/s/m/x/c/r  /  Panes: 1-6", style=C_SUBTLE)

        try:
            self.query_one("#top-status-text", Static).update(t)
        except Exception:
            pass

        # Update backward-compatible widgets
        try:
            if self.status_service:
                w = self.app.size.width if self.app else 120
                self.query_one("#account", Static).update(
                    self.status_service.render_account_bar(self.public_ip, quote_store=self.quotes, width=w)
                )
                raw = getattr(self.app, "raw_ticks", {})
                self.query_one("#indices-bar", Static).update(
                    self.status_service.render_indices_bar(raw, width=w)
                )
        except Exception:
            pass

    @work(thread=True)
    def _fetch_public_ip(self) -> None:
        ip = get_public_ip()
        self.public_ip = ip
        self.app.public_ip = ip
        self.post(self._update_top_status)

    # ── Center & Right Panels Updating ────────────────────────────────────────
    def _update_symbol_focus(self, item: dict | None = None) -> None:
        if item is None:
            item = self.selected_symbol or (self.watch[0] if self.watch else None)
        if not item:
            return
        self.selected_symbol = item

        feed_key = self.feed_key(item) if "scripCode" in item else ""
        quote = self.quotes.get(feed_key) if feed_key else {}
        sym = item.get("tradingSymbol")
        pos = next((p for p in self.data.get("positions", []) if get(p, "tradingSymbol") == sym), None)
        open_orders = sum(
            1 for o in self.data.get("orders", [])
            if get(o, "tradingSymbol") == sym and is_open_order(o)
        )
        stale_status = self.quotes.staleness_status(feed_key) if feed_key else ("--", C_SUBTLE)
        tick_hist = self.quotes.tick_history.get(feed_key, [])
        width = self.app.size.width if self.app else 120

        try:
            panel = self.query_one("#symbol-focus-panel", SymbolFocusPanel)
            panel.update_context(
                item=item,
                quote=quote,
                position=pos,
                open_orders=open_orders,
                stale_status=stale_status,
                tick_history=tick_hist,
                width=width,
            )
        except Exception:
            pass

        self._update_trade_panel(item)

    def _update_trade_panel(self, item: dict | None = None) -> None:
        it = item or self.selected_symbol or (self.watch[0] if self.watch else None)
        sym = it.get("tradingSymbol", "NONE") if it else "NONE"
        exch = it.get("exchange", "NC") if it else "NC"
        feed_key = self.feed_key(it) if it and "scripCode" in it else ""
        quote = self.quotes.get(feed_key) if feed_key else {}
        ltp = quote.get("ltp")

        # 1. Order ticket preview
        preview_text = Text()
        preview_text.append(f"PREPARED: BUY 100 × {sym} ({exch})\n", style=f"bold {C_GREEN}")
        if ltp:
            est_val = ltp * 100
            preview_text.append(f"LTP: ₹{ltp:,.2f}  |  Est. Value: ₹{est_val:,.2f}\n", style=C_TEXT)
        else:
            preview_text.append("Price: MARKET  |  Validity: GFD\n", style=C_MUTED)
        preview_text.append("Order Type: NORMAL  |  Validity: GFD\n", style=C_SUBTLE)
        preview_text.append("Keys: [b] Buy  [s] Sell  [m] Modify  [x] Cancel  [K] Flatten", style=f"bold {C_CYAN}")

        try:
            self.query_one("#order-preview", Static).update(preview_text)
        except Exception:
            pass

        # 2. Risk summary
        positions = self.data.get("positions", [])
        orders = self.data.get("orders", [])
        gross_exp = sum(
            abs(int(get(p, "netQty", default=0))) * safe_float(get(p, "avgPrice", default=0))
            for p in positions
        )
        net_exp = sum(
            int(get(p, "netQty", default=0)) * safe_float(get(p, "avgPrice", default=0))
            for p in positions
        )
        total_pnl = sum(safe_float(get(p, "bpl", default=0)) + safe_float(get(p, "mtm", default=0)) for p in positions)
        open_orders_cnt = sum(1 for o in orders if is_open_order(o))

        risk_text = Text()
        risk_text.append(f"Net Exp: ₹{net_exp:,.2f}  |  Gross: ₹{gross_exp:,.2f}\n", style=C_TEXT)
        risk_text.append(f"Daily P/L: ₹{total_pnl:+,.2f}  |  Active Orders: {open_orders_cnt}\n", style=sign_style(total_pnl))
        risk_text.append("Risk Status: NOMINAL  |  Fat-Finger Check: ACTIVE", style=f"bold {C_GREEN}")

        try:
            self.query_one("#risk-summary", Static).update(risk_text)
        except Exception:
            pass

    def _update_scanner_table(self) -> None:
        t_scan = self.query_one("#t-scanner", DataTable)
        rows: list[dict] = []
        raw_ticks = getattr(self.app, "raw_ticks", {})

        # Top gainers / movers from raw_ticks and watch
        scored = []
        for it in self.watch:
            k = self.feed_key(it)
            q = raw_ticks.get(k, {})
            pct = safe_float(q.get("perChange") or q.get("pct"))
            vol = safe_float(q.get("qty") or q.get("vol"))
            sym = it.get("tradingSymbol", "")
            scored.append((pct, vol, sym))

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            top_gain = scored[0]
            top_loss = scored[-1]
            rows.append({
                "type": "GAINER", "symbol": top_gain[2],
                "value": f"{top_gain[0]:+.2f}%", "trend": "▲ Bullish",
            })
            if len(scored) > 1 and top_loss[0] < 0:
                rows.append({
                    "type": "LOSER", "symbol": top_loss[2],
                    "value": f"{top_loss[0]:+.2f}%", "trend": "▼ Bearish",
                })
            # Most active volume
            scored_vol = sorted(scored, key=lambda x: x[1], reverse=True)
            if scored_vol and scored_vol[0][1] > 0:
                rows.append({
                    "type": "ACTIVE", "symbol": scored_vol[0][2],
                    "value": compact_number(scored_vol[0][1]), "trend": "● Volume",
                })

        # Fill table
        if rows:
            fill_table(t_scan, rows, [("type", "Type"), ("symbol", "Symbol"), ("value", "Value"), ("trend", "Trend")])

    # ── Watchlist / Tick Wiring ───────────────────────────────────────────────
    def add_watch_row(self, item: dict) -> None:
        t = self.query_one("#t-watch", DataTable)
        q = self.market_service.initial_quote(item)
        add_watch_row(t, item, q)
        self.selected_symbol = item
        self._update_symbol_focus(item)


    def _simulate_tick(self) -> None:
        if not getattr(self.app, "enable_feed", True):
            return
        if not self.watch:
            return
        item = random.choice(self.watch)
        self.market_service.simulate_tick(item)


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
            # Check price alerts
            if sym and new_ltp is not None and new_ltp > 0:
                self.alert_engine.evaluate_quote(sym, new_ltp)

            # Center symbol panel immediate refresh if matching selected symbol
            if self.selected_symbol and self.feed_key(self.selected_symbol) == key:
                self._update_symbol_focus(self.selected_symbol)
        except Exception:
            pass

    # ── Row Selection Events ──────────────────────────────────────────────────
    @on(DataTable.RowHighlighted, "#t-watch")
    def _on_watch_highlighted(self, event: DataTable.RowHighlighted) -> None:
        try:
            key = event.row_key.value
            item = next((w for w in self.watch if self.feed_key(w) == key), None)
            if item:
                self._update_symbol_focus(item)
        except Exception:
            pass

    @on(DataTable.RowHighlighted, "#t-orders")
    def _on_orders_highlighted(self, event: DataTable.RowHighlighted) -> None:
        try:
            orders = self.data.get("orders", [])
            idx = event.cursor_row
            if 0 <= idx < len(orders):
                item = self.row_to_info(orders[idx])
                self._update_symbol_focus(item)
        except Exception:
            pass

    @on(DataTable.RowHighlighted, "#t-positions")
    def _on_positions_highlighted(self, event: DataTable.RowHighlighted) -> None:
        try:
            pos = self.data.get("positions", [])
            idx = event.cursor_row
            if 0 <= idx < len(pos):
                item = {
                    "tradingSymbol": get(pos[idx], "tradingSymbol"),
                    "exchange": get(pos[idx], "exchange", default="NC"),
                    "scripCode": get(pos[idx], "scripCode", default=None),
                }
                self._update_symbol_focus(item)
        except Exception:
            pass

    @on(DataTable.RowHighlighted, "#t-holdings")
    def _on_holdings_highlighted(self, event: DataTable.RowHighlighted) -> None:
        try:
            holds = self.data.get("holdings", [])
            idx = event.cursor_row
            if 0 <= idx < len(holds):
                item = {
                    "tradingSymbol": get(holds[idx], "tradingSymbol"),
                    "exchange": get(holds[idx], "exchange", default="NC"),
                    "scripCode": get(holds[idx], "scripCode", default=None),
                }
                self._update_symbol_focus(item)
        except Exception:
            pass

    # ── Key Navigation / Panes ────────────────────────────────────────────────
    def action_focus_watchlist(self) -> None:
        self.query_one("#t-watch", DataTable).focus()

    def action_focus_symbol(self) -> None:
        self.query_one("#symbol-focus-panel", SymbolFocusPanel).focus()

    def action_focus_trade(self) -> None:
        self.query_one("#order-preview", Static).focus()

    def action_focus_scanner(self) -> None:
        self.query_one("#t-scanner", DataTable).focus()

    def action_focus_alerts(self) -> None:
        self.action_show_alerts()

    def action_focus_logs(self) -> None:
        self.query_one("#status-log", RichLog).focus()

    def action_focus_cmd(self) -> None:
        self.query_one("#cmd-input", Input).focus()

    def _switch_desk_tab(self, tab: str) -> None:
        """Switch active desk execution table (Orders, Positions, Holdings, Funds) in right pane."""
        tab_lower = (tab or "").lower()
        if tab_lower in ("trade", "order"):
            tab_lower = "orders"
        elif tab_lower in ("position", "pos"):
            tab_lower = "positions"
        elif tab_lower in ("holding", "hold"):
            tab_lower = "holdings"
        elif tab_lower in ("fund",):
            tab_lower = "funds"

        self._current_desk_tab = tab_lower
        tables = {
            "orders": "#t-orders",
            "positions": "#t-positions",
            "holdings": "#t-holdings",
            "funds": "#t-funds",
        }
        labels = [
            ("orders", "Orders [3]"),
            ("positions", "Positions [4]"),
            ("holdings", "Holdings [5]"),
            ("funds", "Funds [6]"),
        ]
        target_table = None
        for name, selector in tables.items():
            try:
                tbl = self.query_one(selector, DataTable)
                is_active = (name == tab_lower)
                tbl.display = is_active
                if is_active:
                    target_table = tbl
            except Exception:
                pass

        if target_table:
            target_table.focus()

        hdr_text = Text()
        hdr_text.append("  DESK:  ", style=f"bold {C_CYAN}")
        for idx, (name, label) in enumerate(labels):
            if idx > 0:
                hdr_text.append("  │  ", style=C_SUBTLE)
            if name == tab_lower:
                hdr_text.append(f"● {label}", style="bold white on #0d1e38")
            else:
                hdr_text.append(label, style=C_MUTED)

        try:
            self.query_one("#desk-header", Static).update(hdr_text)
        except Exception:
            pass

    def action_tab(self, tab: str) -> None:
        """Switch active view / desk table and focus according to 1-7 shortcuts."""
        t = (tab or "").lower()
        if t in ("watch", "watchlist", "dashboard"):
            self.action_focus_watchlist()
            self.status("Selected Watchlist [1]")
            self.log_activity("📑 View: Watchlist [1]")
        elif t in ("symbol", "center", "chart", "focus"):
            self.action_focus_symbol()
            self.status("Selected Symbol Focus & Chart [2]")
            self.log_activity("📑 View: Symbol Focus & Chart [2]")
        elif t in ("orders", "positions", "holdings", "funds", "trade"):
            self._switch_desk_tab(t)
            self.status(f"Selected Desk: {t.title()}")
            self.log_activity(f"📑 Desk: {t.title()}")
        elif t in ("activity", "logs", "log", "feed"):
            self.action_focus_logs()
            self.status("Selected Activity & Audit Log [7]")
            self.log_activity("📑 View: Activity Log [7]")

    def active_tab(self) -> str:
        focused = self.focused
        if focused and getattr(focused, "id", ""):
            f_id = str(focused.id)
            if "order" in f_id:
                return "orders"
            if "pos" in f_id:
                return "positions"
            if "hold" in f_id:
                return "holdings"
            if "fund" in f_id:
                return "funds"
            if "watch" in f_id:
                return "watch"
        return getattr(self, "_current_desk_tab", "orders")

    def selected(self, tab: str | None = None) -> dict | None:
        if not tab or tab in ("dashboard", "watch"):
            try:
                t = self.query_one("#t-watch", DataTable)
                if t.row_count == 0:
                    return None
                key = t.coordinate_to_cell_key(t.cursor_coordinate).row_key.value
                return next((w for w in self.watch if self.feed_key(w) == key), None)
            except Exception:
                return self.selected_symbol or (self.watch[0] if self.watch else None)
        try:
            t = self.query_one(f"#t-{tab}", DataTable)
            if t.row_count == 0:
                return None
            rows = self.data.get(tab, [])
            if not rows:
                return None
            return rows[t.cursor_row] if (0 <= t.cursor_row < len(rows)) else rows[0]
        except Exception:
            return None


    # ── Command Bar Dispatch ──────────────────────────────────────────────────
    ALL_COMMANDS = [
        "/watchlist", "/symbol", "/orders", "/positions", "/holdings",
        "/funds", "/buy", "/sell", "/cancel", "/modify", "/chart",
        "/quote", "/add", "/remove", "/products", "/alert", "/alerts",
        "/flatten", "/risk", "/whatif", "/audit", "/analytics", "/status",
        "/refresh", "/scanner", "/focus", "/replay", "/help", "/kill", "/logout",
    ]

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

        # Parameterized /alert command
        if raw.lower().startswith("/alert ") or raw.lower().startswith("alert "):
            parsed = parse_alert_command(raw)
            if parsed:
                sym, cond, val = parsed
                self.alert_engine.add_alert(sym, cond, val)
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
            "/watchlist":  self.action_focus_watchlist,
            "/symbol":     self.action_focus_symbol,
            "/orders":     lambda: self.action_tab("orders"),
            "/positions":  lambda: self.action_tab("positions"),
            "/holdings":   lambda: self.action_tab("holdings"),
            "/funds":      lambda: self.action_tab("funds"),
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
            "/replay":     self.action_replay,
            "/flatten":    self.action_panic_flatten,
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

    # ── Data Loading & Row Display ────────────────────────────────────────────
    def refresh_all_data(self) -> None:
        for tab in ("orders", "positions", "holdings", "funds"):
            self.load(tab)

    def refresh_active(self) -> None:
        self.load("orders")
        self.load("positions")

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
            COLS.get(tab) or [("segment", "Segment"), ("field", "Field"), ("value", "Value")]
        )
        n = len(rows)
        self.status(
            f"{tab.capitalize()}: {n} record{'s' if n != 1 else ''}"
            if n else f"{tab.capitalize()}: no records found"
        )
        self._update_trade_panel()

    # ── Order Actions & Tickets ───────────────────────────────────────────────
    def action_trade(self, side: str, override_item: dict | None = None) -> None:
        item = override_item
        if not item:
            tab = self.active_tab()
            if tab == "orders":
                row = self.selected("orders")
                if row:
                    item = self.row_to_info(row)
            elif tab == "positions":
                row = self.selected("positions")
                if row:
                    item = {
                        "tradingSymbol": get(row, "tradingSymbol"),
                        "scripCode": get(row, "scripCode", default=None),
                        "exchange": get(row, "exchange", default="NC"),
                    }
        if not item:
            item = self.selected("watch") or self.selected_symbol or (self.watch[0] if self.watch else None)
        if not item:
            self.status("Select an instrument in Watchlist / Orders first", True)
            return

        info = dict(item, side=side)
        ltp = getattr(self.app, "raw_ticks", {}).get(
            self.feed_key(item) if "scripCode" in item else "", {}
        ).get("ltp")
        if ltp:
            info["price"] = ltp
        self.open_ticket(info, "NEW")


    @staticmethod
    def row_to_info(r: dict) -> dict:
        return OrderService.row_to_info(r)

    def action_modify(self) -> None:
        row = self.selected("orders")
        if row:
            self.open_ticket(self.row_to_info(row), "MODIFY")
        else:
            self.status("Select an order in Orders table first", True)

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
            lambda ok: action() if ok else None
        )

    def action_cancel_order(self) -> None:
        row = self.selected("orders")
        if not row:
            self.status("Select an order to cancel in Active Orders", True)
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
        if order_ids:
            self.order_service.cancel_many(
                self, order_ids, on_activity=lambda m: self.post(self.log_activity, m)
            )
        for pos in positions:
            net_q = int(get(pos, "netQty", default=0))
            if net_q == 0:
                continue
            opp_side = "S" if net_q > 0 else "B"
            sq_params = {
                "tradingSymbol": get(pos, "tradingSymbol"),
                "exchange": get(pos, "exchange", default="NC"),
                "scripCode": get(pos, "scripCode"),
                "transactionType": opp_side,
                "quantity": abs(net_q),
                "price": 0.0,
                "priceType": "MARKET",
                "productType": get(pos, "productType", default="INVESTMENT"),
                "requestType": "NEW",
            }
            try:
                self.order_service._submit(
                    self, sq_params, on_activity=lambda m: self.post(self.log_activity, m)
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
            self, ids, on_activity=lambda m: self.post(self.log_activity, m),
            on_done=lambda: self.post(self.load, "orders"),
        )

    # ── Watchlist Management ──────────────────────────────────────────────────
    def action_add(self) -> None:
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
        self.status(f"✓ Added {sym} to watchlist")
        self.log_activity(f"+ Added {sym} to watchlist")
        self.selected_symbol = item
        self._update_symbol_focus(item)

    def action_remove(self) -> None:
        item = self.selected_symbol or self.selected("watch")
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
        if self.watch:
            self.selected_symbol = self.watch[0]
            self._update_symbol_focus(self.selected_symbol)

    # ── Modals & Drawers ──────────────────────────────────────────────────────
    def action_chart(self) -> None:
        item = (
            self.selected_symbol
            or self.selected(self.active_tab())
            or self.selected("watch")
            or (self.watch[0] if self.watch else None)
        )
        if item:
            sym = scrip_label(item)
            self.status(f"Opening interactive chart for {sym}…")
            self.log_activity(f"📈 Opened chart for {sym} ({item.get('exchange', '')})")
            self.app.push_screen(HistoryScreen(item))
        else:
            self.status("Select a symbol to inspect chart", True)

    def action_detail(self) -> None:
        row = self.selected("orders")
        if row:
            oid = get(row, "orderId")
            sym = get(row, "tradingSymbol", default="?")
            self.log_activity(f"ℹ Opened order detail: {sym} (#{oid})")
            self.app.push_screen(DetailScreen(row))
        else:
            self.status("Select an order in Orders table to inspect detail", True)

    def action_quote(self) -> None:
        item = self.selected_symbol or (self.watch[0] if self.watch else None)
        if item:
            sym = scrip_label(item)
            self.log_activity(f"❓ Opened live quote for {sym}")
            self.app.push_screen(QuoteScreen(self.feed_key(item), scrip_label(item)))

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

    def action_show_alerts(self) -> None:
        self.app.push_screen(AlertsModal(self.alert_engine))

    def action_whatif(self) -> None:
        item = self.selected_symbol or (self.watch[0] if self.watch else None)
        self.app.push_screen(WhatIfScreen(item))

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen())

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
                self.app.push_screen(HistoryScreen(candidate))
        self.app.push_screen(ScannerModal(scanner), on_result)

    def action_replay(self) -> None:
        item = self.selected_symbol or (self.watch[0] if self.watch else None)
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

    def action_kill(self) -> None:
        self.log_activity("⚠ KILL SWITCH — automated order entry blocked")
        self.status("⚠ KILL SWITCH ACTIVATED — automation blocked", True)

    def action_refresh_all(self) -> None:
        self.refresh_all_data()
        self._update_top_status()
        self._update_symbol_focus(self.selected_symbol)
        self._update_trade_panel(self.selected_symbol)
        self.status("All workspace data refreshed")
        self.log_activity("🔄 Workspace refreshed")

    def action_toggle_log(self) -> None:
        try:
            log = self.query_one("#status-log", RichLog)
            log.display = not log.display
        except Exception:
            pass

    def action_toggle_focus(self) -> None:
        self.focus_mode = not self.focus_mode
        self.set_class(self.focus_mode, "focus-mode")
        if self.focus_mode:
            self.status("⚡ Focus Mode Enabled — Left/Right panes compressed")
        else:
            self.status("✓ Standard 3-Pane Workstation Layout Restored")

    def action_logout(self) -> None:
        if self.feed:
            self.feed.stop()
        self.app.client.logout()
        SESSION_FILE.unlink(missing_ok=True)
        self.app.client = None
        self.app.switch_screen(LoginScreen())

    # ── Feed & Logging ────────────────────────────────────────────────────────
    def on_ws(self, msg: dict) -> None:
        log = self.query_one("#status-log", RichLog)
        data = msg.get("data") if isinstance(msg, dict) else None
        if data and isinstance(data, dict):
            sym = data.get("tradingSymbol") or data.get("scripCode")
            ltp = data.get("ltp")
            if sym and ltp:
                log.write(f"Tick: {sym} @ ₹{ltp}")
        self.market_service.handle_ws(msg)

    def on_ack(self, d: dict) -> None:
        state = d.get("AckState", "")
        side_str = d.get("BuySellString", "")
        qty = d.get("TradeQty") or d.get("OrderQty", "")
        sym = d.get("TradingSymbol", "")
        price = (d.get("TradePrice") if d.get("TradeQty") else d.get("OrderPrice", ""))
        oid = d.get("SharekhanOrderID", "")
        err = d.get("ErrorMessage") or ""
        bad = any(x in str(state).lower() for x in ("reject", "fail", "error"))
        icon = "✗" if bad else "✓"
        line = f"{icon}  {state}  {side_str} {qty} × {sym} @ ₹{price}  (#{oid})"
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

    def log_activity(self, line: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        t = Text()
        t.append(f"  {ts}  ", style=C_SUBTLE)
        t.append(line)
        try:
            self.query_one("#status-log", RichLog).write(t)
        except Exception:
            pass

    def status(self, msg: str, error: bool = False) -> None:
        prefix = "  ✗  " if error else "  ·  "
        style = f"bold {C_RED}" if error else C_MUTED
        now = datetime.now().strftime("%H:%M:%S")
        t = Text()
        t.append(prefix, style=style)
        t.append(msg, style=style if error else C_TEXT)
        t.append(f"  [{now}]", style=C_SUBTLE)
        try:
            self.query_one("#status", Static).update(t)
        except Exception:
            pass

    def on_resize(self, event: Any) -> None:
        w, h = event.size.width, event.size.height
        self.set_class(w < 90, "-xs")
        self.set_class(90 <= w < 120, "-sm")
        self.set_class(120 <= w < 160, "-md")
        self.set_class(160 <= w < 200, "-lg")
        self.set_class(w >= 200, "-xl")
        self.set_class(h < 30, "-short")
        self.set_class(30 <= h < 45, "-medium-h")
        self.set_class(h >= 45, "-tall")
        self._update_top_status()
        self._update_symbol_focus(self.selected_symbol)

    def on_unmount(self) -> None:
        if self.feed:
            self.feed.stop()

    def post(self, fn, *a) -> None:
        try:
            self.app.call_from_thread(fn, *a)
        except Exception:
            pass

    @staticmethod
    def feed_key(item: dict) -> str:
        return WatchlistStore.feed_key(item)
