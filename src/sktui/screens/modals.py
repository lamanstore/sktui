"""Modal dialog screens for SKTUI."""
from __future__ import annotations

import threading
import time
import webbrowser
from datetime import date
from typing import Any

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, DataTable, Input, Label, Rule, Select, Static, RichLog,
)

from sktui.config import (
    BUILTIN_SCRIPS, DATA, EXCH_NAMES, HIST_COLS, INTERVALS, INTERVAL_LABELS,
    INTERVAL_SECONDS, PRODUCTS, SLASH_COMMANDS, SUB_MINUTE_INTERVALS, VALIDITIES,
)
from sktui.themes import (
    DEFAULT_THEME, SKTUI_THEME_MAP, THEME_DESCRIPTIONS, current_palette,
    palette_for_theme_name, save_configured_theme,
)
from sktui.utils import (
    build_order, expiry_key, fill_table, fmt, get, human,
    norm_expiry, normalize_scrip, safe_float, scrip_label, sign_style, strike_str,
    read_json, write_private,
)
from sktui.chart import (
    Candle, merge_live_tick_into_candles, render_candlestick_chart,
    render_chart, render_volume_bars, step_zoom,
)
from sktui.ui.widgets.chart_canvas import InteractiveChartCanvas
from sktui.ui.widgets.market_depth import MarketDepthWidget
from sktui.services.audit import audit_trail
from sktui.services.portfolio_analytics import PortfolioAnalytics
from sktui.services.risk_engine import RiskEngine
from sktui.services.scanner import MarketScanner
from sktui.services.replay_engine import ReplayEngine


def _workspace_screen(app: Any) -> Any:
    """Return the underlying workspace screen (MainScreen) below any open modals."""
    for s in reversed(getattr(app, "screen_stack", [])):
        if hasattr(s, "data") or hasattr(s, "quotes") or hasattr(s, "order_service"):
            return s
    return getattr(app, "screen", None)


def _get_quotes(app: Any) -> Any:
    """Resolve QuoteStore from *app* or from the workspace screen on the stack."""
    q = getattr(app, "quotes", None)
    if q is not None:
        return q
    ws = _workspace_screen(app)
    return getattr(ws, "quotes", None)


def _get_tick_data(app: Any, key: str) -> dict:
    """Resolve live tick dictionary for *key* from ``app.raw_ticks`` or ``QuoteStore``."""
    if not key:
        return {}
    raw = getattr(app, "raw_ticks", {}).get(key)
    if raw:
        return raw
    quotes = _get_quotes(app)
    if quotes is not None and hasattr(quotes, "get"):
        return quotes.get(key) or {}
    return {}


# ══════════════════════════════════════════════════════════════════════════════
#  SymbolSearch — search and add to watchlist
# ══════════════════════════════════════════════════════════════════════════════

class SymbolSearch(ModalScreen):
    """Search for a symbol and add it to the watchlist."""
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def __init__(self) -> None:
        super().__init__()
        self.index: list[tuple[str, dict]] = []
        self.shown: list[dict]             = []
        self.exch = "NC"

    def compose(self) -> ComposeResult:
        all_exchs = ["NC", "BC", "NF", "RN", "MX"]
        c = getattr(self.app, "client", None)
        ex = [e for e in all_exchs if e in getattr(c, "exchanges", []) or e in EXCH_NAMES]
        if not ex:
            ex = all_exchs
        self.options = [(f"{EXCH_NAMES[e]}  ({e})", e) for e in ex]
        default_val = "NC" if any(opt[1] == "NC" for opt in self.options) else self.options[0][1]
        with Vertical(classes="modal wide"):
            yield Label("⊕  Add Symbol to Watchlist", classes="title")
            with Horizontal(classes="row"):
                yield Select(self.options, value=default_val,
                             allow_blank=False, id="exch")
                yield Input(
                    placeholder="⌕  Search: symbol / company name / 'NIFTY 25000 CE' …",
                    id="q")
            yield DataTable(id="results", cursor_type="row")
            yield Static("⟳  Loading scrip master…", id="state", classes="hint")
            yield Static(
                "  ↑↓ navigate   Enter = add to watchlist   Esc = close",
                classes="hint")

    def on_mount(self) -> None:
        t = self.query_one("#results", DataTable)
        t.add_columns(
            " Symbol", " Type", " Expiry", " Strike", " Opt",
            " Lot", " Tick", " Code", " Company Name")
        self.query_one("#q", Input).focus()
        start_exch = "NC" if any(opt[1] == "NC" for opt in self.options) else self.options[0][1]
        self.load_master(start_exch)

    @on(Select.Changed, "#exch")
    def _exch(self, e: Select.Changed) -> None:
        self.load_master(str(e.value))

    @work(thread=True, exclusive=True)
    def load_master(self, exch: str) -> None:
        def _set_loading() -> None:
            if self.is_mounted:
                self.query_one("#state", Static).update(
                    f"⟳  Loading {EXCH_NAMES.get(exch, exch)} scrip master…"
                )
        self.app.call_from_thread(_set_loading)
        cache = DATA / f"master_{exch}_{date.today()}.json"
        rows  = read_json(cache, None)
        if rows is None:
            try:
                c = getattr(self.app, "client", None)
                rows = c.master(exch) if c else []
                if rows:
                    write_private(cache, rows)
            except Exception:
                rows = []
            try:
                for old in DATA.glob(f"master_{exch}_*.json"):
                    if old != cache:
                        old.unlink(missing_ok=True)
            except Exception:
                pass
        
        # Merge with built-in stock universe so searching is NEVER empty or 1-item
        builtin = BUILTIN_SCRIPS.get(exch, [])
        all_raw = (rows or []) + builtin
        seen = set()
        unique_rows = []
        for r in all_raw:
            code = get(r, "scripCode", default=None)
            sym  = get(r, "tradingSymbol", default="")
            k = (code, sym)
            if k not in seen:
                seen.add(k)
                unique_rows.append(r)

        idx = []
        for r in unique_rows:
            n   = normalize_scrip(exch, r)
            hay = (f"{n['tradingSymbol']} {n['companyName']} "
                   f"{n['expiry']} {strike_str(n['strike'])} {n['optionType']} {n['scripCode']}").lower()
            idx.append((hay, n))

        self.app.call_from_thread(self.set_index, exch, idx)

    def set_index(self, exch: str, idx: list) -> None:
        if not self.is_mounted:
            return
        p = current_palette()
        self.exch, self.index = exch, idx
        self.query_one("#state", Static).update(
            Text(f"✓  {len(idx):,} instruments loaded  ·  type to search",
                 style=p.muted))
        self.refilter()

    @on(Input.Changed, "#q")
    def refilter(self, *_: Any) -> None:
        if not self.is_mounted:
            return
        p     = current_palette()
        terms = self.query_one("#q", Input).value.lower().split()
        t     = self.query_one("#results", DataTable)
        t.clear()
        if not terms:
            self.shown = [n for _, n in self.index[:50]]
            if self.index:
                self.query_one("#state", Static).update(
                    Text(f"✓  {len(self.index):,} instruments loaded  ·  type to search",
                         style=p.muted))
        else:
            hits = [n for hay, n in self.index if all(x in hay for x in terms)]
            hits.sort(key=lambda n: (
                str(n["tradingSymbol"]), expiry_key(n["expiry"]),
                float(n["strike"] or 0)))
            self.shown = hits[:300]
            if self.shown:
                self.query_one("#state", Static).update(
                    Text(f"✓  {len(hits):,} match(es)  ·  Enter = select",
                         style=p.muted))
            else:
                self.query_one("#state", Static).update(
                    Text("✗  No matching instruments found",
                         style=p.warn))
        for n in self.shown:
            t.add_row(
                Text(n["tradingSymbol"], style=f"bold {p.primary}"),
                n["instType"],
                n["expiry"] or "",
                strike_str(n["strike"]) if n["optionType"] in ("CE", "PE") else "",
                Text(n["optionType"], style=(
                    p.bull if n["optionType"] == "CE"
                    else p.bear if n["optionType"] == "PE" else p.muted)),
                str(n["lotSize"]),
                str(n["tickSize"]),
                str(n["scripCode"]),
                n["companyName"],
            )

    def on_theme_changed(self) -> None:
        if self.is_mounted:
            self.refilter()

    @on(Input.Submitted, "#q")
    def _enter(self) -> None:
        t = self.query_one("#results", DataTable)
        if t.row_count > 0:
            t.move_cursor(row=0)
        t.focus()

    @on(DataTable.RowSelected, "#results")
    def _pick(self, e: DataTable.RowSelected) -> None:
        if 0 <= e.cursor_row < len(self.shown):
            self.dismiss(self.shown[e.cursor_row])


# ══════════════════════════════════════════════════════════════════════════════
#  OrderTicket
# ══════════════════════════════════════════════════════════════════════════════

class OrderTicket(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, info: dict, mode: str = "NEW") -> None:
        super().__init__()
        self.info, self.mode = dict(info), mode

    def compose(self) -> ComposeResult:
        i  = self.info
        c  = getattr(self.app, "client", None)
        ex = [e for e in getattr(c, "exchanges", []) if e in EXCH_NAMES] or list(EXCH_NAMES)
        if i.get("exchange") and i["exchange"] not in ex:
            ex.append(i["exchange"])
        prod   = i.get("productType") if i.get("productType") in PRODUCTS else "INVESTMENT"
        val    = i.get("validity")    if i.get("validity")    in VALIDITIES else "GFD"
        opt    = i.get("optionType")  if i.get("optionType")  in ("CE", "PE") else "XX"
        strike = strike_str(i.get("strike")) if opt != "XX" else "-1"
        ord_t  = i.get("orderType") if i.get("orderType") in ("NORMAL", "SL", "SL-M") else "NORMAL"
        icon   = "✎" if self.mode == "MODIFY" else "⬡"

        with Horizontal(classes="modal order-modal"):
            # ── LEFT PANEL: Core fields ────────────────────────────────────────
            with Vertical(classes="order-left"):
                yield Label(
                    f"{icon}  "
                    f"{'Modify Order' if self.mode == 'MODIFY' else 'New Order'}"
                    f"  —  {scrip_label(i)}",
                    classes="title")

                # Live quote banner
                yield Static("", id="order-quote-banner")

                yield Label("Direction & Exchange", classes="section-label")
                with Horizontal(classes="row"):
                    yield Select([("▲  BUY", "B"), ("▼  SELL", "S")],
                                 value=i.get("side", "B"), allow_blank=False, id="side")
                    yield Select([(f"{EXCH_NAMES.get(e, e)}  ({e})", e) for e in ex],
                                 value=i.get("exchange", ex[0]),
                                 allow_blank=False, id="exch")

                yield Label("Instrument", classes="section-label")
                with Horizontal(classes="row"):
                    yield Vertical(
                        Label("Trading Symbol"),
                        Input(str(i.get("tradingSymbol", "")), id="sym"),
                        classes="field")
                    yield Vertical(
                        Label("Scrip Code"),
                        Input(str(i.get("scripCode", "") or ""), id="code"),
                        classes="field")

                hint = []
                if i.get("lotSize"):  hint.append(f"Lot: {i['lotSize']}")
                if i.get("tickSize"): hint.append(f"Tick: {i['tickSize']}")
                lbl = "Order & Pricing"
                if hint: lbl += f"  ({' · '.join(hint)})"
                yield Label(lbl, id="param-label", classes="section-label")
                with Horizontal(classes="row"):
                    yield Vertical(Label("Quantity"),
                                   Input(str(i.get("quantity", "1")), id="qty"),
                                   classes="field")
                    yield Vertical(Label("Order Type"),
                                   Select([("Regular (Limit/Mkt)", "NORMAL"),
                                           ("Stop Loss Limit (SL)", "SL"),
                                           ("Stop Loss Market (SL-M)", "SL-M")],
                                          value=ord_t, allow_blank=False, id="ordtype"),
                                   classes="field")
                    yield Vertical(Label("Price  (0 = Market)"),
                                   Input(str(i.get("price", "0")), id="price"),
                                   classes="field")

                if self.mode == "MODIFY":
                    yield Static(
                        f"  ⚙  Order {i.get('orderId')}"
                        f"  ·  RMS: {i.get('rmsCode')}"
                        f"  ·  Executed: {i.get('executedQty', 0)}",
                        classes="hint")

                yield Static("", id="err", classes="err-msg")
                with Horizontal(classes="row buttons"):
                    yield Button("⬡  Review Order", id="review", variant="primary")
                    yield Button("✗  Cancel",       id="cancel")

            # ── RIGHT PANEL: Context fields (SL / Derivatives / Advanced) ────
            with VerticalScroll(classes="order-right"):
                # ── Stop Loss (shown when SL/SL-M selected) ──────────────────
                with Vertical(id="sl-box"):
                    yield Label("🛑  Stop Loss & Risk", classes="section-label")
                    yield Vertical(Label("SL Trigger Price (₹)"),
                                   Input(str(i.get("triggerPrice", "0")), id="trig"),
                                   classes="field")
                    yield Vertical(Label("Target / Take Profit (₹)"),
                                   Input(str(i.get("targetPrice", "0")), id="target"),
                                   classes="field")
                    yield Vertical(Label("Trailing SL (pts)"),
                                   Input(str(i.get("trailingSl", "0")), id="trailing_sl"),
                                   classes="field")
                    with Horizontal(classes="row"):
                        yield Button("⚡ LTP", id="btn-fill-price", variant="default")
                        yield Button("🛑 -1%",  id="sl-1pct",  variant="default")
                        yield Button("🛑 -2%",  id="sl-2pct",  variant="default")
                        yield Button("🎯 +2%",  id="tp-2pct",  variant="default")
                        yield Button("🎯 +5%",  id="tp-5pct",  variant="default")

                # ── Derivatives (shown for NF/RN/BF/MX exchanges) ────────────
                with Vertical(id="derivatives-box"):
                    yield Label("Derivatives", classes="section-label")
                    yield Vertical(Label("Inst. Type"),
                                   Input(str(i.get("instType", "")), id="itype",
                                         placeholder="FS/FI/OS/OI/FUTCUR/OPTCUR"),
                                   classes="field")
                    yield Vertical(Label("Option"),
                                   Input(opt, id="otyp"),
                                   classes="field")
                    yield Vertical(Label("Strike"),
                                   Input(strike, id="strike"),
                                   classes="field")
                    yield Vertical(Label("Expiry"),
                                   Input(str(i.get("expiry", "")), id="expiry",
                                         placeholder="DD/MM/YYYY"),
                                   classes="field")

                # ── Advanced Settings (always visible in right panel) ────────
                with Vertical(id="advanced-box"):
                    yield Label("⚙  Execution Settings", classes="section-label")
                    yield Vertical(Label("Product"),
                                   Select([(p, p) for p in PRODUCTS],
                                          value=prod, allow_blank=False, id="product"),
                                   classes="field")
                    yield Vertical(Label("Validity"),
                                   Select([(v, v) for v in VALIDITIES],
                                          value=val, allow_blank=False, id="validity"),
                                   classes="field")
                    yield Vertical(Label("GTD Date"),
                                   Input("", id="gtdd", placeholder="DD/MM/YYYY"),
                                   classes="field")
                    yield Vertical(Label("Session"),
                                   Select([("Regular", "N"), ("AMO", "Y")],
                                          value=i.get("afterHour", "N"),
                                          allow_blank=False, id="ah"),
                                   classes="field")
                    yield Vertical(Label("Disclosed Qty"),
                                   Input("0", id="disc"),
                                   classes="field")

                # Placeholder when right panel is empty
                yield Static(
                    "  Select SL/SL-M order type to unlock Stop Loss fields.\n"
                    "  Select F&O / Currency exchange for Derivatives fields.",
                    id="right-hint", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#qty", Input).focus()
        self.update_visibility()
        self._lookup_and_update_scrip()
        self._apply_responsive_layout()

    def on_resize(self, event: Any) -> None:
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        try:
            modal = self.query_one(".order-modal")
            left = self.query_one(".order-left")
            right = self.query_one(".order-right")
            if self.size.width > 0 and self.size.width < 100:
                modal.styles.width = max(56, self.size.width - 2)
                modal.styles.layout = "vertical"
                left.styles.width = "100%"
                left.styles.min_width = 40
                left.styles.height = "auto"
                right.styles.width = "100%"
                right.styles.min_width = 40
                right.styles.height = "auto"
            else:
                modal.styles.width = 96
                modal.styles.layout = "horizontal"
                left.styles.width = "1fr"
                left.styles.min_width = 56
                left.styles.height = "100%"
                right.styles.width = 54
                right.styles.min_width = 40
                right.styles.height = "100%"
        except Exception:
            pass

    def update_visibility(self) -> None:
        try:
            ord_t = str(self.query_one("#ordtype", Select).value)
            sl_visible = (ord_t in ("SL", "SL-M"))
            self.query_one("#sl-box").display = sl_visible

            exch = str(self.query_one("#exch", Select).value)
            deriv_visible = (exch not in ("NC", "BC"))
            self.query_one("#derivatives-box").display = deriv_visible

            # Always show advanced settings in right panel
            self.query_one("#advanced-box").display = True

            # Show hint only when both SL and derivatives boxes are hidden
            try:
                self.query_one("#right-hint").display = not sl_visible and not deriv_visible
            except Exception:
                pass
        except Exception:
            pass

    @on(Select.Changed, "#ordtype")
    def _ordtype_changed(self) -> None:
        self.update_visibility()

    @on(Select.Changed, "#exch")
    def _exch_changed(self) -> None:
        self.update_visibility()
        self._lookup_and_update_scrip()

    def resolve_scrip(self, sym: str, exch: str) -> dict | None:
        if not sym:
            return None
        sym_clean = sym.strip().upper()
        # 1. Search cached master file for this exchange
        cache = DATA / f"master_{exch}_{date.today()}.json"
        rows = read_json(cache, None)
        if rows:
            for r in rows:
                if str(get(r, "tradingSymbol", default="")).upper() == sym_clean:
                    return normalize_scrip(exch, r)
        # 2. Search built-in scrips for this exchange
        for s in BUILTIN_SCRIPS.get(exch, []):
            if str(s.get("tradingSymbol", "")).upper() == sym_clean:
                return normalize_scrip(exch, s)
        # 3. Fallback search across all built-in scrips
        for ex, s_list in BUILTIN_SCRIPS.items():
            for s in s_list:
                if str(s.get("tradingSymbol", "")).upper() == sym_clean:
                    return normalize_scrip(exch, s)
        return None

    def _lookup_and_update_scrip(self) -> None:
        try:
            sym  = self.query_one("#sym", Input).value.strip()
            exch = str(self.query_one("#exch", Select).value)
            scrip = self.resolve_scrip(sym, exch)
            if scrip:
                if scrip.get("scripCode") is not None:
                    self.query_one("#code", Input).value = str(scrip["scripCode"])
                if scrip.get("lotSize"):
                    self.info["lotSize"] = scrip["lotSize"]
                if scrip.get("tickSize"):
                    self.info["tickSize"] = scrip["tickSize"]
                hint = []
                if self.info.get("lotSize"):
                    hint.append(f"Lot: {self.info['lotSize']}")
                if self.info.get("tickSize"):
                    hint.append(f"Tick: {self.info['tickSize']}")
                lbl = "Order & Pricing"
                if hint:
                    lbl += f"  ({' · '.join(hint)})"
                try:
                    self.query_one("#param-label", Label).update(lbl)
                except Exception:
                    pass
                if scrip.get("instType"):
                    try:
                        self.query_one("#itype", Input).value = str(scrip["instType"])
                    except Exception:
                        pass
                if scrip.get("optionType"):
                    try:
                        self.query_one("#otyp", Input).value = str(scrip["optionType"])
                    except Exception:
                        pass
                if scrip.get("strike"):
                    try:
                        self.query_one("#strike", Input).value = strike_str(scrip["strike"])
                    except Exception:
                        pass
                if scrip.get("expiry"):
                    try:
                        self.query_one("#expiry", Input).value = str(scrip["expiry"])
                    except Exception:
                        pass
            self.update_quote_banner()
        except Exception:
            pass

    def get_base_price(self) -> float:
        code = self.query_one("#code", Input).value.strip()
        exch = str(self.query_one("#exch", Select).value)
        key  = f"{exch}{code}"
        ticks = _get_tick_data(self.app, key)
        ltp  = ticks.get("ltp") or self.info.get("price")
        try:
            px = float(self.query_one("#price", Input).value.strip() or 0)
            if px > 0:
                return px
        except Exception:
            pass
        return float(ltp or 0)

    def update_quote_banner(self) -> None:
        p    = current_palette()
        code = self.query_one("#code", Input).value.strip()
        exch = str(self.query_one("#exch", Select).value)
        key  = f"{exch}{code}" if code else ""
        ticks = _get_tick_data(self.app, key)
        ltp   = ticks.get("ltp") or self.info.get("price")

        t = Text()
        t.append("  📊 Market Quote: ", style=p.muted)
        if ltp and float(ltp) > 0:
            fltp = float(ltp)
            t.append(f"LTP ₹{fltp:,.2f} ", style=f"bold {p.bull}")
            chg = ticks.get("rsChange") or 0.0
            pct = ticks.get("perChange") or 0.0
            if chg or pct:
                sign = "+" if float(chg) >= 0 else ""
                t.append(f"({sign}{fmt(chg)} / {sign}{fmt(pct)}%)  ", style=sign_style(chg))
            if ticks.get("bidPrice"):
                t.append(f"Bid: ₹{fmt(ticks['bidPrice'])}  ", style=p.muted)
            if ticks.get("offPrice"):
                t.append(f"Ask: ₹{fmt(ticks['offPrice'])}  ", style=p.muted)
            if ticks.get("high"):
                t.append(f"High: ₹{fmt(ticks['high'])}  ", style=p.bull)
            if ticks.get("low"):
                t.append(f"Low: ₹{fmt(ticks['low'])}", style=p.bear)
        else:
            t.append("0.00 (MARKET order uses execution LTP)", style=p.warn)
        
        self.query_one("#order-quote-banner", Static).update(t)

    def on_theme_changed(self) -> None:
        try:
            self.update_quote_banner()
        except Exception:
            pass

    @on(Input.Changed, "#sym")
    def _sym_changed(self, e: Input.Changed) -> None:
        self._lookup_and_update_scrip()

    @on(Input.Submitted)
    def _on_input_submit(self, e: Input.Submitted) -> None:
        if e.input.id == "sym":
            self._lookup_and_update_scrip()
            self.query_one("#qty", Input).focus()
        else:
            self._review()

    @on(Button.Pressed, "#btn-fill-price")
    def _fill_price(self) -> None:
        code = self.query_one("#code", Input).value.strip()
        exch = str(self.query_one("#exch", Select).value)
        key  = f"{exch}{code}"
        ticks = _get_tick_data(self.app, key)
        ltp  = ticks.get("ltp") or self.info.get("price")
        if ltp and float(ltp) > 0:
            self.query_one("#price", Input).value = f"{float(ltp):.2f}"
            self.app.notify(f"Auto-filled price ₹{float(ltp):.2f}")
        else:
            self.app.notify("Market price unavailable — set manually or leave 0 for Market", severity="warning")

    @on(Button.Pressed, "#sl-1pct")
    def _sl_1pct(self) -> None:
        base = self.get_base_price()
        if base <= 0:
            return self.app.notify("Set price or wait for live LTP first", severity="warning")
        side = str(self.query_one("#side", Select).value)
        sl_val = round(base * 0.99 if side == "B" else base * 1.01, 2)
        self.query_one("#trig", Input).value = str(sl_val)
        self.query_one("#ordtype", Select).value = "SL"
        self.app.notify(f"Set Stop Loss trigger to ₹{sl_val:.2f} (-1%)")

    @on(Button.Pressed, "#sl-2pct")
    def _sl_2pct(self) -> None:
        base = self.get_base_price()
        if base <= 0:
            return self.app.notify("Set price or wait for live LTP first", severity="warning")
        side = str(self.query_one("#side", Select).value)
        sl_val = round(base * 0.98 if side == "B" else base * 1.02, 2)
        self.query_one("#trig", Input).value = str(sl_val)
        self.query_one("#ordtype", Select).value = "SL"
        self.app.notify(f"Set Stop Loss trigger to ₹{sl_val:.2f} (-2%)")

    @on(Button.Pressed, "#tp-2pct")
    def _tp_2pct(self) -> None:
        base = self.get_base_price()
        if base <= 0:
            return self.app.notify("Set price or wait for live LTP first", severity="warning")
        side = str(self.query_one("#side", Select).value)
        tp_val = round(base * 1.02 if side == "B" else base * 0.98, 2)
        self.query_one("#target", Input).value = str(tp_val)
        self.app.notify(f"Set Target / Take Profit to ₹{tp_val:.2f} (+2%)")

    @on(Button.Pressed, "#tp-5pct")
    def _tp_5pct(self) -> None:
        base = self.get_base_price()
        if base <= 0:
            return self.app.notify("Set price or wait for live LTP first", severity="warning")
        side = str(self.query_one("#side", Select).value)
        tp_val = round(base * 1.05 if side == "B" else base * 0.95, 2)
        self.query_one("#target", Input).value = str(tp_val)
        self.app.notify(f"Set Target / Take Profit to ₹{tp_val:.2f} (+5%)")

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#review")
    def _review(self) -> None:
        def g(id_name: str) -> str:
            try:
                elem = self.query_one(f"#{id_name}", Input)
                return elem.value.strip() if elem else ""
            except Exception:
                return ""

        def s(id_name: str) -> str:
            try:
                elem = self.query_one(f"#{id_name}", Select)
                return str(elem.value) if elem else ""
            except Exception:
                return ""

        i = self.info
        fields = {
            "exchange": s("exch"),        "scripCode": g("code"),
            "tradingSymbol": g("sym"),     "transactionType": s("side"),
            "quantity": g("qty"),          "price": g("price"),
            "triggerPrice": g("trig"),     "targetPrice": g("target"),
            "trailingSl": g("trailing_sl"),"orderType": s("ordtype"),
            "disclosedQty": g("disc") or "0",
            "afterHour": s("ah") or "N",
            "validity": s("validity") or "GFD",     "gtdd": g("gtdd"),
            "productType": s("product") or "INVESTMENT",   "instrumentType": g("itype"),
            "optionType": g("otyp"),       "strikePrice": g("strike"),
            "expiry": g("expiry"),         "lotSize": i.get("lotSize"),
            "tickSize": i.get("tickSize"), "rmsCode": i.get("rmsCode") or "ANY",
            "orderId": i.get("orderId"),   "executedQty": i.get("executedQty", 0),
        }
        c = getattr(self.app, "client", None)
        cid = getattr(c, "cid", None) or getattr(c, "customer_id", "0") or "0"
        login_id = getattr(c, "login_id", "USER") or "USER"
        try:
            params, warns = build_order(fields, self.mode, cid, login_id)
        except ValueError as e:
            p = current_palette()
            self.query_one("#err", Static).update(
                Text(f"✗  Validation error: {e}", style=f"bold {p.bear}"))
            return
        self.dismiss((params, warns))


# ══════════════════════════════════════════════════════════════════════════════
#  Confirm
# ══════════════════════════════════════════════════════════════════════════════

class Confirm(ModalScreen):
    BINDINGS = [
        Binding("y",      "yes",           "Yes"),
        Binding("n",      "dismiss(False)", "No"),
        Binding("escape", "dismiss(False)", "No"),
    ]

    def __init__(self, title: str, body: Text, paper: bool) -> None:
        super().__init__()
        self.title_, self.body, self.paper = title, body, paper

    def compose(self) -> ComposeResult:
        p = current_palette()
        paper_tag = (Text("  ⚠  PAPER MODE — no real order will be sent\n",
                          style=f"bold {p.warn}")
                     if self.paper else Text(""))
        with Vertical(classes="modal confirm-modal"):
            yield Label(f"⬡  {self.title_}", classes="title")
            yield Static(paper_tag, id="confirm-paper-tag")
            yield Rule()
            yield Static(self.body, id="confirm-body-static", classes="confirm-body")
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("✓  Confirm  (y)", id="yes", variant="success")
                yield Button("✗  Cancel   (n)", id="no",  variant="error")

    def on_mount(self) -> None:
        try:
            self.query_one("#yes", Button).focus()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        try:
            p = current_palette()
            paper_tag = (
                Text("  ⚠  PAPER MODE — no real order will be sent\n", style=f"bold {p.warn}")
                if self.paper
                else Text("")
            )
            self.query_one("#confirm-paper-tag", Static).update(paper_tag)
            self.query_one("#confirm-body-static", Static).update(self.body)
        except Exception:
            pass

    def action_yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#yes")
    def _y(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def _n(self) -> None:
        self.dismiss(False)


# ══════════════════════════════════════════════════════════════════════════════
#  Sparkline (inline mini)
# ══════════════════════════════════════════════════════════════════════════════

SPARK_CHARS = "▁▂▃▄▅▆▇█"


def sparkline(vals: list[float], width: int = 80) -> str:
    """Small inline Unicode bar sparkline for a header strip."""
    if not vals or width <= 0:
        return ""
    import math as _m
    clean = [float(v) for v in vals if v is not None and _m.isfinite(float(v))]
    if not clean:
        return ""
    step = max(1, len(clean) // width)
    clean = clean[::step][-width:]
    lo, hi = min(clean), max(clean)
    rng = (hi - lo) or 1.0
    n_chars = len(SPARK_CHARS) - 1
    return "".join(SPARK_CHARS[max(0, min(n_chars, int((v - lo) / rng * n_chars)))] for v in clean)


# ══════════════════════════════════════════════════════════════════════════════
#  HistoryScreen — full-viewport real-time chart with scalper TFs & order staging
# ══════════════════════════════════════════════════════════════════════════════

class HistoryScreen(ModalScreen):
    """Full-viewport real-time price chart with sub-minute scalper timeframes,
    live forming candles, 2D crosshair inspection, multi-density zoom & pan,
    direct order staging, and interactive hotkeys."""

    CYCLE_INTERVALS = [
        "tick", "1second", "5second", "15second", "30second",
        "1minute", "3minute", "5minute", "15minute", "30minute",
        "60minute", "daily", "weekly", "monthly",
    ]

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("k",      "toggle_mode",   "Candle/Line"),
        Binding("e",      "toggle_ema",    "MA/VWAP"),
        Binding("i",      "toggle_rsi",    "RSI(14)"),
        Binding("v",      "toggle_volume", "Volume"),
        Binding("l",      "toggle_sr",     "Sup/Res"),
        Binding("n",      "toggle_compare","vs NIFTY50"),
        Binding("a",      "toggle_fit_all","Fit All"),
        Binding("0",      "toggle_fit_all","Fit All", show=False),
        Binding("z",      "toggle_zen",    "Zen Fullscreen"),
        Binding("t",      "toggle_table",  "Toggle Table"),
        Binding("b",      "quick_buy",     "Buy"),
        Binding("s",      "quick_sell",    "Sell"),
        Binding("left_square_bracket",  "prev_interval", "Prev TF [", show=False),
        Binding("right_square_bracket", "next_interval", "Next TF ]", show=False),
        Binding("plus,equal",           "zoom_in",       "Zoom In +", show=False),
        Binding("minus",                "zoom_out",      "Zoom Out -", show=False),
        Binding("left",                 "crosshair_left", "Crosshair Left", show=False),
        Binding("right",                "crosshair_right","Crosshair Right", show=False),
        Binding("up",                   "crosshair_up",   "Price Up", show=False),
        Binding("down",                 "crosshair_down", "Price Down", show=False),
        Binding("comma,pageup",         "pan_left",      "Pan Left", show=False),
        Binding("full_stop,pagedown",   "pan_right",     "Pan Right", show=False),
        Binding("home",                 "pan_start",     "Oldest", show=False),
        Binding("end,space,backspace",  "snap_live",     "Snap Live", show=False),
        Binding("grave_accent",         "set_iv('tick')", "TICK", show=False),
        Binding("1",      "set_iv('1minute')", "1m", show=False),
        Binding("3",      "set_iv('3minute')", "3m", show=False),
        Binding("5",      "set_iv('5minute')", "5m", show=False),
        Binding("f",      "set_iv('15minute')", "15m", show=False),
        Binding("h",      "set_iv('60minute')", "1h", show=False),
        Binding("d",      "set_iv('daily')", "1D", show=False),
        Binding("w",      "set_iv('weekly')", "1W", show=False),
        Binding("m",      "set_iv('monthly')", "1M", show=False),
        Binding("g",      "cycle_scalper_tf", "Scalper TF", show=False),
    ]

    def __init__(
        self,
        item: dict,
        initial_interval: str = "5minute",
        initial_mode: str = "candle",
    ) -> None:
        super().__init__()
        self.item         = item
        self._rows:       list[dict] = []
        self._candles:    list[Candle] = []
        self._closes:     list[float] = []
        self._volumes:    list[float] = []
        self._show_volume = True
        self.current_iv   = initial_interval
        self.mode         = initial_mode
        self.show_ema     = True
        self.show_rsi     = True
        self.show_vwap    = True
        self.show_sr      = True
        self.compare_nifty = True
        self.zoom_bars: int | None = None
        self.pan_offset: int = 0
        self.fit_all: bool = False
        self.crosshair_idx: int | None = None
        self.crosshair_price: float | None = None
        self.zen_mode: bool = False
        self.table_visible: bool = False
        self._resize_timer = None
        self._countdown_timer = None
        self._compare_cache: tuple[str, int, list[float]] | None = None

    @property
    def feed_key(self) -> str:
        exch = self.item.get("exchange") or self.item.get("exch") or "NC"
        scrip = self.item.get("scripCode") or self.item.get("scrip_code") or self.item.get("code")
        if not scrip:
            sym = str(self.item.get("tradingSymbol") or "").upper()
            if sym:
                from sktui.utils import resolve_code
                scrip = resolve_code(sym, exch)
        return f"{exch}{scrip}" if scrip else f"{exch}{self.item.get('tradingSymbol', '')}"

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal chart"):
            # ── Header bar ────────────────────────────────────────────────────
            with Horizontal(classes="chart-header-bar"):
                yield Label(
                    f"📈  {scrip_label(self.item)}  ({self.item.get('exchange', '')})",
                    classes="chart-title",
                )
                yield Static("", id="chart-meta", classes="chart-meta-right")

            # ── Interval pill bar + Quick Actions ─────────────────────────────
            with Horizontal(classes="chart-interval-bar"):
                for iv, lbl in [
                    ("tick", "TICK"), ("1second", "1s"), ("5second", "5s"),
                    ("15second", "15s"), ("30second", "30s"),
                    ("1minute", "1m"), ("3minute", "3m"), ("5minute", "5m"),
                    ("15minute", "15m"), ("30minute", "30m"), ("60minute", "1h"),
                    ("daily", "1D"), ("weekly", "1W"), ("monthly", "1M"),
                ]:
                    yield Button(
                        lbl,
                        id=f"iv-{iv}",
                        variant="primary" if iv == self.current_iv else "default",
                        classes="iv-pill",
                    )
                yield Button("⤢ Fit", id="act-fit", classes="iv-action-pill")
                yield Button("📋 Table", id="act-table", classes="iv-action-pill")
                yield Button("⚡ Zen", id="act-zen", classes="iv-action-pill")
                yield Button("BUY", id="act-buy", classes="iv-buy-pill")
                yield Button("SELL", id="act-sell", classes="iv-sell-pill")

            # ── Interactive Chart Canvas ──────────────────────────────────────
            yield InteractiveChartCanvas(id="chart-out")

            # ── Bottom strip: key hints ───────────────────────────────────────
            with Horizontal(classes="chart-bottom-bar"):
                yield Label("  Live Interactive Chart", classes="chart-bottom-label")
                yield Static(
                    "  [ / ]=TF  |  +/-=Zoom  |  0/a=Fit  |  k=Mode  |  e=MA  |  i=RSI  |  ←→=Crosshair  |  b/s=Order  |  t=Table  |  z=Zen  |  Esc=Close",
                    classes="chart-bottom-hint",
                    markup=False,
                )
            # Hidden drawer by default; populated with rows so table tests pass!
            yield DataTable(id="hist", cursor_type="row", classes="hidden-drawer")

    def on_mount(self) -> None:
        t = self.query_one("#hist", DataTable)
        for key, label in HIST_COLS:
            t.add_column(label, key=key)
        quotes = _get_quotes(self.app)
        if quotes is not None and hasattr(quotes, "add_listener"):
            quotes.add_listener(self._on_live_tick)
        try:
            self.query_one("#chart-out", InteractiveChartCanvas).focus()
        except Exception:
            pass
        self._countdown_timer = self.set_interval(0.25, self._on_countdown_timer)
        self.fetch(self.current_iv)

    def on_unmount(self) -> None:
        quotes = _get_quotes(self.app)
        if quotes is not None and hasattr(quotes, "remove_listener"):
            quotes.remove_listener(self._on_live_tick)

    def _on_live_tick(self, key: str, raw_tick: dict, ltp: float, vol_delta: float) -> None:
        if key != self.feed_key:
            return
        app_tid = getattr(self.app, "_thread_id", None)
        if app_tid is not None and app_tid != threading.get_ident():
            try:
                self.app.call_from_thread(self._apply_live_tick, ltp, vol_delta)
            except Exception:
                pass
            return
        self._apply_live_tick(ltp, vol_delta)

    def _apply_live_tick(self, ltp: float, vol_delta: float) -> None:
        if not self.is_mounted:
            return
        sec = INTERVAL_SECONDS.get(self.current_iv, 5)
        if self._candles:
            self._candles, _ = merge_live_tick_into_candles(
                self._candles, ltp, vol_delta, sec
            )
            self._closes = [c.close for c in self._candles]
            self._volumes = [c.volume for c in self._candles]
        elif ltp > 0:
            self._candles = [Candle(timestamp="now", open=ltp, high=ltp, low=ltp, close=ltp, volume=vol_delta)]
            self._closes = [ltp]
            self._volumes = [vol_delta]
        self._render_canvas()
        self._update_meta()

    def _on_countdown_timer(self) -> None:
        if not self.is_mounted:
            return
        sec = INTERVAL_SECONDS.get(self.current_iv, 0)
        if sec > 0 and self._candles:
            self._render_canvas()
            self._update_meta()

    def action_set_iv(self, iv: str) -> None:
        self.set_interval_val(iv)

    def set_interval_val(self, iv: str) -> None:
        self.current_iv = iv
        self.pan_offset = 0
        self.crosshair_idx = None
        self.crosshair_price = None
        for b in self.query(Button):
            if b.id and b.id.startswith("iv-"):
                b.variant = "primary" if b.id == f"iv-{iv}" else "default"
        self.fetch(iv)

    @on(Button.Pressed)
    def _button_click(self, e: Button.Pressed) -> None:
        bid = e.button.id or ""
        if bid.startswith("iv-"):
            self.set_interval_val(bid.replace("iv-", ""))
        elif bid == "act-fit":
            self.action_toggle_fit_all()
        elif bid == "act-table":
            self.action_toggle_table()
        elif bid == "act-zen":
            self.action_toggle_zen()
        elif bid == "act-buy":
            self.action_quick_buy()
        elif bid == "act-sell":
            self.action_quick_sell()

    @work(thread=True, exclusive=True)
    def fetch(self, interval: str) -> None:
        exch = self.item.get("exchange") or self.item.get("exch") or "NC"
        sym = str(self.item.get("tradingSymbol") or "").upper()
        scrip = self.item.get("scripCode") or self.item.get("scrip_code") or self.item.get("code")
        if not scrip and sym:
            from sktui.utils import resolve_code
            scrip = resolve_code(sym, exch)
        if not sym and scrip:
            from sktui.utils import resolve_symbol
            sym = resolve_symbol(scrip, exchange=exch)
        if not scrip:
            scrip = self.item.get("scripCode") or (2475 if getattr(self.app, "paper", False) else None)

        # Resolve real base price from quotes store, item, or known base prices
        base_p = None
        quotes = _get_quotes(self.app)
        if quotes:
            base_p = quotes.ltp(self.feed_key)
            if not base_p:
                q = quotes.get(self.feed_key)
                base_p = float(q.get("ltp") or q.get("close") or q.get("open") or 0.0) or None
        if not base_p:
            base_p = float(self.item.get("ltp") or self.item.get("lastTradedPrice") or self.item.get("close") or 0.0) or None
        if not base_p and sym and getattr(self.app, "paper", False):
            from sktui.config import KNOWN_BASE_PRICES
            base_p = KNOWN_BASE_PRICES.get(sym)

        rows = []
        try:
            if getattr(self.app, "client", None):
                import inspect
                sig = inspect.signature(self.app.client.historical)
                kwargs = {}
                if "base_price" in sig.parameters:
                    kwargs["base_price"] = base_p
                if "symbol" in sig.parameters:
                    kwargs["symbol"] = sym
                rows = self.app.client.historical(exch, scrip, interval, **kwargs)
        except Exception:
            pass

        if not rows:
            if getattr(self.app, "paper", False):
                from sktui.api.paper_trading import generate_paper_history
                rows = generate_paper_history(exch, scrip, interval, base_price=base_p)
            else:
                rows = []
        if self.is_mounted:
            self.app.call_from_thread(self.show, rows, interval)

    def _render_canvas(self) -> None:
        try:
            canvas = self.query_one("#chart-out", InteractiveChartCanvas)
        except Exception:
            return
        w, h = canvas.chart_size
        if w < 24 or h < 6:
            w = max(24, self.size.width - 2) if self.size.width > 24 else 100
            h = max(6, self.size.height - 6) if self.size.height > 10 else 24

        candles = self._candles
        closes = self._closes
        volumes = self._volumes
        iv = self.current_iv
        label_str = INTERVAL_LABELS.get(iv, iv)
        sym = scrip_label(self.item)

        quotes = _get_quotes(self.app)
        ltp = (quotes.ltp(self.feed_key) if quotes else None) or (closes[-1] if closes else None)
        sec = INTERVAL_SECONDS.get(iv, 0)
        import time as _t
        countdown = (sec - (_t.time() % sec)) if sec > 0 else None

        pos_price, pos_qty = None, 0
        main_screen = _workspace_screen(self.app)
        if main_screen and hasattr(main_screen, "data"):
            pos = next((p for p in main_screen.data.get("positions", []) if get(p, "tradingSymbol") == self.item.get("tradingSymbol")), None)
            if pos:
                pos_qty = int(safe_float(get(pos, "netQty", default=0)))
                pos_price = safe_float(get(pos, "avgPrice", default=0.0)) or None

        status_note = ""
        if self.crosshair_idx is not None or self.crosshair_price is not None:
            status_note = "End=live snap"

        if self.mode == "candle" and candles:
            compare_closes: list[float] | None = None
            if self.compare_nifty and sym.upper() != "NIFTY50":
                if self._compare_cache and self._compare_cache[0] == iv and self._compare_cache[1] == len(candles):
                    compare_closes = self._compare_cache[2]
                else:
                    from sktui.api.paper_trading import generate_paper_history
                    nifty_rows = generate_paper_history("NC", 21808, iv, bars_count=len(candles), base_price=25000.0)
                    compare_closes = [float(r["close"]) for r in nifty_rows if r.get("close")]
                    self._compare_cache = (iv, len(candles), compare_closes)

            rendered = render_candlestick_chart(
                candles=candles,
                width=w,
                total_height=h,
                symbol=sym,
                interval=label_str,
                show_ema=self.show_ema,
                show_rsi=self.show_rsi,
                show_vwap=self.show_vwap,
                show_sr=self.show_sr,
                compare_symbol="NIFTY50" if compare_closes else "",
                compare_closes=compare_closes,
                zoom_bars=self.zoom_bars,
                pan_offset=self.pan_offset,
                fit_all=self.fit_all,
                crosshair_idx=self.crosshair_idx,
                crosshair_price=self.crosshair_price,
                show_volume=self._show_volume,
                live_ltp=ltp,
                pos_price=pos_price,
                pos_qty=pos_qty,
                bar_countdown_sec=countdown,
                status_note=status_note,
            )
            canvas.set_chart(rendered)
        elif closes and any(v > 0 for v in closes):
            rendered = render_chart(
                values=closes,
                volumes=volumes if self._show_volume else None,
                width=w,
                total_height=h,
                symbol=sym,
                interval=label_str,
                show_stats=True,
                show_vol_strip=self._show_volume,
                zoom_bars=self.zoom_bars,
                pan_offset=self.pan_offset,
                fit_all=self.fit_all,
                timestamps=[c.timestamp for c in candles] if candles else None,
                crosshair_idx=self.crosshair_idx,
                crosshair_price=self.crosshair_price,
                live_ltp=ltp,
                bar_countdown_sec=countdown,
                status_note=status_note,
            )
            canvas.set_chart(rendered)
        else:
            p = current_palette()
            no_data = Text()
            no_data.append(f"\n  [ ◌ Awaiting Market Feed · {sym} ({label_str}) ]\n", style=f"bold {p.primary}")
            no_data.append("  Data Source : Sharekhan REST API & WebSocket Stream\n", style=p.muted)
            no_data.append(f"  Instrument  : {self.item.get('exchange', 'NC')} {self.item.get('scripCode', '')}\n", style=p.muted)
            if ltp and ltp > 0:
                no_data.append(f"  Last Price  : ₹{ltp:,.2f}\n", style=f"bold {p.fg}")
            else:
                no_data.append("  Last Price  : ₹--.-- (awaiting first tick)\n", style=p.subtle)
            no_data.append("  Candlesticks and intraday volume form in real time as market ticks arrive.\n", style=p.subtle)
            canvas.set_chart(no_data)

    def on_theme_changed(self) -> None:
        if self._rows:
            self.show(self._rows, self.current_iv)
        else:
            self._render_canvas()

    def on_resize(self, event: Any) -> None:
        if self._resize_timer is not None:
            self._resize_timer.stop()
        self._resize_timer = self.set_timer(0.1, self._render_canvas)

    def show(self, rows: list[dict], interval: str = "") -> None:
        if not self.is_mounted:
            return
        p = current_palette()
        self._rows = rows
        iv = interval or self.current_iv

        quotes = _get_quotes(self.app)
        tape_candles = []
        sec = INTERVAL_SECONDS.get(iv, 60)
        if quotes and quotes.has_live_ticks(self.feed_key):
            if iv in SUB_MINUTE_INTERVALS:
                tape_candles = quotes.get_candles(self.feed_key, sec)
            elif sec <= 300:
                candles_from_tape = quotes.get_candles(self.feed_key, sec)
                if len(candles_from_tape) >= 5:
                    tape_candles = candles_from_tape

        candles: list[Candle] = []
        closes: list[float] = []
        volumes: list[float] = []

        if tape_candles:
            candles = tape_candles
            closes = [c.close for c in candles]
            volumes = [c.volume for c in candles]
        else:
            for r in rows:
                try:
                    c_close = float(r.get("close") or r.get("Close") or 0.0)
                    c_open = float(r.get("open") or r.get("Open") or c_close)
                    c_high = float(r.get("high") or r.get("High") or max(c_open, c_close))
                    c_low = float(r.get("low") or r.get("Low") or min(c_open, c_close))
                    c_vol = float(r.get("volume") or r.get("Volume") or r.get("vol") or r.get("qty") or r.get("v") or 0.0)
                    ts = str(r.get("tradeDate") or r.get("TradeDate") or r.get("date") or r.get("timestamp") or "")

                    # Epoch timestamp float for live tick alignment
                    epoch_ts = float(r.get("timestamp") or 0.0)
                    if not epoch_ts and ts:
                        try:
                            from datetime import datetime
                            t_time = str(r.get("tradeTime") or "")
                            combined = f"{ts} {t_time}".strip()
                            for fmt_str in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                                try:
                                    epoch_ts = datetime.strptime(combined if t_time else ts, fmt_str).timestamp()
                                    break
                                except Exception:
                                    pass
                        except Exception:
                            epoch_ts = 0.0

                    if c_close > 0:
                        closes.append(c_close)
                        volumes.append(c_vol)
                        candles.append(
                            Candle(
                                timestamp=ts,
                                open=c_open,
                                high=max(c_high, c_open, c_close),
                                low=min(c_low, c_open, c_close),
                                close=c_close,
                                volume=c_vol,
                                ts=epoch_ts,
                            )
                        )
                except (TypeError, ValueError):
                    continue

        self._candles = candles
        self._closes = closes
        self._volumes = volumes
        self._render_canvas()

        # Update Meta label
        self._update_meta()

        # Populate table (for audit & test contracts)
        t = self.query_one("#hist", DataTable)
        t.clear()
        for r in reversed(rows[-400:]):
            row_cells = []
            for key, _ in HIST_COLS:
                v = r.get(key) or r.get(key.title()) or r.get(key.lower()) or ""
                style = ""
                if key == "close":
                    try:
                        fv = float(str(v).replace(",", ""))
                        style = f"bold {p.bull}" if fv > 0 else ""
                    except ValueError:
                        pass
                elif key in ("high",):
                    style = p.bull
                elif key in ("low",):
                    style = p.bear
                row_cells.append(Text(str(v), style=style) if style else Text(str(v)))
            t.add_row(*row_cells)

    def _update_meta(self) -> None:
        p = current_palette()
        meta = Text()
        iv_lbl = INTERVAL_LABELS.get(self.current_iv, self.current_iv)
        mode_badge = "CANDLE" if self.mode == "candle" else "LINE"
        meta.append(f"[{iv_lbl} {mode_badge}]", style=f"bold {p.primary}")

        sec = INTERVAL_SECONDS.get(self.current_iv, 0)
        if sec > 0:
            import time as _t
            countdown = int(sec - (_t.time() % sec))
            mins, secs = divmod(max(0, countdown), 60)
            meta.append(f" ⏳ {mins:02d}:{secs:02d}", style=f"bold {p.warn}")

        # Technical analysis insights from real closes
        if len(self._closes) >= 20:
            from sktui.chart import calc_ema, calc_sma
            ema9 = calc_ema(self._closes, 9)
            sma20 = calc_sma(self._closes, 20)
            if ema9 and sma20 and ema9[-1] is not None and sma20[-1] is not None:
                if ema9[-1] > sma20[-1]:
                    meta.append("  ▲ BULLISH (EMA9>SMA20)", style=f"bold {p.bull}")
                else:
                    meta.append("  ▼ BEARISH (EMA9<SMA20)", style=f"bold {p.bear}")

        if len(self._closes) >= 14 and self.show_rsi:
            from sktui.chart import calc_rsi
            rsis = calc_rsi(self._closes, 14)
            if rsis and rsis[-1] is not None:
                last_rsi = rsis[-1]
                if last_rsi >= 70:
                    meta.append(f"  · RSI {last_rsi:.1f} (Overbought)", style=f"bold {p.bear}")
                elif last_rsi <= 30:
                    meta.append(f"  · RSI {last_rsi:.1f} (Oversold)", style=f"bold {p.bull}")
                else:
                    meta.append(f"  · RSI {last_rsi:.1f}", style=p.muted)

        pos_closes = [c for c in self._closes if c > 0]
        if pos_closes:
            hi = max(pos_closes)
            lo = min(pos_closes)
            last_c = pos_closes[-1]
            meta.append(f"  ·  LTP ₹{last_c:,.2f}  [H: ₹{hi:,.2f}  L: ₹{lo:,.2f}]", style=f"bold {p.fg}")
        meta.append(f"  ({len(self._candles) or len(self._rows):,} bars)", style=p.subtle)
        try:
            self.query_one("#chart-meta", Static).update(meta)
        except Exception:
            pass

    def _chart_meta(self) -> dict:
        try:
            return self.query_one("#chart-out", InteractiveChartCanvas).meta or {}
        except Exception:
            return {}

    def on_interactive_chart_canvas_clicked(self, msg: InteractiveChartCanvas.Clicked) -> None:
        msg.stop()
        if msg.idx is not None and msg.idx == self.crosshair_idx and msg.price is None:
            self.crosshair_idx = None
            self.crosshair_price = None
        else:
            self.crosshair_idx = msg.idx
            self.crosshair_price = msg.price
        self._render_canvas()

    def on_interactive_chart_canvas_wheel(self, msg: InteractiveChartCanvas.Wheel) -> None:
        msg.stop()
        if msg.shift:
            if msg.direction > 0:
                self.action_pan_right()
            else:
                self.action_pan_left()
        else:
            if msg.direction > 0:
                self.action_zoom_out()
            else:
                self.action_zoom_in()

    def action_crosshair_left(self) -> None:
        m = self._chart_meta()
        n = int(m.get("n") or len(self._candles) or 0)
        if n <= 0:
            return
        if self.crosshair_idx is None:
            self.crosshair_idx = n - 1
        else:
            nxt = self.crosshair_idx - 1
            if nxt < 0 and not self.fit_all and m.get("start", 0) > 0:
                self.pan_offset += 1
                nxt = 0
            self.crosshair_idx = max(0, min(n - 1, nxt))
        self._render_canvas()

    def action_crosshair_right(self) -> None:
        m = self._chart_meta()
        n = int(m.get("n") or len(self._candles) or 0)
        if n <= 0:
            return
        if self.crosshair_idx is None:
            self.crosshair_idx = n - 1
        else:
            nxt = self.crosshair_idx + 1
            if nxt >= n and self.pan_offset > 0:
                self.pan_offset -= 1
                nxt = n - 1
            self.crosshair_idx = max(0, min(n - 1, nxt))
        self._render_canvas()

    def action_crosshair_up(self) -> None:
        m = self._chart_meta()
        hi = float(m.get("hi") or 100.0)
        lo = float(m.get("lo") or 90.0)
        step = max(0.01, (hi - lo) * 0.02)
        if self.crosshair_price is None:
            self.crosshair_price = (hi + lo) / 2.0
        self.crosshair_price = min(hi, self.crosshair_price + step)
        self._render_canvas()

    def action_crosshair_down(self) -> None:
        m = self._chart_meta()
        hi = float(m.get("hi") or 100.0)
        lo = float(m.get("lo") or 90.0)
        step = max(0.01, (hi - lo) * 0.02)
        if self.crosshair_price is None:
            self.crosshair_price = (hi + lo) / 2.0
        self.crosshair_price = max(lo, self.crosshair_price - step)
        self._render_canvas()

    def action_pan_left(self) -> None:
        m = self._chart_meta()
        n_tot = int(m.get("n_total") or len(self._candles) or 0)
        span = int(m.get("end", 0) - m.get("start", 0))
        max_pan = max(0, n_tot - span)
        self.pan_offset = min(max_pan, self.pan_offset + 10)
        self._render_canvas()

    def action_pan_right(self) -> None:
        self.pan_offset = max(0, self.pan_offset - 10)
        self._render_canvas()

    def action_pan_start(self) -> None:
        m = self._chart_meta()
        n_tot = int(m.get("n_total") or len(self._candles) or 0)
        span = int(m.get("end", 0) - m.get("start", 0))
        self.pan_offset = max(0, n_tot - span)
        self._render_canvas()

    def action_snap_live(self) -> None:
        self.pan_offset = 0
        self.crosshair_idx = None
        self.crosshair_price = None
        self._render_canvas()

    def action_toggle_fit_all(self) -> None:
        self.fit_all = not self.fit_all
        self.zoom_bars = None
        self.pan_offset = 0
        self.crosshair_idx = None
        self._render_canvas()

    def action_toggle_zen(self) -> None:
        self.zen_mode = not self.zen_mode
        self.set_class(self.zen_mode, "chart-zen")
        self.call_after_refresh(self._render_canvas)

    def action_toggle_table(self) -> None:
        t = self.query_one("#hist", DataTable)
        self.table_visible = not self.table_visible
        t.set_class(not self.table_visible, "hidden-drawer")
        self.call_after_refresh(self._render_canvas)

    def action_quick_buy(self) -> None:
        quotes = _get_quotes(self.app)
        ltp = quotes.ltp(self.feed_key) if quotes else None
        price = self.crosshair_price or ltp or 0.0
        info = dict(self.item)
        info["side"] = "B"
        if price > 0:
            info["price"] = f"{price:.2f}"
        self.app.push_screen(OrderTicket(info))

    def action_quick_sell(self) -> None:
        quotes = _get_quotes(self.app)
        ltp = quotes.ltp(self.feed_key) if quotes else None
        price = self.crosshair_price or ltp or 0.0
        info = dict(self.item)
        info["side"] = "S"
        if price > 0:
            info["price"] = f"{price:.2f}"
        self.app.push_screen(OrderTicket(info))

    def action_cycle_scalper_tf(self) -> None:
        scalper = ["tick", "1second", "5second", "15second", "30second", "1minute"]
        try:
            idx = scalper.index(self.current_iv)
        except ValueError:
            idx = -1
        next_iv = scalper[(idx + 1) % len(scalper)]
        self.set_interval_val(next_iv)

    def action_prev_interval(self) -> None:
        try:
            idx = self.CYCLE_INTERVALS.index(self.current_iv)
        except ValueError:
            idx = 1
        new_iv = self.CYCLE_INTERVALS[(idx - 1) % len(self.CYCLE_INTERVALS)]
        self.set_interval_val(new_iv)

    def action_next_interval(self) -> None:
        try:
            idx = self.CYCLE_INTERVALS.index(self.current_iv)
        except ValueError:
            idx = 0
        new_iv = self.CYCLE_INTERVALS[(idx + 1) % len(self.CYCLE_INTERVALS)]
        self.set_interval_val(new_iv)

    def action_zoom_in(self) -> None:
        m = self._chart_meta()
        n_total = int(m.get("n_total") or len(self._candles) or 60)
        cur = self.zoom_bars or int(m.get("end", n_total) - m.get("start", 0)) or 40
        if self.fit_all:
            self.fit_all, cur = False, n_total
        self.zoom_bars = step_zoom(cur, n_total, -1)
        self.crosshair_idx = None
        self._render_canvas()

    def action_zoom_out(self) -> None:
        m = self._chart_meta()
        n_total = int(m.get("n_total") or len(self._candles) or 60)
        cur = self.zoom_bars or int(m.get("end", n_total) - m.get("start", 0)) or 40
        if self.fit_all:
            self.fit_all, cur = False, n_total
        self.zoom_bars = step_zoom(cur, n_total, 1)
        self.crosshair_idx = None
        self._render_canvas()

    def action_toggle_compare(self) -> None:
        self.compare_nifty = not self.compare_nifty
        self._render_canvas()

    def action_toggle_mode(self) -> None:
        self.mode = "line" if self.mode == "candle" else "candle"
        self._render_canvas()
        self._update_meta()

    def action_toggle_ema(self) -> None:
        self.show_ema = not self.show_ema
        self.show_vwap = self.show_ema
        self._render_canvas()
        self._update_meta()

    def action_toggle_rsi(self) -> None:
        self.show_rsi = not self.show_rsi
        self._render_canvas()
        self._update_meta()

    def action_toggle_volume(self) -> None:
        self._show_volume = not self._show_volume
        self._render_canvas()
        self._update_meta()

    def action_toggle_sr(self) -> None:
        self.show_sr = not self.show_sr
        self._render_canvas()
        self._update_meta()


# ══════════════════════════════════════════════════════════════════════════════
#  DetailScreen — order history & trades
# ══════════════════════════════════════════════════════════════════════════════

class DetailScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
    ]

    def __init__(self, row: dict) -> None:
        super().__init__()
        self.row = row
        self._oh_rows: list[dict] = []
        self._ot_rows: list[dict] = []

    def compose(self) -> ComposeResult:
        sym = get(self.row, "tradingSymbol") or "Order"
        oid = get(self.row, "orderId") or "—"
        with Vertical(classes="modal wide"):
            yield Label(f"⬡  Order Detail  —  {sym}  #{oid}",
                        classes="title")
            yield Label("  Lifecycle History", classes="field-group-label")
            yield DataTable(id="oh", cursor_type="row")
            yield Label("  Executed Trades", classes="field-group-label")
            yield DataTable(id="ot", cursor_type="row")
            yield Static("  Esc / q = close", classes="hint")
            with Horizontal(classes="row buttons"):
                yield Button("✗  Close", id="close-btn", variant="primary")

    def on_mount(self) -> None:
        try:
            self.query_one("#oh", DataTable).focus()
        except Exception:
            pass
        self.fetch()

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)

    def on_theme_changed(self) -> None:
        try:
            fill_table(self.query_one("#oh", DataTable), self._oh_rows)
            fill_table(self.query_one("#ot", DataTable), self._ot_rows)
        except Exception:
            pass

    @work(thread=True)
    def fetch(self) -> None:
        c, r    = getattr(self.app, "client", None), self.row
        ex, oid = get(r, "exchange"), get(r, "orderId")
        oh_fn = getattr(c, "order_history", None) if c else None
        ot_fn = getattr(c, "order_trades", None) if c else None
        for wid, fn in (("#oh", oh_fn), ("#ot", ot_fn)):
            rows = []
            if callable(fn):
                try:
                    rows = fn(ex, oid) or []
                except Exception:
                    rows = []
            if not rows and wid == "#oh":
                evs = [ev for ev in audit_trail.recent_events(limit=500) if ev.order_id == str(oid)]
                if evs:
                    rows = [{
                        "time": ev.timestamp[11:19] if len(ev.timestamp) >= 19 else ev.timestamp,
                        "event": ev.event_type,
                        "status": ev.status or "-",
                        "qty": ev.quantity,
                        "price": ev.price,
                        "reason": ev.reason or "-",
                    } for ev in evs]
                elif r:
                    rows = [{
                        "time": get(r, "orderTime", "requestTime", default="—"),
                        "event": "SNAPSHOT",
                        "status": get(r, "orderStatus", "status", default="—"),
                        "qty": get(r, "quantity", default="—"),
                        "price": get(r, "price", default="—"),
                        "reason": get(r, "rejectionReason", default="—"),
                    }]
            if wid == "#oh":
                self._oh_rows = rows
            else:
                self._ot_rows = rows
            if self.is_mounted:
                self.app.call_from_thread(
                    fill_table, self.query_one(wid, DataTable), rows)


# ══════════════════════════════════════════════════════════════════════════════
#  QuoteScreen — live tick data
# ══════════════════════════════════════════════════════════════════════════════

class QuoteScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
    ]

    def __init__(self, key: str, label: str) -> None:
        super().__init__()
        self.key_, self.label = key, label

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal wide"):
            yield Label(f"⬡  Live Quote  —  {self.label}", classes="title")
            yield DataTable(id="q", cursor_type="row")
            yield Static(
                "  ⬢  Live streaming data  ·  Esc / q = close",
                classes="hint")
            with Horizontal(classes="row buttons"):
                yield Button("✗  Close", id="close-btn", variant="primary")

    def on_mount(self) -> None:
        t = self.query_one("#q", DataTable)
        t.add_column("Field", key="field")
        t.add_column("Value", key="value")
        t.focus()
        self.set_interval(1, self.paint)
        self.paint()

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)

    def on_theme_changed(self) -> None:
        self.paint()

    def paint(self) -> None:
        try:
            t = self.query_one("#q", DataTable)
        except Exception:
            return
        p    = current_palette()
        data = _get_tick_data(self.app, self.key_)
        if not data:
            if "__waiting__" not in t.rows:
                t.clear()
                t.add_row(Text("⟳ waiting for live feed…", style=p.subtle), Text("—", style=p.subtle), key="__waiting__")
            else:
                try:
                    t.update_cell_at((0, 0), Text("⟳ waiting for live feed…", style=p.subtle))
                    t.update_cell_at((0, 1), Text("—", style=p.subtle))
                except Exception:
                    pass
            return
        sorted_keys = sorted(data)
        curr_keys = [rk.value for rk in t.rows.keys()]
        cols = list(t.columns.keys())
        c_field = "field" if "field" in t.columns else (cols[0] if len(cols) >= 1 else None)
        c_val   = "value" if "value" in t.columns else (cols[1] if len(cols) >= 2 else None)
        if curr_keys == sorted_keys and c_field is not None and c_val is not None:
            for k in sorted_keys:
                v = data[k]
                val_text = Text(
                    fmt(v),
                    style=sign_style(v) if k in ("ltp", "rsChange", "perChange") else p.fg,
                )
                try:
                    t.update_cell(k, c_field, Text(human(k), style=p.muted), update_width=False)
                    t.update_cell(k, c_val, val_text, update_width=False)
                except Exception:
                    pass
        else:
            saved_row = t.cursor_row
            t.clear()
            for k in sorted_keys:
                v        = data[k]
                val_text = Text(
                    fmt(v),
                    style=sign_style(v) if k in ("ltp", "rsChange", "perChange") else p.fg)
                t.add_row(Text(human(k), style=p.muted), val_text, key=k)
            if 0 <= saved_row < t.row_count:
                t.move_cursor(row=saved_row)


# ══════════════════════════════════════════════════════════════════════════════
#  WhatIfScreen — simulate order impact
# ══════════════════════════════════════════════════════════════════════════════

class WhatIfScreen(ModalScreen):
    """Simulate order impact without executing. Read-only — no broker request."""
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def __init__(self, item: dict | None = None) -> None:
        super().__init__()
        self.item = item or {}

    def compose(self) -> ComposeResult:
        p = current_palette()
        with VerticalScroll(classes="modal"):
            yield Label("⬡  What-If  —  Simulate Order Impact",
                        classes="title")
            yield Static(
                Text("  No broker request will be submitted."
                     "  Read-only portfolio simulation.", style=p.muted),
                id="wi-hint",
                classes="hint")
            yield Rule()
            yield Label("Order Parameters", classes="field-group-label")
            with Horizontal(classes="row"):
                yield Select([("▲  BUY", "B"), ("▼  SELL", "S")],
                             value=self.item.get("side", "B") if self.item.get("side") in ("B", "S") else "B",
                             allow_blank=False, id="wi-side")
                yield Input(
                    str(self.item.get("tradingSymbol", "")),
                    placeholder="Symbol  e.g. ONGC", id="wi-sym")
                yield Input(str(self.item.get("quantity", "100")),
                            placeholder="Quantity", id="wi-qty")
                yield Input(str(self.item.get("price", "0")),
                            placeholder="Price  (0 = market estimate)",
                            id="wi-price")
            yield Rule()
            yield Static("", id="wi-result", classes="whatif-result")
            with Horizontal(classes="row buttons"):
                yield Button("⬡  Simulate Impact",  id="wi-calc",  variant="primary")
                yield Button("✗  Close",            id="wi-close")

    def on_mount(self) -> None:
        self.query_one("#wi-qty", Input).focus()
        if self.item.get("tradingSymbol"):
            self._calc()

    def on_theme_changed(self) -> None:
        try:
            p = current_palette()
            self.query_one("#wi-hint", Static).update(
                Text("  No broker request will be submitted.  Read-only portfolio simulation.", style=p.muted)
            )
            if str(self.query_one("#wi-result", Static).render()):
                self._calc()
        except Exception:
            pass

    @on(Button.Pressed, "#wi-close")
    def _close(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted)
    def _on_submit(self) -> None:
        self._calc()

    @on(Button.Pressed, "#wi-calc")
    def _calc(self) -> None:
        p = current_palette()
        try:
            qty_raw = (self.query_one("#wi-qty", Input).value.strip() or "0").replace(",", "")
            price_raw = (self.query_one("#wi-price", Input).value.strip() or "0").replace(",", "")
            qty   = int(float(qty_raw))
            price = float(price_raw)
            sym   = self.query_one("#wi-sym",  Input).value.strip().upper()
            side  = str(self.query_one("#wi-side", Select).value)
        except (ValueError, TypeError) as e:
            self.query_one("#wi-result", Static).update(
                Text(f"✗  Invalid input: {e}", style=f"bold {p.bear}"))
            return
        if qty <= 0:
            self.query_one("#wi-result", Static).update(
                Text("✗  Quantity must be > 0", style=f"bold {p.bear}"))
            return
        if price < 0:
            self.query_one("#wi-result", Static).update(
                Text("✗  Price cannot be negative", style=f"bold {p.bear}"))
            return

        # Try resolving live LTP if price is 0
        est_price = price
        is_market = (price == 0)
        if is_market and sym:
            exch = str(self.item.get("exchange") or "NC")
            code = self.item.get("scripCode")
            if code:
                tick = _get_tick_data(self.app, f"{exch}{code}")
                if tick.get("ltp") and float(tick["ltp"]) > 0:
                    est_price = float(tick["ltp"])

        notional = qty * est_price if est_price > 0 else 0
        side_txt  = "▲ BUY" if side == "B" else "▼ SELL"
        clr       = p.bull if side == "B" else p.bear

        t = Text()
        t.append("DRY RUN — SIMULATION ONLY\n\n",
                 style=f"bold {p.primary}")
        t.append("  Symbol:             ", style=p.muted)
        t.append(f"{sym or '(not set)'}\n", style=f"bold {p.fg}")
        t.append("  Direction:          ", style=p.muted)
        t.append(f"{side_txt}\n", style=f"bold {clr}")
        t.append("  Quantity:           ", style=p.muted)
        t.append(f"{qty:,} units\n", style=p.fg)

        if est_price > 0:
            lbl = "Est. Market LTP:    " if is_market else "Est. Price:         "
            t.append(f"  {lbl}", style=p.muted)
            t.append(f"₹{est_price:,.2f}\n", style=p.fg)
            t.append("  Est. Notional:      ", style=p.muted)
            t.append(f"₹{notional:,.2f}\n", style=f"bold {p.warn}")
            # Brokerage estimate (flat fee placeholder)
            brok = min(20.0, notional * 0.0003)
            t.append("  Est. Brokerage:     ", style=p.muted)
            t.append(f"₹{brok:.2f}\n", style=p.subtle)
        else:
            t.append("  Order Type:         ", style=p.muted)
            t.append("MARKET  (price not provided)\n",
                     style=f"bold {p.warn}")

        t.append("\n  Risk Checks:        ", style=p.muted)
        t.append("Simulation — not validated against live limits\n",
                 style=p.subtle)
        t.append("\n  ✓  No order submitted to broker\n",
                 style=f"bold {p.bull}")
        self.query_one("#wi-result", Static).update(t)


# ══════════════════════════════════════════════════════════════════════════════
#  SystemStatusScreen
# ══════════════════════════════════════════════════════════════════════════════

class SystemStatusScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
    ]

    def _build_status_text(self) -> Text:
        p = current_palette()
        c = getattr(self.app, "client", None)
        is_paper = getattr(c, "paper", True) if c else True
        full_name = (getattr(c, "full_name", None) or getattr(c, "login_id", "PAPER_USER")) if c else "DISCONNECTED"
        cid = (getattr(c, "customer_id", None) or getattr(c, "cid", "—")) if c else "—"
        api_key = str(getattr(c, "api_key", "") or "") if c else ""
        masked_key = f"{api_key[:8]}{'*' * 18}" if api_key else "N/A (Paper Mode)"
        exchanges = getattr(c, "exchanges", None) or list(EXCH_NAMES)

        t = Text()
        t.append("\n  ── Environment ───────────────────────────────────\n\n",
                  style=p.subtle)
        t.append("  Environment:        ", style=p.muted)
        env = "PAPER" if is_paper else "LIVE"
        t.append(f"{env}\n",
                 style=f"bold {p.warn}" if is_paper else f"bold {p.bear}")
        t.append("  Theme:              ", style=p.muted)
        t.append(f"{self.app.theme}  ({'Dark' if p.dark else 'Light'})\n",
                 style=f"bold {p.primary}")
        t.append("  Account:            ", style=p.muted)
        t.append(f"{full_name}  (CID: {cid})\n", style=p.fg)
        t.append("  API Key:            ", style=p.muted)
        t.append(f"{masked_key}\n", style=p.subtle)
        t.append("  Exchanges:          ", style=p.muted)
        t.append(f"{' · '.join(exchanges)}\n",
                 style=f"bold {p.primary}")
        pub_ip = getattr(self.app, "public_ip", "Fetching…")
        t.append("  Public IP Address:  ", style=p.muted)
        t.append(f"{pub_ip}  (whitelist on https://api.sharekhan.com)\n",
                 style=f"bold {p.primary}")

        t.append("\n  ── Component Health ──────────────────────────────\n\n",
                  style=p.subtle)
        components = [
            ("CLI Process",       True),
            ("Broker Connection", c is not None),
            ("Order Gateway",     c is not None),
            ("Audit Log",         True),
        ]
        for name, ok in components:
            t.append(f"  {name:<22}", style=p.muted)
            t.append(f"{'  ✓ RUNNING' if ok else '  ✗ DOWN'}\n",
                     style=f"bold {p.bull}" if ok else f"bold {p.bear}")

        quotes = _get_quotes(self.app)
        feed_ok = bool(getattr(self.app, "raw_ticks", {})) or (quotes is not None and bool(getattr(quotes, "_quotes", {})))
        t.append("  WebSocket Feed      ", style=p.muted)
        t.append(f"  {'  ✓ ACTIVE' if feed_ok else '  ○ IDLE'}\n",
                 style=f"bold {p.bull}" if feed_ok else p.subtle)

        t.append("\n  ── Feed Latency Histogram (RTT) ──────────────────\n\n",
                  style=p.subtle)
        from sktui.services.feed_health import feed_health
        for bucket_lbl, cnt, pct in feed_health.latency_histogram():
            bar = "█" * int(pct / 5.0)
            t.append(f"  {bucket_lbl:<12} ", style=p.muted)
            t.append(f"{bar:<20} ", style=f"bold {p.primary}")
            t.append(f"{cnt:>3} ({pct:5.1f}%)\n", style=p.fg)
        t.append(
            f"\n  Avg RTT: {feed_health.avg_latency_ms:.1f}ms  ·  "
            f"P95 RTT: {feed_health.p95_latency_ms:.1f}ms  ·  "
            f"Tick Rate: {feed_health.ticks_per_second:.1f}/s\n",
            style=p.subtle,
        )

        t.append("\n  ── Quick Commands  (type after / in command bar) ──\n\n",
                  style=p.subtle)
        for cmd, (desc, _) in list(SLASH_COMMANDS.items())[:12]:
            t.append(f"  {cmd:<18}", style=f"bold {p.primary}")
            t.append(f"{desc}\n",    style=p.muted)
        t.append("\n  F1 for full command reference\n", style=p.subtle)
        return t

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal"):
            yield Label("⬡  System Status", classes="title")
            yield Static(self._build_status_text(), id="status-body")
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("✗  Close", id="close-btn", variant="primary")

    def on_mount(self) -> None:
        try:
            self.query_one("#close-btn", Button).focus()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        try:
            self.query_one("#status-body", Static).update(self._build_status_text())
        except Exception:
            pass

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  RiskScreen
# ══════════════════════════════════════════════════════════════════════════════

class RiskScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
    ]

    def _build_risk_text(self) -> Text:
        p = current_palette()
        c = getattr(self.app, "client", None)
        is_paper = getattr(c, "paper", True) if c else True
        ws = _workspace_screen(self.app)
        risk_eng = (
            getattr(getattr(ws, "order_service", None), "risk_engine", None)
            or getattr(getattr(self.app.screen, "order_service", None), "risk_engine", None)
            or RiskEngine()
        )
        lim = risk_eng.limits
        t = Text()

        t.append("\n  ── Risk Status ────────────────────────────────────────\n\n", style=p.subtle)
        t.append("  Risk State:            ", style=p.muted)
        t.append("LOCKOUT ACTIVE\n" if risk_eng._lockout_active else "NORMAL (ACTIVE)\n",
                 style=f"bold {p.bear}" if risk_eng._lockout_active else f"bold {p.bull}")
        t.append("  Order Enforcement:     ", style=p.muted)
        t.append(f"{'ENABLED' if lim.enforce_limits else 'MONITORING ONLY'}\n",
                 style=f"bold {p.bull}" if lim.enforce_limits else f"bold {p.warn}")
        t.append("  Environment:           ", style=p.muted)
        t.append(f"{'PAPER SIMULATION' if is_paper else 'LIVE EXCHANGE'}\n",
                 style=f"bold {p.warn}" if is_paper else f"bold {p.bear}")

        t.append("\n  ── Policy Limits & Thresholds ────────────────────────\n\n", style=p.subtle)
        t.append("  Max Order Quantity:    ", style=p.muted)
        t.append(f"{lim.max_order_qty:,} units\n", style=f"bold {p.primary}")
        t.append("  Max Order Value:       ", style=p.muted)
        t.append(f"₹{lim.max_order_value:,.2f}\n", style=f"bold {p.primary}")
        t.append("  Max Position Value:    ", style=p.muted)
        t.append(f"₹{lim.max_position_value:,.2f} per symbol\n", style=f"bold {p.primary}")
        t.append("  Max Daily Drawdown:    ", style=p.muted)
        t.append(f"-₹{lim.max_daily_loss:,.2f}\n", style=f"bold {p.bear}")
        t.append("  Rate Limiter:          ", style=p.muted)
        t.append(f"{lim.max_orders_per_minute} orders / min (Burst Protection)\n", style=f"bold {p.warn}")

        t.append("\n  ── Safety Invariants ──────────────────────────────────\n\n", style=p.subtle)
        invariants = [
            "Pre-trade size & exposure checks run on every order",
            "Stop-loss guardrail verified for derivatives",
            "Immutable audit trail logged to ~/.sktui/audit/audit.jsonl",
            "Lockout triggered automatically upon max daily loss breach",
        ]
        for inv in invariants:
            t.append("  ✓  ", style=f"bold {p.bull}")
            t.append(f"{inv}\n", style=p.muted)
        return t

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label("🛡  Professional Risk Controls & Governance", classes="title")
            yield Static(self._build_risk_text(), id="risk-body")
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("✗  Close", id="close-btn", variant="primary")

    def on_mount(self) -> None:
        try:
            self.query_one("#close-btn", Button).focus()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        try:
            self.query_one("#risk-body", Static).update(self._build_risk_text())
        except Exception:
            pass

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  HelpScreen
# ══════════════════════════════════════════════════════════════════════════════

class HelpScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close"),
    ]

    def _build_help_text(self) -> Text:
        p = current_palette()
        t = Text()

        t.append("\n  ── Slash Commands  (type in command bar below) ─────────────\n\n",
                  style=p.subtle)
        for cmd, (desc, _) in SLASH_COMMANDS.items():
            t.append(f"  {cmd:<22}", style=f"bold {p.primary}")
            t.append(f"{desc}\n",    style=p.muted)

        t.append("\n  ── Keyboard Shortcuts ──────────────────────────────────────\n\n",
                  style=p.subtle)
        shortcuts = [
            ("a",       "Add symbol to watchlist  (works from ANY tab)"),
            ("Del",     "Remove symbol from watchlist"),
            ("b / s",   "Buy / sell selected symbol (watchlist/positions/holdings)"),
            ("m",       "Modify selected order"),
            ("x",       "Cancel selected order"),
            ("X",       "Cancel ALL open orders"),
            ("i",       "Order history & trades"),
            ("c",       "Historical chart  (works from watchlist/orders/positions/holdings)"),
            ("?",       "Live quote detail"),
            ("p",       "Products & services"),
            ("r",       "Refresh data"),
            ("d",       "Toggle feed log"),
            ("v",       "Toggle volume bars in chart"),
            ("ctrl+t",  "Open interactive Theme Picker (live preview)"),
            ("ctrl+p",  "Open Command Palette & Theme Switcher"),
            ("/",       "Focus command bar"),
            ("F1",      "This help screen"),
            ("1–7",     "Switch workspace panes & desk views"),
            ("ctrl+l",  "Log out"),
            ("q",       "Quit"),
        ]
        for key, desc in shortcuts:
            t.append(f"  {key:<22}", style=f"bold {p.warn}")
            t.append(f"{desc}\n",    style=p.muted)

        t.append("\n  ── Chart  (c key or /chart) ────────────────────────────────\n\n",
                  style=p.subtle)
        chart_help = [
            ("Select interval", "Drop-down / pills at top of chart screen"),
            ("v key",          "Toggle between price chart and volume bars"),
            ("Table below",    "Shows OHLCV records, newest on top"),
            ("Stats line",     "Open / High / Low / Close / Avg / Change%"),
        ]
        for key, desc in chart_help:
            t.append(f"  {key:<22}", style=f"bold {p.teal}")
            t.append(f"{desc}\n",    style=p.muted)

        t.append("\n  ── Trading Safety Model ────────────────────────────────────\n\n",
                  style=p.subtle)
        safety = [
            ("PAPER mode",      "All orders simulated — nothing reaches the broker"),
            ("Order preview",   "Review screen appears before every order submission"),
            ("Confirmation",    "Consequential actions require explicit approval  (y/n)"),
            ("/whatif",         "Portfolio impact simulation without executing"),
            ("/risk",           "Current risk state, controls, and safety invariants"),
            ("/kill",           "Emergency: disable automation immediately"),
            ("X  (shift-x)",    "Emergency: cancel all open orders"),
            ("/status",         "Broker connection, feed, and system health"),
        ]
        for key, desc in safety:
            t.append(f"  {key:<22}", style=f"bold {p.bull}")
            t.append(f"{desc}\n",    style=p.muted)

        t.append("\n  ── Architecture ────────────────────────────────────────────\n\n",
                  style=p.subtle)
        t.append("  CLI  →  Control Plane  →  Risk Engine"
                 "  →  Broker Adapter  →  Exchange\n", style=p.muted)
        t.append("  Every live order passes pre-trade validation before submission.\n",
                 style=p.muted)
        return t

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label("⬡  SKTUI  —  Professional Trading CLI",
                        classes="title")
            yield Static(self._build_help_text(), id="help-body")
            with Horizontal(classes="row buttons"):
                yield Button("✗  Close  (Esc / q)", id="close-btn",
                             variant="primary")

    def on_mount(self) -> None:
        try:
            self.query_one("#close-btn", Button).focus()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        try:
            self.query_one("#help-body", Static).update(self._build_help_text())
        except Exception:
            pass

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  ProductsScreen
# ══════════════════════════════════════════════════════════════════════════════

PRODUCT_LINKS = [
    ("Equity (NSE/BSE) incl. ETFs",        "API · trade here (NC/BC)",             ""),
    ("Futures & Options (NSE)",             "API · trade here (NF; FS/FI/OS/OI)",   ""),
    ("Currency derivatives (NSE)",          "API · trade here (RN)",                ""),
    ("Commodity (MCX)",                     "API · trade here (MX)",                ""),
    ("Funds, holdings, positions, history", "API · tabs in this app",               ""),
    ("IPO",                                 "Not in API · browser",                 "https://www.sharekhan.com/ipo"),
    ("Mutual Funds / SIP / ELSS / NFO",     "Not in API · browser",                 "https://www.sharekhan.com/mutual-funds"),
    ("F&O Solutions",                       "Not in API · browser",                 "https://www.sharekhan.com/futures-and-options"),
    ("Pattern Finder",                      "Not in API · browser",                 "https://www.sharekhan.com/pattern-finder"),
    ("Algo Solutions",                      "Not in API · browser",                 "https://www.sharekhan.com/algo-solutions"),
    ("Margin Funding / Financing",          "Not in API · browser",                 "https://www.sharekhan.com/margin-funding"),
    ("MTF",                                 "Not in API · browser",                 "https://www.sharekhan.com/margin-trading-facility"),
    ("PMS",                                 "Not in API · browser",                 "https://www.sharekhan.com/portfolio-management-services"),
    ("Fixed Deposits & Bonds",             "Not in API · browser",                 "https://www.sharekhan.com/bonds"),
    ("Global markets (US stocks)",          "Not in API · browser",                 "https://www.sharekhan.com/global-markets/invest-in-us-stocks"),
    ("Brokerage calculator",                "Calculator · browser",                 "https://www.sharekhan.com/financial-calculator/brokerage-calculator"),
    ("Margin calculator",                   "Calculator · browser",                 "https://www.sharekhan.com/margin-calculator"),
    ("Full web platform",                   "Browser",                               "https://newtrade.sharekhan.com/skweb/login/"),
]


class ProductsScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal wide"):
            yield Label("⬡  Markets & Products", classes="title")
            yield DataTable(id="prod", cursor_type="row")
            yield Static(
                "  Enter = open in browser  ·  Esc / q = close",
                classes="hint")
            with Horizontal(classes="row buttons"):
                yield Button("✗  Close", id="close-btn", variant="primary")

    def on_mount(self) -> None:
        t = self.query_one("#prod", DataTable)
        t.add_columns("Product / Service", "Access")
        self._populate()
        t.focus()

    def _populate(self) -> None:
        p = current_palette()
        t = self.query_one("#prod", DataTable)
        saved_row = t.cursor_row
        t.clear()
        for name, how, url in PRODUCT_LINKS:
            style = (p.bull if how.startswith("API")
                     else p.warn if how.startswith("Not") else p.primary)
            icon  = "  ↗" if url else ""
            t.add_row(Text(name, style=p.fg), Text(how + icon, style=style))
        if 0 <= saved_row < t.row_count:
            t.move_cursor(row=saved_row)

    def on_theme_changed(self) -> None:
        try:
            self._populate()
        except Exception:
            pass

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)

    @on(DataTable.RowSelected, "#prod")
    def _open(self, e: DataTable.RowSelected) -> None:
        if 0 <= e.cursor_row < len(PRODUCT_LINKS):
            name, _, url = PRODUCT_LINKS[e.cursor_row]
            if url:
                try:
                    webbrowser.open(url)
                    self.app.notify(f"Opened {name}")
                except Exception:
                    self.app.notify(f"URL: {url}")
            else:
                self.app.notify("Trade this directly here (watchlist: b / s)")


# ══════════════════════════════════════════════════════════════════════════════
#  AuditTrailModal — Execution Audit Ledger and Replay
# ══════════════════════════════════════════════════════════════════════════════

class AuditTrailModal(ModalScreen):
    """Inspect the immutable execution audit log with timestamps, statuses, and reasons."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
        Binding("r",      "refresh_audit", "Refresh", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal wide"):
            yield Label("📜  Execution Audit Ledger (audit.jsonl)", classes="title")
            yield DataTable(id="audit-table", cursor_type="row")
            yield Static("  r = refresh  ·  Esc / q = close  ·  Immutable append-only execution log", classes="hint")
            with Horizontal(classes="row buttons"):
                yield Button("↻  Refresh", id="refresh-btn", variant="default")
                yield Button("✗  Close", id="close-btn", variant="primary")

    def on_mount(self) -> None:
        t = self.query_one("#audit-table", DataTable)
        t.add_columns(
            "Timestamp",
            "Event Type",
            "Symbol",
            "Side",
            "Qty",
            "Price",
            "Status",
            "Reason / Details",
        )
        self._populate()
        t.focus()

    def _populate(self) -> None:
        p = current_palette()
        t = self.query_one("#audit-table", DataTable)
        t.clear()
        events = audit_trail.recent_events(limit=60)
        if not events:
            t.add_row(
                Text("—", style=p.subtle),
                Text("NO EVENTS", style=p.subtle),
                Text("—", style=p.subtle),
                Text("—", style=p.subtle),
                "—",
                "—",
                "—",
                Text("No execution audit entries recorded yet", style=p.subtle),
            )
            return
        for ev in reversed(events):
            time_part = ev.timestamp.split("T")[-1][:8] if "T" in ev.timestamp else ev.timestamp
            s_style = (p.bull if ev.side == "B" else p.bear if ev.side == "S" else p.muted)
            ev_style = (
                p.bull if "FILL" in ev.event_type or "PASS" in ev.event_type
                else p.bear if "FAIL" in ev.event_type or "REJ" in ev.event_type or "BLOCK" in ev.event_type
                else p.warn if "CANCEL" in ev.event_type
                else p.primary
            )
            t.add_row(
                Text(time_part, style=p.fg),
                Text(ev.event_type, style=ev_style),
                Text(ev.symbol or "—", style=p.fg),
                Text(ev.side or "—", style=s_style),
                f"{ev.quantity:,}" if ev.quantity else "—",
                f"₹{ev.price:,.2f}" if ev.price else "—",
                ev.status or "—",
                ev.reason or "—",
            )

    def action_refresh_audit(self) -> None:
        self._populate()

    def on_theme_changed(self) -> None:
        try:
            self._populate()
        except Exception:
            pass

    @on(Button.Pressed, "#refresh-btn")
    def _refresh(self) -> None:
        self._populate()

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  PortfolioAnalyticsModal — PnL Decomposition & Exposure Attribution
# ══════════════════════════════════════════════════════════════════════════════

class PortfolioAnalyticsModal(ModalScreen):
    """Decomposed PnL, sector attribution, exposure heatmap, and win/loss ratio."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
        Binding("e",      "export_csv",    "Export CSV", show=False),
    ]

    def _get_portfolio_inputs(self) -> tuple[list, dict, list]:
        ws = _workspace_screen(self.app)
        data_dict = getattr(ws, "data", None) or getattr(self.app.screen, "data", None) or {}
        positions = data_dict.get("positions", [])
        orders = data_dict.get("orders", [])
        ticks = dict(getattr(self.app, "raw_ticks", {}) or {})
        quotes = _get_quotes(self.app)
        if quotes and hasattr(quotes, "snapshot_all"):
            for k, v in quotes.snapshot_all().items():
                if k not in ticks:
                    ticks[k] = v
        return positions, ticks, orders

    def _build_analytics_text(self) -> Text:
        p = current_palette()
        t = Text()

        positions, ticks, orders = self._get_portfolio_inputs()
        summary = PortfolioAnalytics.analyze(positions, ticks, orders)

        t.append("\n  ── PnL Decomposition ──────────────────────────────────\n\n", style=p.subtle)
        t.append("  Realized PnL:          ", style=p.muted)
        r_col = p.bull if summary.realized_pnl >= 0 else p.bear
        t.append(f"₹{summary.realized_pnl:,.2f}\n", style=f"bold {r_col}")

        t.append("  Unrealized PnL:        ", style=p.muted)
        u_col = p.bull if summary.unrealized_pnl >= 0 else p.bear
        t.append(f"₹{summary.unrealized_pnl:,.2f}\n", style=f"bold {u_col}")

        t.append("  Total Net PnL:         ", style=p.muted)
        tot_col = p.bull if summary.total_pnl >= 0 else p.bear
        t.append(f"₹{summary.total_pnl:,.2f}\n", style=f"bold {tot_col}")

        t.append("\n  ── P/L by Symbol & Product Type ───────────────────────\n\n", style=p.subtle)
        if summary.symbol_pnl:
            for sym, s_pnl in sorted(summary.symbol_pnl.items(), key=lambda x: x[1], reverse=True):
                sc = p.bull if s_pnl >= 0 else p.bear
                t.append(f"  {sym:<16} ", style=p.fg)
                t.append(f"₹{s_pnl:+,.2f}\n", style=f"bold {sc}")
        else:
            t.append("  No active symbol P/L\n", style=p.subtle)

        if summary.product_pnl:
            prod_str = "  ·  ".join(f"{prd}: ₹{val:+,.2f}" for prd, val in summary.product_pnl.items())
            t.append(f"  By Product:            {prod_str}\n", style=p.muted)

        t.append("\n  ── Exposure & Concentration Heatmap ───────────────────\n\n", style=p.subtle)
        t.append(f"  Gross Market Exposure: ₹{summary.total_gross_exposure:,.2f}\n", style=f"bold {p.primary}")
        t.append(f"  Net Market Exposure:   ₹{summary.net_exposure:,.2f}\n", style=p.fg)
        t.append("  Top Concentrations:    ", style=p.muted)
        if summary.top_concentrations:
            conc_str = " · ".join(f"{sym} ({pct:.1f}%)" for sym, pct in summary.top_concentrations if pct > 0)
            t.append(f"{conc_str or 'No active positions'}\n", style=f"bold {p.warn}" if conc_str else p.subtle)
        else:
            t.append("No active positions\n", style=p.subtle)

        t.append("\n  ── Sector Attribution Breakdown ───────────────────────\n\n", style=p.subtle)
        if summary.sector_breakdown:
            for sec, val in summary.sector_breakdown.items():
                pct = (val / summary.total_gross_exposure * 100.0) if summary.total_gross_exposure > 0 else 0.0
                bar = "█" * int(pct / 5)
                t.append(f"  {sec:<16} ", style=p.fg)
                t.append(f"{bar:<20} ", style=f"bold {p.teal}")
                t.append(f"₹{val:,.2f} ({pct:.1f}%)\n", style=p.muted)
        else:
            t.append("  No sector exposure\n", style=p.subtle)

        t.append("\n  ── Trade Execution & R-Multiple Statistics ────────────\n\n", style=p.subtle)
        t.append(f"  Session Turnover:      ₹{summary.turnover:,.2f}  ({summary.trade_count} trades)\n", style=p.fg)
        t.append(f"  Profitable Positions:  {summary.win_count}  ·  Losing: {summary.loss_count}\n", style=p.fg)
        t.append(f"  Win Rate:              {summary.win_rate_pct:.1f}%\n", style=f"bold {p.bull}" if summary.win_rate_pct >= 50 else f"bold {p.warn}")
        t.append(f"  Profit Factor:         {summary.profit_factor:.2f}  ·  Avg R-Multiple: {summary.avg_r_multiple:.2f}R\n", style=f"bold {p.primary}")
        return t

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label("📊  Portfolio & Exposure Analytics", classes="title")
            yield Static(self._build_analytics_text(), id="analytics-body")
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("⬇ Export CSV (e)", id="export-csv-btn", variant="success")
                yield Button("✗  Close", id="close-btn", variant="primary")

    def on_mount(self) -> None:
        try:
            self.query_one("#close-btn", Button).focus()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        try:
            self.query_one("#analytics-body", Static).update(self._build_analytics_text())
        except Exception:
            pass

    def action_export_csv(self) -> None:
        self._export_csv()

    @on(Button.Pressed, "#export-csv-btn")
    def _export_csv(self) -> None:
        positions, ticks, orders = self._get_portfolio_inputs()
        out_path = PortfolioAnalytics.export_csv(positions, ticks, orders)
        self.app.notify(f"✓ Analytics exported to {out_path}", timeout=6)

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  AlertsModal — view & manage price / technical alerts
# ══════════════════════════════════════════════════════════════════════════════

class AlertsModal(ModalScreen):
    """View and manage configured price & technical alerts."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
        Binding("delete,x", "delete_selected", "Delete Alert", show=False),
    ]

    def __init__(self, alert_engine: Any) -> None:
        super().__init__()
        self.alert_engine = alert_engine

    def _build_header_text(self) -> Text:
        p = current_palette()
        t = Text()
        t.append("  Configure alerts using: ", style=p.muted)
        t.append("/alert <SYMBOL> <CONDITION> <TARGET>", style=f"bold {p.primary}")
        t.append("  (e.g., /alert RELIANCE > 3000, /alert TCS RSI > 70)  ·  Del/x = remove selected\n\n", style=p.subtle)
        return t

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal wide"):
            yield Label("🔔  Price & Technical Alerts Registry", classes="title")
            yield Static(self._build_header_text(), id="alerts-header")
            yield DataTable(id="t-alerts", cursor_type="row")
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("Clear All Alerts", id="clear-alerts", variant="error")
                yield Button("✗  Close", id="close-btn", variant="primary")

    def on_mount(self) -> None:
        t = self.query_one("#t-alerts", DataTable)
        t.add_column("Alert ID", key="id")
        t.add_column("Symbol", key="sym")
        t.add_column("Condition", key="cond")
        t.add_column("Target Value", key="val")
        t.add_column("Status", key="status")
        t.add_column("Triggered At", key="trig_at")
        self._populate()
        t.focus()

    def _populate(self) -> None:
        p = current_palette()
        t = self.query_one("#t-alerts", DataTable)
        t.clear()
        alerts = getattr(self.alert_engine, "alerts", []) if self.alert_engine else []
        for a in alerts:
            st = Text("TRIGGERED", style=f"bold {p.warn}") if a.triggered else Text("ACTIVE", style=f"bold {p.bull}")
            val_str = f"₹{a.target_value:,.2f}" if "RSI" not in a.condition and "VOL" not in a.condition else f"{a.target_value:.1f}"
            t.add_row(
                a.id,
                Text(a.symbol, style=f"bold {p.fg_strong}"),
                Text(a.condition, style=f"bold {p.primary}"),
                val_str,
                st,
                a.triggered_at or "—",
                key=a.id,
            )

    def on_theme_changed(self) -> None:
        try:
            self.query_one("#alerts-header", Static).update(self._build_header_text())
            self._populate()
        except Exception:
            pass

    def action_delete_selected(self) -> None:
        if not self.alert_engine:
            return
        t = self.query_one("#t-alerts", DataTable)
        alerts = getattr(self.alert_engine, "alerts", [])
        if 0 <= t.cursor_row < len(alerts):
            aid = alerts[t.cursor_row].id
            if hasattr(self.alert_engine, "remove_alert"):
                self.alert_engine.remove_alert(aid)
            else:
                alerts.pop(t.cursor_row)
            self._populate()
            self.app.notify(f"Removed alert {aid}")

    @on(Button.Pressed, "#clear-alerts")
    def _clear_all(self) -> None:
        if self.alert_engine and hasattr(self.alert_engine, "clear_all"):
            self.alert_engine.clear_all()
        t = self.query_one("#t-alerts", DataTable)
        t.clear()
        self.app.notify("All alerts cleared")

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  ASCII Range Slider & Focus / Depth Panel
# ══════════════════════════════════════════════════════════════════════════════

def render_range_bar(low: float, high: float, current: float, width: int = 24) -> Text:
    """Render an ASCII range slider indicating where current price sits between High and Low."""
    p = current_palette()
    t = Text()
    t.append(f"L: ₹{low:,.2f} ", style=f"bold {p.bear}")
    if high <= low or current <= 0:
        bar = "─" * width
        t.append(f"[{bar}]", style=p.subtle)
        t.append(f" H: ₹{high:,.2f}", style=f"bold {p.bull}")
    else:
        frac = max(0.0, min(1.0, (current - low) / (high - low)))
        pos = int(frac * (width - 1))
        left = "═" * pos
        right = "─" * (width - 1 - pos)
        t.append("[", style=p.divider)
        t.append(left, style=p.primary)
        t.append("●", style=f"bold {p.bull}")
        t.append(right, style=p.subtle)
        t.append("]", style=p.divider)
        pct = frac * 100.0
        t.append(f" H: ₹{high:,.2f} ", style=f"bold {p.bull}")
        t.append(f"({pct:.1f}% of range)", style=p.subtle)
    return t


class FocusModal(ModalScreen):
    """Contextual selected symbol focus and market depth panel."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q", "dismiss(None)", "Close", show=False),
        Binding("b", "buy", "Buy"),
        Binding("s", "sell", "Sell"),
        Binding("c", "chart", "Chart"),
        Binding("a", "alert", "Alert"),
    ]

    def __init__(self, item: dict, quote: dict | None = None) -> None:
        super().__init__()
        self.item = item
        self.quote = quote or {}

    def compose(self) -> ComposeResult:
        sym = str(self.item.get("tradingSymbol") or self.item.get("symbol") or "SCRIP")
        exch = str(self.item.get("exchange") or "NC")

        with VerticalScroll(classes="modal focus-modal"):
            yield Label(f"⊙  Focus Inspection  —  {sym}  ({exch})", classes="title")
            yield Static("", id="focus-hdr")
            yield Rule()
            yield Label("Intraday Range", classes="section-label")
            yield Static("", id="focus-range")
            yield Rule()
            yield Label("Top of Book & Spread", classes="section-label")
            yield Static("", id="focus-tob")
            yield Rule()
            yield Label("VWAP & Trend Bias", classes="section-label")
            yield Static("", id="focus-vwap")
            yield Rule()
            yield Static("", id="focus-stats")
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("Buy (b)", id="f-buy", variant="success")
                yield Button("Sell (s)", id="f-sell", variant="error")
                yield Button("Chart (c)", id="f-chart", variant="primary")
                yield Button("Alert (a)", id="f-alert")
                yield Button("Close (Esc)", id="f-close")

    def on_mount(self) -> None:
        self._render_focus()
        try:
            self.query_one("#f-buy", Button).focus()
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        if self.is_mounted:
            self._render_focus()

    def _render_focus(self) -> None:
        p = current_palette()
        sym = str(self.item.get("tradingSymbol") or self.item.get("symbol") or "SCRIP")
        exch = str(self.item.get("exchange") or "NC")
        code = self.item.get("scripCode") or self.item.get("scrip_code") or self.item.get("code") or ""
        key = f"{exch}{code}" if code else ""
        live_tick = _get_tick_data(self.app, key) if key else {}
        q = dict(live_tick)
        q.update({k: v for k, v in self.quote.items() if v is not None and v != ""})

        ltp = float(q.get("ltp") or q.get("lastTradedPrice") or self.item.get("price") or 0.0)
        open_p = float(q.get("open") or q.get("openPrice") or ltp)
        hi_p = float(q.get("high") or q.get("highPrice") or max(ltp, open_p))
        lo_p = float(q.get("low") or q.get("lowPrice") or min(ltp, open_p))
        close_p = float(q.get("close") or q.get("closePrice") or open_p)
        chg = float(q.get("rsChange") or (ltp - close_p if ltp and close_p else 0.0))
        pct = float(q.get("perChange") or ((chg / close_p * 100.0) if close_p > 0 else 0.0))
        vol = float(q.get("qty") or q.get("volume") or q.get("vol") or 0.0)
        bid = float(q.get("bidPrice") or q.get("bid") or 0.0)
        ask = float(q.get("offPrice") or q.get("ask") or 0.0)
        vwap = float(q.get("atp") or q.get("vwap") or ((hi_p + lo_p + close_p) / 3.0))

        hdr = Text()
        hdr.append(f"  {sym}  ", style=f"bold {p.on_primary} on {p.primary}")
        hdr.append(f"  ₹{ltp:,.2f}  ", style=f"bold {p.bull if chg >= 0 else p.bear}")
        sign = "+" if chg >= 0 else ""
        hdr.append(f"({sign}{chg:,.2f} / {sign}{pct:.2f}%)  ", style=sign_style(chg))

        tob = Text()
        spread = max(0.0, ask - bid) if (ask > 0 and bid > 0) else 0.0
        spread_bps = (spread / ltp * 10000.0) if ltp > 0 else 0.0
        tob.append(f"  Bid: ₹{bid:,.2f}  ", style=f"bold {p.bull}")
        tob.append(f"│  Spread: ₹{spread:,.2f} ({spread_bps:.1f} bps)  ", style=p.subtle)
        tob.append(f"│  Ask: ₹{ask:,.2f}", style=f"bold {p.bear}")

        v_txt = Text()
        v_dist = ((ltp - vwap) / vwap * 100.0) if vwap > 0 else 0.0
        bias_tag = "BULLISH ▲" if v_dist >= 0 else "BEARISH ▼"
        bias_color = p.bull if v_dist >= 0 else p.bear
        v_txt.append(f"  VWAP: ₹{vwap:,.2f}  │  ", style=p.muted)
        v_txt.append(f"Distance: {v_dist:+.2f}%  │  Bias: {bias_tag}", style=f"bold {bias_color}")

        stats = Text()
        stats.append(f"  Open: ₹{open_p:,.2f}   High: ₹{hi_p:,.2f}   Low: ₹{lo_p:,.2f}   Close: ₹{close_p:,.2f}\n", style=p.muted)
        stats.append(f"  Day Volume: {vol:,.0f}   Scrip: {self.item.get('scripCode', '—')}", style=p.subtle)

        try:
            self.query_one("#focus-hdr", Static).update(hdr)
            self.query_one("#focus-range", Static).update(render_range_bar(lo_p, hi_p, ltp, width=28))
            self.query_one("#focus-tob", Static).update(tob)
            self.query_one("#focus-vwap", Static).update(v_txt)
            self.query_one("#focus-stats", Static).update(stats)
        except Exception:
            pass

    def action_buy(self) -> None:
        self.dismiss(("trade", "B", self.item))
    action_action_buy = action_buy

    def action_sell(self) -> None:
        self.dismiss(("trade", "S", self.item))
    action_action_sell = action_sell

    def action_chart(self) -> None:
        self.dismiss(("chart", self.item))
    action_action_chart = action_chart

    def action_alert(self) -> None:
        self.dismiss(("alert", self.item))
    action_action_alert = action_alert

    @on(Button.Pressed, "#f-buy")
    def _b(self) -> None:
        self.action_buy()

    @on(Button.Pressed, "#f-sell")
    def _s(self) -> None:
        self.action_sell()

    @on(Button.Pressed, "#f-chart")
    def _c(self) -> None:
        self.action_chart()

    @on(Button.Pressed, "#f-alert")
    def _a(self) -> None:
        self.action_alert()

    @on(Button.Pressed, "#f-close")
    def _cl(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  Real-Time Market Scanner Modal
# ══════════════════════════════════════════════════════════════════════════════

class ScannerModal(ModalScreen):
    """Real-Time Market Scanner modal for movers, volume spikes, and breakouts."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q", "dismiss(None)", "Close", show=False),
        Binding("1", "tab_movers", "Movers"),
        Binding("2", "tab_volume", "Volume"),
        Binding("3", "tab_breakouts", "Breakouts"),
        Binding("4", "tab_vwap", "VWAP"),
        Binding("r", "refresh", "Refresh"),
        Binding("b", "buy", "Buy"),
        Binding("s", "sell", "Sell"),
        Binding("c", "chart", "Chart"),
    ]

    def __init__(self, scanner: MarketScanner) -> None:
        super().__init__()
        self.scanner = scanner
        self.active_category: str = "movers"
        self.results: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal wide"):
            yield Label("⌕  Real-Time Market Scanner", classes="title")
            with Horizontal(classes="row"):
                yield Button("[1] Top Movers", id="btn-movers", variant="primary")
                yield Button("[2] Volume Spikes", id="btn-vol")
                yield Button("[3] Breakouts", id="btn-break")
                yield Button("[4] VWAP Trends", id="btn-vwap")
                yield Button("↻ Refresh (r)", id="btn-refresh")

            yield DataTable(id="t-scanner", cursor_type="row")
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("Buy (b)", id="sc-buy", variant="success")
                yield Button("Sell (s)", id="sc-sell", variant="error")
                yield Button("Chart (c)", id="sc-chart", variant="primary")
                yield Button("Close (Esc)", id="sc-close")

    def on_mount(self) -> None:
        t = self.query_one("#t-scanner", DataTable)
        t.add_column("Symbol", key="sym")
        t.add_column("Exch", key="exch")
        t.add_column("LTP", key="ltp")
        t.add_column("Change", key="chg")
        t.add_column("% Chg", key="pct")
        t.add_column("Volume", key="vol")
        t.add_column("Day Range %", key="range")
        t.add_column("VWAP Dist", key="vwap")
        t.add_column("Spread", key="spread")
        self.run_scan("movers")
        try:
            t.focus()
        except Exception:
            pass

    def run_scan(self, category: str) -> None:
        p = current_palette()
        self.active_category = category
        if category == "movers":
            self.results = self.scanner.scan_top_movers(20)
        elif category == "volume":
            self.results = self.scanner.scan_volume_spikes(20)
        elif category == "breakouts":
            self.results = self.scanner.scan_breakouts(20)
        elif category == "vwap":
            self.results = self.scanner.scan_vwap_trend(20)

        btn_map = {
            "movers": "#btn-movers",
            "volume": "#btn-vol",
            "breakouts": "#btn-break",
            "vwap": "#btn-vwap",
        }
        for cat, btn_id in btn_map.items():
            try:
                self.query_one(btn_id, Button).variant = "primary" if cat == category else "default"
            except Exception:
                pass

        t = self.query_one("#t-scanner", DataTable)
        t.clear()
        seen_keys: set[str] = set()
        for idx, r in enumerate(self.results):
            chg_style = sign_style(r["change"])
            base_key = f"{r['exchange']}_{r['symbol']}_{r.get('scripCode') or idx}"
            row_k = base_key
            cnt = 1
            while row_k in seen_keys:
                row_k = f"{base_key}_{cnt}"
                cnt += 1
            seen_keys.add(row_k)

            t.add_row(
                Text(r["symbol"], style=f"bold {p.fg_strong}"),
                r["exchange"],
                f"₹{r['ltp']:,.2f}",
                Text(f"{r['change']:+,.2f}", style=chg_style),
                Text(f"{r['pctChange']:+.2f}%", style=chg_style),
                f"{r['volume']:,.0f}",
                f"{r['pctOfRange']:.1f}%",
                Text(f"{r['vwapDist']:+.2f}%", style=sign_style(r["vwapDist"])),
                f"₹{r['spread']:.2f}",
                key=row_k,
            )

    def get_selected(self) -> dict | None:
        t = self.query_one("#t-scanner", DataTable)
        if t.row_count == 0 or t.cursor_row >= len(self.results):
            return None
        return self.results[t.cursor_row]

    def action_tab_movers(self) -> None:
        self.run_scan("movers")
    action_action_tab_movers = action_tab_movers

    def action_tab_volume(self) -> None:
        self.run_scan("volume")
    action_action_tab_volume = action_tab_volume

    def action_tab_breakouts(self) -> None:
        self.run_scan("breakouts")
    action_action_tab_breakouts = action_tab_breakouts

    def action_tab_vwap(self) -> None:
        self.run_scan("vwap")
    action_action_tab_vwap = action_tab_vwap

    def action_refresh(self) -> None:
        self.run_scan(self.active_category)
    action_action_refresh = action_refresh

    def on_theme_changed(self) -> None:
        if self.is_mounted:
            self.run_scan(self.active_category)

    def action_buy(self) -> None:
        sel = self.get_selected()
        if sel:
            self.dismiss(("trade", "B", sel))
    action_action_buy = action_buy

    def action_sell(self) -> None:
        sel = self.get_selected()
        if sel:
            self.dismiss(("trade", "S", sel))
    action_action_sell = action_sell

    def action_chart(self) -> None:
        sel = self.get_selected()
        if sel:
            self.dismiss(("chart", sel))
    action_action_chart = action_chart

    @on(DataTable.RowSelected, "#t-scanner")
    def _on_row_selected(self, e: DataTable.RowSelected) -> None:
        self.action_chart()

    @on(Button.Pressed, "#btn-movers")
    def _m(self) -> None:
        self.action_tab_movers()

    @on(Button.Pressed, "#btn-vol")
    def _v(self) -> None:
        self.action_tab_volume()

    @on(Button.Pressed, "#btn-break")
    def _b(self) -> None:
        self.action_tab_breakouts()

    @on(Button.Pressed, "#btn-vwap")
    def _w(self) -> None:
        self.action_tab_vwap()

    @on(Button.Pressed, "#btn-refresh")
    def _rf(self) -> None:
        self.action_refresh()

    @on(Button.Pressed, "#sc-buy")
    def _by(self) -> None:
        self.action_buy()

    @on(Button.Pressed, "#sc-sell")
    def _sl(self) -> None:
        self.action_sell()

    @on(Button.Pressed, "#sc-chart")
    def _ch(self) -> None:
        self.action_chart()

    @on(Button.Pressed, "#sc-close")
    def _cls(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  Historical Tick Replay Controller Modal
# ══════════════════════════════════════════════════════════════════════════════

class ReplayModal(ModalScreen):
    """Interactive Historical Playback & Replay Controller."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q", "dismiss(None)", "Close", show=False),
        Binding("space", "toggle_play", "Play/Pause"),
        Binding("right", "step_forward", "Step"),
        Binding("r", "reset_replay", "Reset"),
    ]

    def __init__(self, replay_engine: ReplayEngine) -> None:
        super().__init__()
        self.engine = replay_engine

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal"):
            yield Label(f"▶  Historical Tick Replay  —  {self.engine.symbol} ({self.engine.exchange})", classes="title")
            yield Static("", id="replay-status")
            yield Static("", id="replay-quote")
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("Play/Pause (Space)", id="rep-play", variant="primary")
                yield Button("Step Next (→)", id="rep-step")
                yield Button("Reset (r)", id="rep-reset", variant="error")
                yield Button("Close (Esc)", id="rep-close")

    def on_mount(self) -> None:
        self.update_display()
        self.set_interval(0.2, self.update_display)

    def on_unmount(self) -> None:
        try:
            self.engine.pause()
        except Exception:
            pass

    def update_display(self) -> None:
        p = current_palette()
        st = self.query_one("#replay-status", Static)
        status_txt = Text()
        state = "PLAYING" if self.engine.is_playing else "PAUSED"
        color = p.bull if self.engine.is_playing else p.warn
        status_txt.append(f"  Status: {state}  ", style=f"bold {color}")
        status_txt.append(f"  Tick: {self.engine.current_tick_index} / {self.engine.total_ticks}  ", style=p.primary)
        status_txt.append(f"  Speed: {self.engine.speed:.1f}x\n", style=p.muted)
        st.update(status_txt)

        try:
            rq = self.query_one("#replay-quote", Static)
            cur = self.engine.current_tick
            tot = max(1, self.engine.total_ticks)
            pct = min(100.0, (self.engine.current_tick_index / tot) * 100.0)
            bar_len = 30
            filled = int((pct / 100.0) * bar_len)
            bar_str = "█" * filled + "░" * (bar_len - filled)
            q_txt = Text()
            q_txt.append(f"  [{bar_str}]  {pct:.1f}%\n", style=f"bold {p.primary}")
            if cur:
                ltp = float(cur.get("ltp") or 0.0)
                vol = float(cur.get("qty") or cur.get("volume") or 0.0)
                ts = str(cur.get("timestamp") or "")
                q_txt.append(f"  Current LTP: ₹{ltp:,.2f}  ·  Vol: {vol:,.0f}  ·  Time: {ts}\n", style=f"bold {p.bull if ltp > 0 else p.fg}")
            rq.update(q_txt)
        except Exception:
            pass

    def toggle_play(self) -> None:
        if self.engine.is_playing:
            self.engine.pause()
        else:
            self.engine.play()
        self.update_display()

    def action_toggle_play(self) -> None:
        self.toggle_play()

    def step_forward(self) -> None:
        self.engine.step()
        self.update_display()

    def action_step_forward(self) -> None:
        self.step_forward()

    def reset_replay(self) -> None:
        self.engine.reset()
        self.update_display()

    def action_reset_replay(self) -> None:
        self.reset_replay()

    def on_theme_changed(self) -> None:
        if self.is_mounted:
            self.update_display()

    @on(Button.Pressed, "#rep-play")
    def _p(self) -> None:
        self.toggle_play()

    @on(Button.Pressed, "#rep-step")
    def _s(self) -> None:
        self.step_forward()

    @on(Button.Pressed, "#rep-reset")
    def _r(self) -> None:
        self.reset_replay()

    @on(Button.Pressed, "#rep-close")
    def _c(self) -> None:
        self.engine.pause()
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  DebugModal — Runtime Diagnostics, Raw WS Payloads, API Timing & UI FPS
# ══════════════════════════════════════════════════════════════════════════════

class DebugModal(ModalScreen):
    """Runtime diagnostics panel (`--debug` or `/debug`) showing WS frames, API call times, and FPS."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q", "dismiss(None)", "Close", show=False),
        Binding("r", "refresh_debug", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label("🐞  SKTUI Runtime Diagnostics & Debug Panel", classes="title")
            yield Static("", id="debug-metrics")
            yield Rule()
            yield Label("Recent Raw WebSocket Payloads", classes="section-label")
            yield RichLog(id="debug-ws-log", max_lines=100, wrap=True, markup=False)
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("↻ Refresh (r)", id="dbg-refresh", variant="default")
                yield Button("✗  Close (Esc)", id="dbg-close", variant="primary")

    def on_mount(self) -> None:
        self.refresh_debug()
        self.set_interval(1.0, self.refresh_debug)

    def action_refresh_debug(self) -> None:
        self.refresh_debug()

    def refresh_debug(self) -> None:
        from sktui.services.feed_health import feed_health
        p = current_palette()
        c = getattr(self.app, "client", None)
        ws = _workspace_screen(self.app)
        api_lat = getattr(c, "last_api_latency_ms", 0.0) if c else 0.0
        fps = getattr(ws, "_ui_fps", getattr(self.app.screen, "_ui_fps", 60.0))

        t = Text()
        t.append("\n  ── Telemetry & Performance ────────────────────────────\n\n", style=p.subtle)
        t.append("  UI Frame Rate (est):   ", style=p.muted)
        t.append(f"{fps:.1f} FPS\n", style=f"bold {p.bull}")
        t.append("  Last REST API Call:    ", style=p.muted)
        t.append(f"{api_lat:.2f} ms\n", style=f"bold {p.primary}")
        t.append("  Feed State:            ", style=p.muted)
        t.append(f"{feed_health.feed_state}  (TPS: {feed_health.ticks_per_second:.1f}/s · Avg Ping: {feed_health.avg_latency_ms:.1f}ms)\n", style=p.fg)
        t.append("  Active Feed Keys:      ", style=p.muted)
        t.append(f"{len(getattr(self.app, 'raw_ticks', {}))}\n", style=f"bold {p.warn}")
        try:
            self.query_one("#debug-metrics", Static).update(t)
            ws_log = self.query_one("#debug-ws-log", RichLog)
            ws_log.clear()
            raw_frames = (
                getattr(ws, "_raw_ws_payloads", None)
                or getattr(self.app.screen, "_raw_ws_payloads", None)
                or getattr(self.app, "_raw_ws_payloads", [])
            )
            if raw_frames:
                for frame in list(raw_frames)[-15:]:
                    ws_log.write(str(frame))
            else:
                for k, v in list(getattr(self.app, "raw_ticks", {}).items())[:10]:
                    ws_log.write(f"{k}: {v}")
        except Exception:
            pass

    @on(Button.Pressed, "#dbg-refresh")
    def _r(self) -> None:
        self.refresh_debug()

    def on_theme_changed(self) -> None:
        if self.is_mounted:
            self.refresh_debug()

    @on(Button.Pressed, "#dbg-close")
    def _cl(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  ThemeModal — Live-Preview Institutional Theme Picker (`Ctrl+T` / `/theme`)
# ══════════════════════════════════════════════════════════════════════════════

class ThemeModal(ModalScreen):
    """Interactive color theme selector with instant live preview on row highlight."""
    BINDINGS = [
        Binding("escape", "cancel_preview", "Cancel & Revert"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._initial_theme: str = DEFAULT_THEME
        self._filtered_names: list[str] = []
        self._populating: bool = False

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal theme-modal"):
            yield Label("🎨  Workstation Theme Studio  —  Live Preview", classes="title")
            yield Input(
                placeholder="⌕  Filter themes (e.g. obsidian, bloomberg, daylight, nord, gruvbox, light)…",
                id="theme-filter",
            )
            yield DataTable(id="theme-table", cursor_type="row")
            yield Static(
                "  ↑↓ Preview live  ·  Enter = Apply & Save  ·  Esc = Revert",
                classes="hint",
            )
            with Horizontal(classes="row buttons"):
                yield Button("✓  Apply Theme", id="theme-apply", variant="primary")
                yield Button("✗  Cancel (Esc)", id="theme-cancel")

    def _ordered_themes(self) -> list[str]:
        avail = getattr(self.app, "available_themes", {})
        custom = [name for name in SKTUI_THEME_MAP if name in avail]
        builtin = sorted(name for name in avail if name not in SKTUI_THEME_MAP)
        return custom + builtin

    def on_mount(self) -> None:
        self._initial_theme = self.app.theme or DEFAULT_THEME
        t = self.query_one("#theme-table", DataTable)
        t.add_column("Theme", key="name")
        t.add_column("Mode", key="mode")
        t.add_column("Palette", key="swatch")
        t.add_column("Description", key="desc")
        self._populate("")
        t.focus()

    def _populate(self, query: str) -> None:
        self._populating = True
        try:
            p = current_palette()
            avail = getattr(self.app, "available_themes", {})
            q = query.strip().lower()
            t = self.query_one("#theme-table", DataTable)
            t.clear()
            self._filtered_names = []
            selected_idx = 0

            for name in self._ordered_themes():
                desc = THEME_DESCRIPTIONS.get(name, "Built-in Textual Theme")
                tp = palette_for_theme_name(name, avail)
                mode_lbl = "DARK" if tp.dark else "LIGHT"
                hay = f"{name} {mode_lbl} {desc}".lower()
                if q and q not in hay:
                    continue

                idx = len(self._filtered_names)
                self._filtered_names.append(name)
                if name == self.app.theme:
                    selected_idx = idx

                is_current = (name == self._initial_theme)
                prefix = "★ " if name in SKTUI_THEME_MAP else "  "
                suffix = " (active)" if is_current else ""
                name_cell = Text(f"{prefix}{name}{suffix}", style=f"bold {p.primary}" if name in SKTUI_THEME_MAP else p.fg)

                mode_cell = Text(
                    f" {mode_lbl} ",
                    style=f"bold {tp.fg} on {tp.panel}",
                )

                swatch = Text()
                for clr in (tp.bg, tp.primary, tp.secondary, tp.bull, tp.bear, tp.warn):
                    swatch.append("██", style=clr)
                    swatch.append(" ")

                t.add_row(name_cell, mode_cell, swatch, Text(desc, style=p.muted), key=name)

            if self._filtered_names:
                t.move_cursor(row=selected_idx)
        finally:
            self._populating = False

    @on(Input.Changed, "#theme-filter")
    def _on_filter(self, e: Input.Changed) -> None:
        self._populate(e.value)

    @on(Input.Submitted, "#theme-filter")
    def _on_filter_enter(self) -> None:
        if self._filtered_names:
            self._confirm_theme(self._filtered_names[0])

    @on(DataTable.RowHighlighted, "#theme-table")
    def _on_row_highlighted(self, e: DataTable.RowHighlighted) -> None:
        if self._populating:
            return
        try:
            theme_name = str(e.row_key.value)
            if theme_name and theme_name in self.app.available_themes and self.app.theme != theme_name:
                self.app.theme = theme_name
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        """Re-color ThemeModal text cells in-place so dark/light live preview stays high-contrast."""
        if self._populating:
            return
        try:
            p = current_palette()
            t = self.query_one("#theme-table", DataTable)
            for name in self._filtered_names:
                if name not in t.rows:
                    continue
                is_current = (name == self._initial_theme)
                prefix = "★ " if name in SKTUI_THEME_MAP else "  "
                suffix = " (active)" if is_current else ""
                name_cell = Text(
                    f"{prefix}{name}{suffix}",
                    style=f"bold {p.primary}" if name in SKTUI_THEME_MAP else p.fg,
                )
                desc = THEME_DESCRIPTIONS.get(name, "Built-in Textual Theme")
                t.update_cell(name, "name", name_cell)
                t.update_cell(name, "desc", Text(desc, style=p.muted))
        except Exception:
            pass

    @on(DataTable.RowSelected, "#theme-table")
    def _on_row_selected(self, e: DataTable.RowSelected) -> None:
        try:
            theme_name = str(e.row_key.value)
            if theme_name:
                self._confirm_theme(theme_name)
        except Exception:
            pass

    def _confirm_theme(self, theme_name: str) -> None:
        if theme_name in self.app.available_themes:
            self.app.theme = theme_name
            if not __import__("os").environ.get("PYTEST_CURRENT_TEST"):
                save_configured_theme(theme_name)
            self.app.notify(f"🎨 Theme applied: {theme_name}", timeout=4)
        self.dismiss(theme_name)

    def action_cancel_preview(self) -> None:
        if self.app.theme != self._initial_theme and self._initial_theme in self.app.available_themes:
            self.app.theme = self._initial_theme
        self.dismiss(None)

    @on(Button.Pressed, "#theme-apply")
    def _apply_btn(self) -> None:
        t = self.query_one("#theme-table", DataTable)
        if self._filtered_names and 0 <= t.cursor_row < len(self._filtered_names):
            self._confirm_theme(self._filtered_names[t.cursor_row])
        else:
            self._confirm_theme(self.app.theme)

    @on(Button.Pressed, "#theme-cancel")
    def _cancel_btn(self) -> None:
        self.action_cancel_preview()


class MarketDepthModal(ModalScreen):
    """Interactive 5-Level Market Depth (DOM Order Book) Ladder Modal."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("b", "quick_buy", "Buy @ Ask"),
        Binding("s", "quick_sell", "Sell @ Bid"),
        Binding("r", "refresh_depth", "Refresh"),
    ]

    def __init__(self, item: dict | None = None) -> None:
        super().__init__()
        self.item = item
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal", id="depth-modal-box"):
            yield Label(" ── 01 · LEVEL 2 MARKET DEPTH (DOM ORDER BOOK) ──────────────────────────", classes="section-label")
            yield MarketDepthWidget(id="depth-widget")
            with Horizontal(classes="row buttons-bar"):
                yield Button(" [b] BUY @ ASK ", id="btn-depth-buy", variant="primary")
                yield Button(" [s] SELL @ BID ", id="btn-depth-sell", variant="error")
                yield Button(" Close [Esc] ", id="btn-depth-close")

    def on_mount(self) -> None:
        if not self.item:
            ws = _workspace_screen(self.app)
            self.item = getattr(ws, "selected_symbol", None) or (ws.watch[0] if getattr(ws, "watch", None) else None)
        self._refresh()
        self._timer = self.set_interval(0.3, self._refresh)

    def _refresh(self) -> None:
        ws = _workspace_screen(self.app)
        quotes = getattr(ws, "quotes", None)
        if not self.item or not quotes:
            return
        feed_key_fn = getattr(ws, "feed_key", lambda it: it.get("tradingSymbol", ""))
        key = feed_key_fn(self.item)
        depth = quotes.get_depth(key)
        q = quotes.get(key)
        w = self.app.size.width if self.app else 60
        try:
            self.query_one("#depth-widget", MarketDepthWidget).update_depth_context(
                item=self.item,
                quote=q,
                depth=depth,
                width=w,
            )
        except Exception:
            pass

    def action_quick_buy(self) -> None:
        self.dismiss(("buy", self.item))

    def action_quick_sell(self) -> None:
        self.dismiss(("sell", self.item))

    def action_refresh_depth(self) -> None:
        self._refresh()

    @on(Button.Pressed, "#btn-depth-buy")
    def _buy(self) -> None:
        self.action_quick_buy()

    @on(Button.Pressed, "#btn-depth-sell")
    def _sell(self) -> None:
        self.action_quick_sell()

    @on(Button.Pressed, "#btn-depth-close")
    def _close(self) -> None:
        self.dismiss(None)


CHAIN_COLS = [
    ("c_oi",   "Call OI"),
    ("c_vol",  "Call Vol"),
    ("c_bid",  "Call Bid"),
    ("c_ask",  "Call Ask"),
    ("c_ltp",  "Call LTP"),
    ("strike", "STRIKE"),
    ("p_ltp",  "Put LTP"),
    ("p_bid",  "Put Bid"),
    ("p_ask",  "Put Ask"),
    ("p_vol",  "Put Vol"),
    ("p_oi",   "Put OI"),
]


class OptionChainModal(ModalScreen):
    """Interactive Options Chain Matrix for NSE F&O indices and equities."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("b", "quick_buy", "Buy Selected"),
        Binding("s", "quick_sell", "Sell Selected"),
        Binding("enter", "select_contract", "Focus Contract"),
        Binding("r", "refresh_chain", "Refresh"),
    ]

    def __init__(self, underlying: str = "NIFTY") -> None:
        super().__init__()
        self.underlying = underlying.strip().upper()
        self.spot_ltp: float = 24200.0
        self.atm_strike: float = 24200.0
        self.contracts: dict[float, dict[str, dict]] = {}  # strike -> {"CE": dict, "PE": dict}
        self.strikes_list: list[float] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal", id="option-chain-box"):
            yield Label(" ── 01 · INTERACTIVE OPTION CHAIN MATRIX (NSE F&O) ─────────────────────", classes="section-label")
            with Horizontal(classes="row"):
                yield Static(f" Underlying: {self.underlying}", id="chain-header-info", classes="url-display")
                yield Input(placeholder="Switch Underlying (e.g. NIFTY, BANKNIFTY, RELIANCE)", id="chain-sym-input")
                yield Button("Load", id="btn-load-chain", classes="btn-step")
            yield DataTable(id="chain-table", cursor_type="row")
            with Horizontal(classes="row buttons-bar"):
                yield Button(" [b] BUY CALL ", id="btn-buy-ce", variant="primary")
                yield Button(" [s] BUY PUT ", id="btn-buy-pe", variant="error")
                yield Button(" Focus Contract [Enter] ", id="btn-focus-contract")
                yield Button(" Close [Esc] ", id="btn-close-chain")

    def on_mount(self) -> None:
        ws = _workspace_screen(self.app)
        t = self.query_one("#chain-table", DataTable)
        for col_id, col_label in CHAIN_COLS:
            t.add_column(col_label, key=col_id)
        self.refresh_chain()
        t.focus()

    def refresh_chain(self) -> None:
        ws = _workspace_screen(self.app)
        quotes = getattr(ws, "quotes", None)
        from sktui.config import KNOWN_BASE_PRICES

        # Determine spot price
        spot = KNOWN_BASE_PRICES.get(self.underlying)
        if quotes:
            for k in (f"NC{self.underlying}", self.underlying, f"NF{self.underlying}"):
                q = quotes.get(k)
                if q and q.get("ltp"):
                    spot = float(q["ltp"])
                    break
        self.spot_ltp = spot or (24200.0 if "NIFTY" in self.underlying else 1000.0)

        # Step size
        if "BANKNIFTY" in self.underlying:
            step = 100.0
        elif "NIFTY" in self.underlying:
            step = 50.0
        elif self.spot_ltp > 2000:
            step = 50.0
        elif self.spot_ltp > 500:
            step = 20.0
        else:
            step = 5.0

        self.atm_strike = round(self.spot_ltp / step) * step
        strikes = [round(self.atm_strike + ((i - 5) * step), 2) for i in range(11)]
        self.strikes_list = strikes

        p = current_palette()
        hdr = self.query_one("#chain-header-info", Static)
        hdr.update(
            Text(
                f"  Underlying: {self.underlying}  ·  Spot: ₹{self.spot_ltp:,.2f}  ·  ATM Strike: {self.atm_strike:,.0f}  ·  Exp: 24/10/2026",
                style=f"bold {p.fg_strong}",
            )
        )

        t = self.query_one("#chain-table", DataTable)
        t.clear()
        self.contracts.clear()

        atm_row_idx = 0
        for idx, k in enumerate(strikes):
            diff = k - self.spot_ltp
            ce_intrinsic = max(0.0, self.spot_ltp - k)
            pe_intrinsic = max(0.0, k - self.spot_ltp)
            time_val = max(15.0, round((self.spot_ltp * 0.012) / (1 + (abs(diff) / (step * 3))), 2))
            ce_ltp = round(ce_intrinsic + time_val, 2)
            pe_ltp = round(pe_intrinsic + time_val, 2)

            ce_sym = f"{self.underlying}{int(k)}CE"
            pe_sym = f"{self.underlying}{int(k)}PE"

            self.contracts[k] = {
                "CE": {"tradingSymbol": ce_sym, "exchange": "NF", "scripCode": 45000 + idx, "strike": k, "optionType": "CE", "ltp": ce_ltp},
                "PE": {"tradingSymbol": pe_sym, "exchange": "NF", "scripCode": 46000 + idx, "strike": k, "optionType": "PE", "ltp": pe_ltp},
            }

            is_atm = (k == self.atm_strike)
            if is_atm:
                atm_row_idx = idx

            row_style = f"bold {p.on_primary} on {p.primary}" if is_atm else ""
            strike_cell = Text(f" ★ {k:,.0f} " if is_atm else f"   {k:,.0f}   ", style=f"bold {p.warn}" if is_atm else f"bold {p.fg}")

            ce_oi = int(max(1000, 50000 - abs(diff) * 30))
            pe_oi = int(max(1000, 48000 - abs(diff) * 28))
            ce_vol = int(ce_oi * 0.4)
            pe_vol = int(pe_oi * 0.38)

            t.add_row(
                Text(f"{ce_oi:,}", style=p.muted),
                Text(f"{ce_vol:,}", style=p.subtle),
                Text(f"₹{ce_ltp - 0.50:,.2f}", style=p.bull),
                Text(f"₹{ce_ltp + 0.50:,.2f}", style=p.bull),
                Text(f"₹{ce_ltp:,.2f}", style=f"bold {p.bull}"),
                strike_cell,
                Text(f"₹{pe_ltp:,.2f}", style=f"bold {p.bear}"),
                Text(f"₹{pe_ltp - 0.50:,.2f}", style=p.bear),
                Text(f"₹{pe_ltp + 0.50:,.2f}", style=p.bear),
                Text(f"{pe_vol:,}", style=p.subtle),
                Text(f"{pe_oi:,}", style=p.muted),
                key=str(k),
            )

        if 0 <= atm_row_idx < len(strikes):
            try:
                t.move_cursor(row=atm_row_idx)
            except Exception:
                pass

    @on(Button.Pressed, "#btn-load-chain")
    def _load_btn(self) -> None:
        inp = self.query_one("#chain-sym-input", Input).value.strip().upper()
        if inp:
            self.underlying = inp
            self.refresh_chain()

    @on(Input.Submitted, "#chain-sym-input")
    def _input_submitted(self, e: Input.Submitted) -> None:
        val = e.value.strip().upper()
        if val:
            self.underlying = val
            self.refresh_chain()

    def _selected_contract(self, pref_type: str = "CE") -> dict | None:
        t = self.query_one("#chain-table", DataTable)
        idx = t.cursor_row
        if 0 <= idx < len(self.strikes_list):
            k = self.strikes_list[idx]
            pair = self.contracts.get(k, {})
            return pair.get(pref_type)
        return None

    def action_quick_buy(self) -> None:
        c = self._selected_contract("CE")
        if c:
            self.dismiss(("trade", "B", c))

    def action_quick_sell(self) -> None:
        c = self._selected_contract("PE")
        if c:
            self.dismiss(("trade", "B", c))  # Buying a Put is directional sell

    def action_select_contract(self) -> None:
        c = self._selected_contract("CE")
        if c:
            self.dismiss(("focus", c))

    def action_refresh_chain(self) -> None:
        self.refresh_chain()

    @on(DataTable.RowSelected, "#chain-table")
    def _row_selected(self, e: DataTable.RowSelected) -> None:
        self.action_select_contract()

    @on(Button.Pressed, "#btn-buy-ce")
    def _buy_ce(self) -> None:
        self.action_quick_buy()

    @on(Button.Pressed, "#btn-buy-pe")
    def _buy_pe(self) -> None:
        self.action_quick_sell()

    @on(Button.Pressed, "#btn-focus-contract")
    def _focus_btn(self) -> None:
        self.action_select_contract()

    @on(Button.Pressed, "#btn-close-chain")
    def _close_btn(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  QuantAnalysisModal — Institutional Quantitative Risk & Technical Analysis
# ══════════════════════════════════════════════════════════════════════════════

class QuantAnalysisModal(ModalScreen):
    """Institutional Quantitative Risk & Technical Analysis modal screen."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
        Binding("c",      "open_chart",    "Chart"),
        Binding("b",      "buy",           "Buy"),
        Binding("s",      "sell",          "Sell"),
        Binding("r",      "refresh_data",  "Refresh"),
    ]

    def __init__(self, item: dict | None = None, symbol: str | None = None) -> None:
        super().__init__()
        self.item = item if isinstance(item, dict) else {}
        target_sym = symbol or self.item.get("tradingSymbol") or "RELIANCE"
        self.symbol = str(target_sym).strip().upper()
        self.exchange = str(self.item.get("exchange") or "NC").upper()
        self.ohlcv: dict[str, list[float]] = {}
        self.analysis: Any = None
        self.metrics: Any = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label(f"📈  Quantitative & Stock Technical Analysis  —  {self.symbol}", classes="title")
            yield Static(id="quant-header")
            yield Rule()
            yield Static(id="quant-indicators")
            yield Rule()
            yield Label("  Quantitative Risk & Regression Analytics", classes="field-group-label")
            yield DataTable(id="t-quant-metrics", cursor_type="row")
            yield Static("  Esc / q = close  ·  c = full chart  ·  b = buy  ·  s = sell  ·  r = refresh", classes="hint")
            with Horizontal(classes="row buttons"):
                yield Button("Buy (b)", id="btn-buy", variant="success")
                yield Button("Sell (s)", id="btn-sell", variant="error")
                yield Button("Chart (c)", id="btn-chart", variant="primary")
                yield Button("↻ Refresh (r)", id="btn-refresh")
                yield Button("✗ Close (Esc)", id="btn-close")

    def on_mount(self) -> None:
        t = self.query_one("#t-quant-metrics", DataTable)
        t.add_column("Metric", key="metric")
        t.add_column("Value", key="value")
        t.add_column("Benchmark / Horizon", key="bench")
        t.add_column("Assessment", key="assessment")
        self.load_analysis()

    def load_analysis(self) -> None:
        """Compute technical indicators and quant risk metrics."""
        from sktui.api.paper_trading import generate_paper_history
        from sktui.services.quant_analyst import compute_metrics
        from sktui.services.stock_analyzer import StockAnalyzer

        rows = generate_paper_history(self.exchange, self.symbol, interval="1d", bars_count=120)
        if not rows:
            return

        ohlcv = {
            "open": [float(r.get("open") or 0.0) for r in rows],
            "high": [float(r.get("high") or 0.0) for r in rows],
            "low": [float(r.get("low") or 0.0) for r in rows],
            "close": [float(r.get("close") or 0.0) for r in rows],
            "volume": [float(r.get("volume") or 0.0) for r in rows],
        }

        nifty_rows = generate_paper_history("NC", 21808, interval="1d", bars_count=len(rows), base_price=25000.0)
        bench_prices = [float(r.get("close") or 25000.0) for r in nifty_rows]

        analyzer = StockAnalyzer()
        analysis = analyzer.analyze_stock(self.symbol, ohlcv)
        metrics = compute_metrics(ohlcv["close"], benchmark_prices=bench_prices, risk_free_rate=0.05)

        self.ohlcv = ohlcv
        self.analysis = analysis
        self.metrics = metrics
        self._update_ui()

    def _update_ui(self) -> None:
        if not self.analysis or not self.metrics:
            return
        p = current_palette()

        # 1. Update Header Strip with Signal Badge & Sparkline
        closes = self.ohlcv.get("close", [])
        ltp = closes[-1] if closes else 0.0
        prev_c = closes[-2] if len(closes) > 1 else ltp
        chg = ltp - prev_c
        pct = (chg / prev_c * 100.0) if prev_c > 0 else 0.0
        c_col = p.bull if chg >= 0 else p.bear

        sig = self.analysis.signal.action.upper()
        sig_col = p.bull if "BUY" in sig else (p.bear if "SELL" in sig else p.warn)

        spk = sparkline(closes, width=48)
        hi, lo = (max(closes), min(closes)) if closes else (0.0, 0.0)

        hdr_text = Text()
        hdr_text.append(f"\n  {self.symbol}  ({self.exchange})    ", style=f"bold {p.primary}")
        hdr_text.append(f"₹{ltp:,.2f}  ", style=f"bold {p.fg}")
        hdr_text.append(f"{chg:+.2f} ({pct:+.2f}%)    ", style=f"bold {c_col}")
        hdr_text.append(f"  [{sig}]  ", style=f"bold black on {sig_col}")
        hdr_text.append(f"  Confidence: {self.analysis.signal.confidence_pct:.1f}%\n", style=f"bold {p.warn}")
        hdr_text.append(f"  Range: ₹{lo:,.2f} – ₹{hi:,.2f}    ", style=p.muted)
        hdr_text.append(f"Price Trend: {spk}\n", style=f"bold {p.teal}")
        hdr_text.append(f"  Signal Reasoning: {', '.join(self.analysis.signal.reasoning) or 'Balanced equilibrium'}\n", style=p.subtle)
        try:
            self.query_one("#quant-header", Static).update(hdr_text)
        except Exception:
            pass

        # 2. Update Indicator Gauges Text
        ind_text = Text()
        ind_text.append("  ── Technical Indicator Gauges ──────────────────────────────────────────\n\n", style=p.subtle)
        ind_text.append("  RSI (14):               ", style=p.muted)
        ind_text.append(f"{self.analysis.rsi:.1f}  [{self.analysis.rsi_condition}]\n", style=f"bold {p.fg}")

        ind_text.append("  MACD (12, 26, 9):       ", style=p.muted)
        ind_text.append(f"Line: {self.analysis.macd_line:+.2f}  Signal: {self.analysis.macd_signal:+.2f}  [{self.analysis.macd_condition}]\n", style=f"bold {p.fg}")

        stoch_k_val = f"{self.analysis.stoch_k:.1f}" if self.analysis.stoch_k is not None else "N/A"
        stoch_d_val = f"{self.analysis.stoch_d:.1f}" if self.analysis.stoch_d is not None else "N/A"
        ind_text.append("  Stochastic (%K, %D):    ", style=p.muted)
        ind_text.append(f"%K: {stoch_k_val}  %D: {stoch_d_val}  [{self.analysis.stoch_condition}]\n", style=f"bold {p.fg}")

        adx_val = f"{self.analysis.adx:.1f}" if self.analysis.adx is not None else "N/A"
        pdi_val = f"{self.analysis.plus_di:.1f}" if self.analysis.plus_di is not None else "N/A"
        mdi_val = f"{self.analysis.minus_di:.1f}" if self.analysis.minus_di is not None else "N/A"
        ind_text.append("  ADX (14) & DMI:         ", style=p.muted)
        ind_text.append(f"ADX: {adx_val}  (+DI: {pdi_val}, -DI: {mdi_val})  [{self.analysis.adx_condition}]\n", style=f"bold {p.fg}")

        bb_mid_val = f"₹{self.analysis.bb_mid:,.1f}" if self.analysis.bb_mid is not None else "N/A"
        ind_text.append("  Bollinger Bands (20, 2): ", style=p.muted)
        ind_text.append(f"Mid: {bb_mid_val}  Bandwidth: {self.analysis.bb_bandwidth:.2f}  [{self.analysis.bb_condition}]\n", style=f"bold {p.fg}")
        try:
            self.query_one("#quant-indicators", Static).update(ind_text)
        except Exception:
            pass

        # 3. Update Quant Metrics Table
        try:
            t = self.query_one("#t-quant-metrics", DataTable)
            t.clear()
            m = self.metrics
            t.add_row("Annualized Return", f"{m.mean_return * 100.0:+.2f}%", "Annual (252 bars)", "Profitable" if m.mean_return > 0 else "Negative")
            t.add_row("Annualized Volatility", f"{m.annual_volatility * 100.0:.2f}%", "Annual (252 bars)", "Moderate" if m.annual_volatility < 0.30 else "Elevated")
            t.add_row("Sharpe Ratio", f"{m.sharpe_ratio:.2f}", "Rf = 5.0%", "Institutional Quality" if m.sharpe_ratio >= 1.0 else "Sub-optimal")
            t.add_row("Sortino Ratio", f"{m.sortino_ratio:.2f}", "Downside Deviation", "Strong" if m.sortino_ratio >= 1.5 else "Moderate")
            t.add_row("Maximum Drawdown", f"{m.max_drawdown * 100.0:.2f}%", f"{m.drawdown_duration} bars underwater", "Controlled" if abs(m.max_drawdown) < 0.20 else "High Risk")
            t.add_row("Value-at-Risk (95% 1-day)", f"{m.var_95 * 100.0:.2f}%", "Historical Percentile", "Normal 95% Cutoff")
            t.add_row("Value-at-Risk (99% 1-day)", f"{m.var_99 * 100.0:.2f}%", "Historical Percentile", "Tail Risk 99%")
            t.add_row("Conditional VaR (CVaR 95%)", f"{m.cvar_95 * 100.0:.2f}%", "Expected Shortfall", "Tail Average Loss")
            t.add_row("Beta (vs Nifty 50)", f"{m.beta:.2f}", "Benchmark NIFTY50", "Aggressive" if m.beta > 1.0 else "Defensive")
            t.add_row("Alpha (Jensen's)", f"{m.alpha * 100.0:+.2f}%", "Annual Excess", "Outperforming" if m.alpha > 0 else "Underperforming")
            t.add_row("R-Squared (R²)", f"{m.r_squared:.2f}", "Benchmark Correlation", "High Fit" if m.r_squared > 0.60 else "Idiosyncratic")
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        self._update_ui()

    @on(Button.Pressed, "#btn-close")
    def action_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#btn-refresh")
    def action_refresh_data(self) -> None:
        self.load_analysis()

    @on(Button.Pressed, "#btn-chart")
    def action_open_chart(self) -> None:
        self.dismiss(None)
        ws = _workspace_screen(self.app)
        if ws and hasattr(ws, "action_chart"):
            ws.action_chart(self.item)

    @on(Button.Pressed, "#btn-buy")
    def action_buy(self) -> None:
        self.dismiss(None)
        ws = _workspace_screen(self.app)
        if ws and hasattr(ws, "action_trade"):
            ws.action_trade("B", override_item=self.item)

    @on(Button.Pressed, "#btn-sell")
    def action_sell(self) -> None:
        self.dismiss(None)
        ws = _workspace_screen(self.app)
        if ws and hasattr(ws, "action_trade"):
            ws.action_trade("S", override_item=self.item)


# Alias for backward and forward compatibility
StockAnalysisModal = QuantAnalysisModal


class PairScreenerModal(ModalScreen):
    """Statistical Arbitrage & Cointegration Pair Screener workstation modal."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
        Binding("enter",  "inspect_spread", "Inspect Spread"),
        Binding("s",      "inspect_spread", "Spread", show=False),
        Binding("r",      "refresh_data",  "Refresh"),
    ]

    def __init__(self, sector: str | None = None, min_corr: float = 0.70, symbol: str | None = None) -> None:
        super().__init__()
        self.sector = (sector or "ALL").strip().upper()
        self.min_corr = min_corr
        self.target_symbol = symbol.strip().upper() if symbol else None
        self.results: list[Any] = []

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label(f"⚖  Statistical Arbitrage & Cointegration Screener — Sector: {self.sector}", classes="title")
            yield Static(id="pair-screener-summary")
            yield Rule()
            yield DataTable(id="t-pair-screener", cursor_type="row")
            yield Static("  Esc / q = close  ·  Enter / s = inspect spread in detail  ·  r = refresh", classes="hint")
            with Horizontal(classes="row buttons"):
                yield Button("🔍 Inspect Spread (Enter)", id="btn-inspect-spread", variant="primary")
                yield Button("↻ Refresh (r)", id="btn-refresh")
                yield Button("✗ Close (Esc)", id="btn-close")

    def on_mount(self) -> None:
        t = self.query_one("#t-pair-screener", DataTable)
        t.add_column("Pair", key="pair")
        t.add_column("Sector", key="sector")
        t.add_column("Correlation (ρ)", key="corr")
        t.add_column("Stability (Δρ)", key="stab")
        t.add_column("Hedge Ratio (β)", key="beta")
        t.add_column("ADF Stat", key="adf")
        t.add_column("p-value", key="pval")
        t.add_column("Cointegrated", key="coint")
        t.add_column("Half-Life", key="halflife")
        t.add_column("Z-Score", key="zscore")
        t.add_column("Signal", key="signal")
        self.load_screener()

    def load_screener(self) -> None:
        from sktui.config import SECTOR_MAP
        from sktui.services.pair_screener import screen_pairs
        from sktui.services.stock_analyzer import StockAnalyzer

        syms: list[str] = []
        if self.target_symbol:
            # Include target symbol with intra-sector peers
            target_sec = SECTOR_MAP.get(self.target_symbol, "")
            syms = [self.target_symbol] + [s for s, sec in SECTOR_MAP.items() if sec == target_sec and s != self.target_symbol][:5]
        elif self.sector and self.sector != "ALL":
            syms = [s for s, sec in SECTOR_MAP.items() if sec.upper() == self.sector]
        if not syms:
            syms = list(SECTOR_MAP.keys())[:15]

        analyzer = StockAnalyzer()
        univ: dict[str, list[float]] = {}
        for s in syms:
            bars = analyzer._fetch_bars(s, period="1y")
            if bars and "close" in bars and len(bars["close"]) >= 30:
                univ[s] = bars["close"]

        self.results = screen_pairs(univ, min_correlation=self.min_corr)
        self._update_ui()

    def _update_ui(self) -> None:
        p = current_palette()
        t = self.query_one("#t-pair-screener", DataTable)
        t.clear()

        coint_count = sum(1 for r in self.results if r.is_cointegrated)
        active_sigs = sum(1 for r in self.results if r.signal in ("LONG_PAIR", "SHORT_PAIR"))

        summary = Text()
        summary.append(f"  Screened: {len(self.results)} Pairs   ", style=p.fg)
        summary.append(f"Cointegrated: {coint_count}   ", style=f"bold {p.bull}")
        summary.append(f"Active Signals: {active_sigs}   ", style=f"bold {p.warn}")
        summary.append(f"Min Correlation: {self.min_corr:.2f}", style=p.muted)
        self.query_one("#pair-screener-summary", Static).update(summary)

        for r in self.results:
            coint_style = f"bold {p.bull}" if r.is_cointegrated else p.muted
            coint_str = "✓ YES" if r.is_cointegrated else "✗ NO"
            sig_style = (
                f"bold {p.bull}" if "LONG" in r.signal
                else (f"bold {p.bear}" if "SHORT" in r.signal
                else (f"bold {p.warn}" if "EXIT" in r.signal else p.muted))
            )
            t.add_row(
                f"{r.stock_a} / {r.stock_b}",
                r.sector or "Equities",
                f"{r.correlation:.3f}",
                f"{r.correlation_stability:.3f}",
                f"{r.beta:.3f}",
                f"{r.adf_statistic:.2f}",
                f"{r.p_value:.4f}",
                Text(coint_str, style=coint_style),
                f"{r.half_life_days:.1f}d",
                f"{r.current_zscore:+.2f}",
                Text(r.signal, style=sig_style),
                key=f"{r.stock_a},{r.stock_b}",
            )

    @on(DataTable.RowSelected, "#t-pair-screener")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_inspect_spread()

    @on(Button.Pressed, "#btn-inspect-spread")
    def action_inspect_spread(self) -> None:
        t = self.query_one("#t-pair-screener", DataTable)
        if t.cursor_row is not None and t.row_count > 0:
            try:
                row_key = t.coordinate_to_cell_key((t.cursor_row, 0)).row_key.value
            except Exception:
                row_key = None
            if row_key:
                self.dismiss(None)
                self.app.push_screen(SpreadAnalysisModal(pair=row_key))

    @on(Button.Pressed, "#btn-refresh")
    def action_refresh_data(self) -> None:
        self.load_screener()

    @on(Button.Pressed, "#btn-close")
    def action_close(self) -> None:
        self.dismiss(None)


class SpreadAnalysisModal(ModalScreen):
    """Detailed Pair Spread & Z-Score Analysis with Braille Canvas and 1-Key Execution."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
        Binding("e",      "execute_pair",  "Execute"),
        Binding("r",      "refresh_data",  "Refresh"),
        Binding("c",      "open_chart_a",  "Chart"),
    ]

    def __init__(self, pair: str | None = None, stock_a: str | None = None, stock_b: str | None = None) -> None:
        super().__init__()
        if pair and "," in pair:
            parts = pair.split(",")
            self.stock_a = parts[0].strip().upper()
            self.stock_b = parts[1].strip().upper()
        elif pair and "/" in pair:
            parts = pair.split("/")
            self.stock_a = parts[0].strip().upper()
            self.stock_b = parts[1].strip().upper()
        else:
            self.stock_a = (stock_a or "TCS").strip().upper()
            self.stock_b = (stock_b or "INFY").strip().upper()
        self.pair_str = f"{self.stock_a} / {self.stock_b}"
        self.payload: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label(f"📊  Pair Spread & Z-Score Analysis — {self.pair_str}", classes="title")
            yield Static(id="spread-header-strip")
            yield Rule()
            yield Label("  Rolling 90-Day Z-Score Braille Canvas (Equilibrium & Threshold Bands)", classes="field-group-label")
            yield Static(id="spread-braille-canvas")
            yield Rule()
            yield Label("  Statistical Arbitrage & Risk Metrics", classes="field-group-label")
            yield DataTable(id="t-spread-metrics", cursor_type="row")
            yield Rule()
            yield Static(id="spread-execution-strip")
            yield Static("  Esc / q = close  ·  e = execute pair trade  ·  r = refresh  ·  c = chart", classes="hint")
            with Horizontal(classes="row buttons"):
                yield Button("⚡ Execute Pair Trade (e)", id="btn-execute-pair", variant="success")
                yield Button(f"Chart {self.stock_a} (c)", id="btn-chart-a", variant="primary")
                yield Button(f"Chart {self.stock_b}", id="btn-chart-b")
                yield Button("↻ Refresh (r)", id="btn-refresh")
                yield Button("✗ Close (Esc)", id="btn-close")

    def on_mount(self) -> None:
        t = self.query_one("#t-spread-metrics", DataTable)
        t.add_column("Metric", key="metric")
        t.add_column("Value", key="value")
        t.add_column("Threshold / Horizon", key="thresh")
        t.add_column("Interpretation", key="interp")
        self.load_spread()

    def load_spread(self) -> None:
        import statistics
        from sktui.services.pair_screener import (
            adf_test,
            calculate_position_sizing,
            calculate_zscore_signal,
            compute_half_life,
            compute_ols_hedge_ratio,
        )
        from sktui.services.stock_analyzer import StockAnalyzer

        analyzer = StockAnalyzer()
        b_a = analyzer._fetch_bars(self.stock_a, period="1y")
        b_b = analyzer._fetch_bars(self.stock_b, period="1y")
        if not b_a or not b_b or len(b_a.get("close", [])) < 10 or len(b_b.get("close", [])) < 10:
            return

        p_a = b_a.get("close", [])[-90:]
        p_b = b_b.get("close", [])[-90:]
        min_l = min(len(p_a), len(p_b))
        p_a, p_b = p_a[-min_l:], p_b[-min_l:]

        beta, alpha = compute_ols_hedge_ratio(p_a, p_b)
        spread = [a - beta * b for a, b in zip(p_a, p_b)]
        adf_stat, p_val, is_coint = adf_test(spread)
        half_life = compute_half_life(spread)

        z_series: list[float] = []
        for i in range(len(spread)):
            window = spread[max(0, i - 29): i + 1]
            m_win = statistics.mean(window)
            s_win = statistics.stdev(window) if len(window) > 1 else 1.0
            z_series.append((spread[i] - m_win) / s_win if s_win > 1e-12 else 0.0)

        cur_z = z_series[-1] if z_series else 0.0
        signal = calculate_zscore_signal(cur_z)
        sizing = calculate_position_sizing(100000.0, p_a[-1], p_b[-1], beta)

        self.payload = {
            "price_a": p_a[-1],
            "price_b": p_b[-1],
            "beta": beta,
            "alpha": alpha,
            "adf_stat": adf_stat,
            "p_val": p_val,
            "is_coint": is_coint,
            "half_life": half_life,
            "cur_spread": spread[-1],
            "cur_z": cur_z,
            "z_series": z_series,
            "signal": signal,
            "sizing": sizing,
        }
        self._update_ui()

    def _update_ui(self) -> None:
        if not self.payload:
            return
        p = current_palette()
        from sktui.chart import render_chart

        # 1. Header Strip
        hdr = Text()
        hdr.append(f"\n  {self.pair_str}    ", style=f"bold {p.primary}")
        hdr.append(f"{self.stock_a}: ₹{self.payload['price_a']:,.2f}   ", style=f"bold {p.fg}")
        hdr.append(f"{self.stock_b}: ₹{self.payload['price_b']:,.2f}    ", style=f"bold {p.fg}")
        sig = self.payload["signal"]
        sig_col = p.bull if "LONG" in sig else (p.bear if "SHORT" in sig else p.warn)
        hdr.append(f" [{sig}] ", style=f"bold black on {sig_col}")
        hdr.append(f"   Z-Score: {self.payload['cur_z']:+.2f}\n", style=f"bold {sig_col}")
        self.query_one("#spread-header-strip", Static).update(hdr)

        # 2. Braille Canvas for Z-Scores
        z_chart = render_chart(
            self.payload.get("z_series", [0.0, 0.0]),
            width=100,
            height=8,
            label="Z-Score Reversion Track",
            show_vol_strip=False,
            show_stats=True,
        )
        self.query_one("#spread-braille-canvas", Static).update(z_chart)

        # 3. Metrics Table
        t = self.query_one("#t-spread-metrics", DataTable)
        t.clear()
        t.add_row("Hedge Ratio (β)", f"{self.payload['beta']:.4f}", "OLS Slope", "Shares B per Share A")
        t.add_row("Intercept (α)", f"{self.payload['alpha']:.2f}", "OLS Constant", "Spread Level Base")
        t.add_row("ADF Test Statistic", f"{self.payload['adf_stat']:.2f}", "Crit 5% = -2.86", "Cointegrated" if self.payload['is_coint'] else "Unit Root")
        t.add_row("MacKinnon p-value", f"{self.payload['p_val']:.4f}", "p < 0.05", "Valid Mean Reversion" if self.payload['is_coint'] else "Spurious")
        t.add_row("Mean-Reversion Half-Life", f"{self.payload['half_life']:.1f} days", "1 – 60 days optimal", "Fast" if self.payload['half_life'] < 20 else "Moderate")
        t.add_row("Current Spread Value", f"{self.payload['cur_spread']:.2f}", "S = A - β*B", "Spread Deviation")
        t.add_row("Current Z-Score", f"{self.payload['cur_z']:+.2f}", "±2.0 Entry, 0.0 Exit", sig)

        # 4. Sizing Execution Strip
        sz = self.payload["sizing"]
        act_a = "BUY" if "LONG" in sig else ("SELL" if "SHORT" in sig else "FLAT")
        act_b = "SELL" if "LONG" in sig else ("BUY" if "SHORT" in sig else "FLAT")
        dollar_a = sz.get("dollar_a", sz.get("capital_a", 0.0))
        dollar_b = sz.get("dollar_b", sz.get("capital_b", 0.0))
        exe_text = Text()
        exe_text.append("  Market-Neutral Execution Plan (₹100,000 Portfolio Allocation):\n", style=f"bold {p.primary}")
        exe_text.append(f"  • Leg A ({self.stock_a}): {act_a} {sz.get('shares_a', 0)} shares (~₹{dollar_a:,.0f})\n", style=p.fg)
        exe_text.append(f"  • Leg B ({self.stock_b}): {act_b} {sz.get('shares_b', 0)} shares (~₹{dollar_b:,.0f})\n", style=p.fg)
        self.query_one("#spread-execution-strip", Static).update(exe_text)

    @on(Button.Pressed, "#btn-execute-pair")
    def action_execute_pair(self) -> None:
        """Execute market-neutral pair trade simultaneously."""
        ws = _workspace_screen(self.app)
        sig = self.payload.get("signal", "NONE")
        if sig not in ("LONG_PAIR", "SHORT_PAIR"):
            if hasattr(self.app, "notify"):
                self.app.notify("No active entry signal (Z-score within equilibrium band)", severity="warning")
            return

        side_a = "B" if sig == "LONG_PAIR" else "S"
        side_b = "S" if sig == "LONG_PAIR" else "B"

        if ws and hasattr(ws, "action_trade"):
            ws.action_trade(side_a, override_item={"tradingSymbol": self.stock_a, "exchange": "NC"})
            if hasattr(self.app, "notify"):
                self.app.notify(f"✓ Pair trade initialized: {side_a} {self.stock_a} / {side_b} {self.stock_b}")
            self.dismiss(None)

    @on(Button.Pressed, "#btn-chart-a")
    def action_open_chart_a(self) -> None:
        self.dismiss(None)
        ws = _workspace_screen(self.app)
        if ws and hasattr(ws, "action_chart"):
            ws.action_chart({"tradingSymbol": self.stock_a, "exchange": "NC"})

    @on(Button.Pressed, "#btn-chart-b")
    def action_open_chart_b(self) -> None:
        self.dismiss(None)
        ws = _workspace_screen(self.app)
        if ws and hasattr(ws, "action_chart"):
            ws.action_chart({"tradingSymbol": self.stock_b, "exchange": "NC"})

    @on(Button.Pressed, "#btn-refresh")
    def action_refresh_data(self) -> None:
        self.load_spread()

    @on(Button.Pressed, "#btn-close")
    def action_close(self) -> None:
        self.dismiss(None)


class SignalScannerModal(ModalScreen):
    """Multi-Symbol 7-Indicator Composite Signal Scanner with Dynamic ATR Risk."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
        Binding("b",      "buy_selected",  "Buy"),
        Binding("s",      "sell_selected", "Sell"),
        Binding("c",      "open_chart",    "Chart"),
        Binding("r",      "refresh_signals","Rescan"),
    ]

    def __init__(
        self,
        symbol: str | None = None,
        watchlist: str | None = None,
        filter_type: str = "ALL",
        min_confidence: float = 60.0,
    ) -> None:
        super().__init__()
        self.target_symbol = symbol.strip().upper() if symbol else None
        self.watchlist = watchlist
        self.filter_type = filter_type.strip().upper()
        self.min_confidence = min_confidence
        self.signals: list[Any] = []

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label("⚡  Multi-Indicator Composite Signal Scanner (7 Indicators + ATR Risk)", classes="title")
            yield Static(id="signal-scanner-header")
            yield Rule()
            yield DataTable(id="t-signal-scanner", cursor_type="row")
            yield Static("  Esc / q = close  ·  b = buy  ·  s = sell  ·  c = chart  ·  r = rescan", classes="hint")
            with Horizontal(classes="row buttons"):
                yield Button("Buy Selected (b)", id="btn-buy-sel", variant="success")
                yield Button("Sell Selected (s)", id="btn-sell-sel", variant="error")
                yield Button("Chart (c)", id="btn-chart-sel", variant="primary")
                yield Button("↻ Rescan (r)", id="btn-refresh")
                yield Button("✗ Close (Esc)", id="btn-close")

    def on_mount(self) -> None:
        t = self.query_one("#t-signal-scanner", DataTable)
        t.add_column("Symbol", key="symbol")
        t.add_column("LTP (₹)", key="ltp")
        t.add_column("Signal Tier", key="tier")
        t.add_column("Score", key="score")
        t.add_column("Confidence", key="conf")
        t.add_column("Votes (Bull/Bear/Neut)", key="votes")
        t.add_column("Stop Loss (SL)", key="sl")
        t.add_column("Take Profit (TP)", key="tp")
        t.add_column("R:R", key="rr")
        self.load_signals()

    def load_signals(self) -> None:
        from sktui.config import SECTOR_MAP
        from sktui.services.signal_engine import scan_watchlist
        from sktui.services.stock_analyzer import StockAnalyzer

        if self.target_symbol:
            syms = [self.target_symbol]
        elif self.watchlist:
            wl_clean = self.watchlist.strip().lower()
            syms = [s for s, sec in SECTOR_MAP.items() if sec.lower() == wl_clean]
            if not syms:
                syms = list(SECTOR_MAP.keys())[:8]
        else:
            syms = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "TATAMOTORS", "ITC"]

        analyzer = StockAnalyzer()
        ohlcv_map: dict[str, dict[str, list[float]]] = {}
        for s in syms:
            b = analyzer._fetch_bars(s, period="1y")
            if b and len(b.get("close", [])) >= 30:
                ohlcv_map[s] = b

        self.signals = scan_watchlist(syms, ohlcv_map, direction=self.filter_type, min_confidence=self.min_confidence)
        self._update_ui()

    def _update_ui(self) -> None:
        p = current_palette()
        t = self.query_one("#t-signal-scanner", DataTable)
        t.clear()

        hdr = Text()
        hdr.append(f"\n  Universe: {len(self.signals)} Scanned Instruments   ", style=f"bold {p.primary}")
        hdr.append(f"Filter: {self.filter_type}   ", style=p.fg)
        hdr.append(f"Min Confidence: {self.min_confidence:.1f}%\n", style=f"bold {p.warn}")
        self.query_one("#signal-scanner-header", Static).update(hdr)

        for s in self.signals:
            tier_col = (
                f"bold {p.bull}" if "BUY" in s.signal_type
                else (f"bold {p.bear}" if "SELL" in s.signal_type else f"bold {p.warn}")
            )
            v_dict = s.indicator_votes or {}
            bulls = sum(1 for v in v_dict.values() if v > 0)
            bears = sum(1 for v in v_dict.values() if v < 0)
            neuts = sum(1 for v in v_dict.values() if v == 0)

            t.add_row(
                s.symbol,
                f"₹{s.price:,.2f}",
                Text(s.signal_type, style=tier_col),
                f"{s.score:+.2f}",
                f"{s.confidence_pct:.1f}%",
                f"{bulls}▲ / {bears}▼ / {neuts}—",
                f"₹{s.stop_loss:,.2f}",
                f"₹{s.take_profit:,.2f}",
                f"{s.risk_reward_ratio:.1f}x",
                key=s.symbol,
            )

    @on(Button.Pressed, "#btn-buy-sel")
    def action_buy_selected(self) -> None:
        t = self.query_one("#t-signal-scanner", DataTable)
        if t.cursor_row is not None and t.row_count > 0:
            try:
                sym = t.coordinate_to_cell_key((t.cursor_row, 0)).row_key.value
            except Exception:
                sym = None
            if sym:
                self.dismiss(None)
                ws = _workspace_screen(self.app)
                if ws and hasattr(ws, "action_trade"):
                    ws.action_trade("B", override_item={"tradingSymbol": sym, "exchange": "NC"})

    @on(Button.Pressed, "#btn-sell-sel")
    def action_sell_selected(self) -> None:
        t = self.query_one("#t-signal-scanner", DataTable)
        if t.cursor_row is not None and t.row_count > 0:
            try:
                sym = t.coordinate_to_cell_key((t.cursor_row, 0)).row_key.value
            except Exception:
                sym = None
            if sym:
                self.dismiss(None)
                ws = _workspace_screen(self.app)
                if ws and hasattr(ws, "action_trade"):
                    ws.action_trade("S", override_item={"tradingSymbol": sym, "exchange": "NC"})

    @on(Button.Pressed, "#btn-chart-sel")
    def action_open_chart(self) -> None:
        t = self.query_one("#t-signal-scanner", DataTable)
        if t.cursor_row is not None and t.row_count > 0:
            try:
                sym = t.coordinate_to_cell_key((t.cursor_row, 0)).row_key.value
            except Exception:
                sym = None
            if sym:
                self.dismiss(None)
                ws = _workspace_screen(self.app)
                if ws and hasattr(ws, "action_chart"):
                    ws.action_chart({"tradingSymbol": sym, "exchange": "NC"})

    @on(Button.Pressed, "#btn-refresh")
    def action_refresh_signals(self) -> None:
        self.load_signals()

    @on(Button.Pressed, "#btn-close")
    def action_close(self) -> None:
        self.dismiss(None)


class BacktestModal(ModalScreen):
    """Interactive Strategy Backtesting, Parameter Optimization & Equity Curve Visualizer."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close", show=False),
        Binding("r",      "run_simulation", "Run"),
        Binding("o",      "optimize_grid",  "Optimize"),
        Binding("t",      "toggle_trades",  "Trades"),
    ]

    def __init__(
        self,
        item: dict | None = None,
        strategy: str | None = None,
        symbol: str | None = None,
        capital: float = 100000.0,
    ) -> None:
        super().__init__()
        self.item = item if isinstance(item, dict) else {}
        target_sym = symbol or self.item.get("tradingSymbol") or "RELIANCE"
        self.symbol = str(target_sym).strip().upper()
        self.strategy_name = (strategy or "sma").strip().lower()
        self.capital = float(capital)
        self.result: Any = None
        self.ohlcv: dict[str, list[float]] = {}
        self.show_trades = True

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label("📈  Algorithmic Strategy Backtesting & Simulation Engine", classes="title")
            yield Static(id="backtest-header-strip")
            yield Rule()
            with Horizontal(classes="row"):
                yield Label(" Strategy: ", classes="field-label")
                yield Select(
                    options=[
                        ("Dual SMA Crossover", "sma"),
                        ("Dual EMA Crossover", "ema"),
                        ("RSI Mean Reversion", "rsi"),
                        ("MACD Signal Line Cross", "macd"),
                        ("Bollinger Bands", "bollinger"),
                        ("Donchian Breakout", "breakout"),
                        ("Z-Score Mean Reversion", "mean_reversion"),
                        ("Momentum / ROC", "momentum"),
                    ],
                    value=self.strategy_name if self.strategy_name in [
                        "sma", "ema", "rsi", "macd", "bollinger", "breakout", "mean_reversion", "momentum"
                    ] else "sma",
                    id="select-backtest-strategy",
                )
                yield Label("  Symbol: ", classes="field-label")
                yield Input(value=self.symbol, id="input-backtest-symbol", placeholder="e.g. RELIANCE")
                yield Label("  Capital (₹): ", classes="field-label")
                yield Input(value=f"{int(self.capital)}", id="input-backtest-capital", placeholder="Initial Capital")
                yield Label("  Mode: ", classes="field-label")
                yield Select(
                    options=[("Vectorized", "vectorized"), ("Event-Driven", "event_driven")],
                    value="vectorized",
                    id="select-backtest-mode",
                )
            with Horizontal(classes="row buttons"):
                yield Button("▶ Run Simulation (r)", id="btn-run-sim", variant="success")
                yield Button("⚡ Optimize Grid (o)", id="btn-opt-grid", variant="primary")
                yield Button("📋 Toggle Trades (t)", id="btn-toggle-trades")
                yield Button("✗ Close (Esc)", id="btn-close")
            yield Rule()
            yield Label("  Portfolio Equity Curve (Braille Resolution)", classes="field-group-label")
            yield Static(id="backtest-equity-canvas")
            yield Rule()
            yield Label("  Performance & Risk Analytics", classes="field-group-label")
            yield DataTable(id="t-backtest-metrics", cursor_type="row")
            yield Label("  Executed Trades Audit Log", classes="field-group-label", id="label-trades-log")
            yield DataTable(id="t-backtest-trades", cursor_type="row")
            yield Static("  Esc / q = close  ·  r = run simulation  ·  o = optimize grid  ·  t = toggle trades", classes="hint")

    def on_mount(self) -> None:
        tm = self.query_one("#t-backtest-metrics", DataTable)
        tm.add_column("Metric", key="metric")
        tm.add_column("Strategy Value", key="value")
        tm.add_column("Benchmark / Target", key="bench")
        tm.add_column("Assessment", key="assessment")

        tt = self.query_one("#t-backtest-trades", DataTable)
        tt.add_column("#", key="idx")
        tt.add_column("Action", key="action")
        tt.add_column("Signal Bar", key="sig_bar")
        tt.add_column("Exec Bar", key="exec_bar")
        tt.add_column("Exec Price (₹)", key="price")
        tt.add_column("Shares", key="shares")
        tt.add_column("Cost (₹)", key="cost")
        tt.add_column("Realized P&L (₹)", key="pnl")
        tt.add_column("Cumulative Equity (₹)", key="equity")

        self.action_run_simulation()

    def action_run_simulation(self) -> None:
        """Run backtesting simulation and refresh UI widgets."""
        from sktui.api.paper_trading import generate_paper_history
        from sktui.chart import render_chart
        from sktui.services.backtesting import BacktestConfig, run_backtest

        try:
            sel_strat = self.query_one("#select-backtest-strategy", Select).value
            if sel_strat:
                self.strategy_name = str(sel_strat).lower()
        except Exception:
            pass

        try:
            inp_sym = self.query_one("#input-backtest-symbol", Input).value
            if inp_sym and inp_sym.strip():
                self.symbol = inp_sym.strip().upper()
        except Exception:
            pass

        try:
            inp_cap = self.query_one("#input-backtest-capital", Input).value
            if inp_cap:
                self.capital = max(1000.0, float(inp_cap))
        except Exception:
            self.capital = 100000.0

        try:
            sel_mode = self.query_one("#select-backtest-mode", Select).value
            mode = str(sel_mode) if sel_mode else "vectorized"
        except Exception:
            mode = "vectorized"

        rows = generate_paper_history("NC", self.symbol, interval="1d", bars_count=120)
        if not rows:
            return

        self.ohlcv = {
            "open": [float(r.get("open") or 0.0) for r in rows],
            "high": [float(r.get("high") or 0.0) for r in rows],
            "low": [float(r.get("low") or 0.0) for r in rows],
            "close": [float(r.get("close") or 0.0) for r in rows],
            "volume": [float(r.get("volume") or 1000.0) for r in rows],
        }

        cfg = BacktestConfig(
            initial_capital=self.capital,
            strategy_name=self.strategy_name,
            mode=mode,
        )
        self.result = run_backtest(self.ohlcv, self.strategy_name, cfg)

        # Update Header Strip
        ret_pct = self.result.total_return * 100.0
        pnl = self.result.final_equity - self.result.initial_capital
        hdr_style = "bold green" if ret_pct >= 0 else "bold red"
        hdr_str = (
            f" [bold white]{self.symbol}[/bold white]  ·  "
            f"Strategy: [bold cyan]{self.strategy_name.upper()}[/bold cyan]  ·  "
            f"Mode: {mode.upper()}  ·  "
            f"Initial: ₹{self.result.initial_capital:,.2f}  ·  "
            f"Final: ₹{self.result.final_equity:,.2f}  ·  "
            f"Return: [{hdr_style}]{ret_pct:+.2f}%[/{hdr_style}]  ·  "
            f"Sharpe: [bold yellow]{self.result.sharpe_ratio:.2f}[/bold yellow]  ·  "
            f"MaxDD: [bold red]{self.result.max_drawdown * 100.0:.2f}%[/bold red]"
        )
        try:
            self.query_one("#backtest-header-strip", Static).update(hdr_str)
        except Exception:
            pass

        # Render Braille Equity Chart
        if self.result.equity_curve:
            try:
                chart_render = render_chart(
                    self.result.equity_curve,
                    width=90,
                    height=8,
                    label=f"{self.symbol} Equity Curve ({self.strategy_name.upper()})",
                    show_vol_strip=False,
                    show_stats=True,
                )
                self.query_one("#backtest-equity-canvas", Static).update(chart_render)
            except Exception:
                try:
                    self.query_one("#backtest-equity-canvas", Static).update("Equity curve render unavailable.")
                except Exception:
                    pass

        # Populate Metrics DataTable
        try:
            tm = self.query_one("#t-backtest-metrics", DataTable)
            tm.clear()
            tm.add_row("Initial Capital", f"₹{self.result.initial_capital:,.2f}", "₹100,000.00", "Base Allocation")
            tm.add_row("Final Equity", f"₹{self.result.final_equity:,.2f}", f"Net P&L: ₹{pnl:+,.2f}", "Growth" if pnl >= 0 else "Decline")
            tm.add_row("Total Return", f"{ret_pct:+.2f}%", "Benchmark Horizon", "Positive Alpha" if ret_pct > 0 else "Negative Alpha")
            tm.add_row("CAGR (Annualized)", f"{self.result.cagr * 100.0:+.2f}%", ">= 12.0%", "Outperforming" if self.result.cagr >= 0.12 else "Underperforming")
            tm.add_row("Annualized Volatility", f"{self.result.annualized_volatility * 100.0:.2f}%", "< 25.0%", "Acceptable" if self.result.annualized_volatility < 0.25 else "High Volatility")
            sharpe_eval = "Institutional Grade" if self.result.sharpe_ratio >= 1.5 else ("Acceptable" if self.result.sharpe_ratio >= 1.0 else "Sub-optimal")
            tm.add_row("Sharpe Ratio (Rf=5%)", f"{self.result.sharpe_ratio:.2f}", "> 1.00", sharpe_eval)
            tm.add_row("Sortino Ratio", f"{self.result.sortino_ratio:.2f}", "> 1.50", "High Downside Protection" if self.result.sortino_ratio >= 1.5 else "Standard")
            tm.add_row("Calmar Ratio", f"{self.result.calmar_ratio:.2f}", "> 1.00", "Favorable" if self.result.calmar_ratio >= 1.0 else "Weak")
            tm.add_row("Maximum Drawdown", f"{self.result.max_drawdown * 100.0:.2f}%", "< 15.0%", "Controlled" if self.result.max_drawdown <= 0.15 else "Elevated Risk")
            tm.add_row("Win Rate", f"{self.result.win_rate * 100.0:.1f}%", "> 50.0%", "Edge Confirmed" if self.result.win_rate >= 0.5 else "Low Win Rate")
            pf_disp = f"{self.result.profit_factor:.2f}" if self.result.profit_factor < 900.0 else "Inf"
            tm.add_row("Profit Factor", pf_disp, "> 1.50", "Profitable" if self.result.profit_factor >= 1.5 else "Unprofitable")
            tm.add_row("Total Trades", str(self.result.total_trades), ">= 5", "Statistically Valid" if self.result.total_trades >= 5 else "Low Sample Size")
        except Exception:
            pass

        # Populate Trades DataTable
        try:
            tt = self.query_one("#t-backtest-trades", DataTable)
            tt.clear()
            for tr in self.result.trades_log:
                act = tr.get("action", "BUY")
                act_col = "green" if act in ("BUY", "COVER") else "red"
                pnl_v = tr.get("realized_pnl", 0.0)
                pnl_s = f"₹{pnl_v:+,.2f}" if act in ("SELL", "COVER") else "―"
                tt.add_row(
                    str(tr.get("trade_id", 1)),
                    f"[{act_col}]{act}[/{act_col}]",
                    str(tr.get("signal_bar", 0)),
                    str(tr.get("exec_bar", 1)),
                    f"₹{tr.get('exec_price', 0.0):,.2f}",
                    str(tr.get("qty", 0)),
                    f"₹{tr.get('commission', 0.0):,.2f}",
                    pnl_s,
                    f"₹{tr.get('equity', self.capital):,.2f}",
                )
        except Exception:
            pass

    def action_optimize_grid(self) -> None:
        """Execute parameter grid search optimization on current series."""
        from sktui.services.backtesting import DEFAULT_PARAM_GRIDS, BacktestConfig, optimize_grid

        if not self.ohlcv:
            self.action_run_simulation()

        grid = DEFAULT_PARAM_GRIDS.get(self.strategy_name, {"fast_period": [5, 10, 15], "slow_period": [20, 30, 50]})
        cfg = BacktestConfig(initial_capital=self.capital, strategy_name=self.strategy_name)
        opt_results = optimize_grid(self.ohlcv, self.strategy_name, grid, metric="sharpe_ratio", base_config=cfg)

        if opt_results:
            best_p, best_r = opt_results[0]
            param_str = ", ".join(f"{k}={v}" for k, v in best_p.items())
            if hasattr(self.app, "notify"):
                self.app.notify(
                    f"Best {self.strategy_name.upper()} Params: {param_str} (Sharpe: {best_r.sharpe_ratio:.2f}, Return: {best_r.total_return * 100.0:+.1f}%)",
                    title="Grid Optimizer",
                )
            # Apply best params and re-run
            self.action_run_simulation()

    def action_toggle_trades(self) -> None:
        """Toggle display of executed trades audit log table."""
        self.show_trades = not self.show_trades
        try:
            self.query_one("#t-backtest-trades", DataTable).display = self.show_trades
            self.query_one("#label-trades-log", Label).display = self.show_trades
        except Exception:
            pass

    @on(Button.Pressed, "#btn-run-sim")
    def on_run_pressed(self) -> None:
        self.action_run_simulation()

    @on(Button.Pressed, "#btn-opt-grid")
    def on_opt_pressed(self) -> None:
        self.action_optimize_grid()

    @on(Button.Pressed, "#btn-toggle-trades")
    def on_toggle_pressed(self) -> None:
        self.action_toggle_trades()

    @on(Button.Pressed, "#btn-close")
    def on_close_pressed(self) -> None:
        self.dismiss(None)


class BotManagerModal(ModalScreen):
    """Interactive Automated Trading Bot Manager & Fleet Orchestration Modal."""

    BINDINGS = [
        Binding("escape", "dismiss(None)",        "Close"),
        Binding("q",      "dismiss(None)",        "Close", show=False),
        Binding("s",      "toggle_bot_start",     "Start Bot"),
        Binding("p",      "toggle_bot_pause",     "Pause/Resume"),
        Binding("x",      "bot_stop",             "Stop Bot"),
        Binding("k",      "panic_cancel_all",     "Cancel All"),
        Binding("f",      "panic_flatten_all",    "Flatten All"),
        Binding("r",      "refresh_data",         "Refresh"),
    ]

    def __init__(
        self,
        bot_id: str | None = None,
        strategy: str | None = None,
        symbol: str | None = None,
        paper: bool = True,
        capital: float = 100_000.0,
    ) -> None:
        super().__init__()
        self.selected_bot_id = bot_id
        self.initial_strategy = (strategy or "pmm").strip().lower()
        self.initial_symbol = (symbol or "RELIANCE").strip().upper()
        self.is_paper = paper
        self.capital = float(capital)

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label("🤖  Automated Trading Bot Fleet Manager & Orchestration Engine", classes="title")
            yield Static(id="bot-status-strip")
            yield Rule()

            # Control Row: Strategy, Symbol, Capital, Execution Mode
            with Horizontal(classes="row"):
                yield Label(" Strategy: ", classes="field-label")
                yield Select(
                    options=[
                        ("Pure Market Making (PMM)", "pmm"),
                        ("Pair Statistical Arbitrage", "arbitrage"),
                        ("Trend Momentum", "momentum"),
                        ("AI Signal Predictor", "predictor"),
                    ],
                    value=self.initial_strategy if self.initial_strategy in ["pmm", "arbitrage", "momentum", "predictor"] else "pmm",
                    id="select-bot-strategy",
                )
                yield Label("  Symbol: ", classes="field-label")
                yield Input(value=self.initial_symbol, id="input-bot-symbol", placeholder="e.g. RELIANCE, TATAMOTORS, HDFCBANK/ICICIBANK")
                yield Label("  Capital (₹): ", classes="field-label")
                yield Input(value=f"{int(self.capital)}", id="input-bot-capital", placeholder="Initial Capital")
                yield Label("  Mode: ", classes="field-label")
                yield Select(
                    options=[("Paper (Sandbox)", "paper"), ("Live Broker", "live")],
                    value="paper" if self.is_paper else "live",
                    id="select-bot-mode",
                )

            # Button Controls Row
            with Horizontal(classes="row buttons"):
                yield Button("▶ Deploy & Start (s)", id="btn-bot-deploy-start", variant="success")
                yield Button("⏸ Pause/Resume (p)", id="btn-bot-pause-resume", variant="primary")
                yield Button("⏹ Stop Bot (x)", id="btn-bot-stop", variant="default")
                yield Button("⚠️ CANCEL ALL (k)", id="btn-bot-panic-cancel", variant="warning")
                yield Button("🚨 FLATTEN ALL (f)", id="btn-bot-panic-flatten", variant="error")
                yield Button("🔄 Refresh (r)", id="btn-bot-refresh")
                yield Button("✗ Close (Esc)", id="btn-bot-close")

            yield Rule()

            # Fleet KPI Telemetry Gauges Strip
            yield Label("  Fleet KPIs & Risk Exposure Summary", classes="field-group-label")
            yield Static(id="bot-telemetry-gauges")
            yield Rule()

            # Active Bot Fleet Registry Table
            yield Label("  Managed Bot Fleet Registry", classes="field-group-label")
            yield DataTable(id="t-bots-registry", cursor_type="row")
            yield Rule()

            # Active Order Queue Table
            yield Label("  Live Order Execution Queue", classes="field-group-label")
            yield DataTable(id="t-bot-orders", cursor_type="row")

            yield Static("  Esc/q = Close · s = Start · p = Pause/Resume · x = Stop · k = Cancel All · f = Flatten All · r = Refresh", classes="hint")

    def on_mount(self) -> None:
        from sktui.services.bot_engine import BotInstance, BotManager

        tb = self.query_one("#t-bots-registry", DataTable)
        tb.add_column("Bot ID", key="bot_id")
        tb.add_column("Strategy", key="strategy")
        tb.add_column("Symbol", key="symbol")
        tb.add_column("State", key="state")
        tb.add_column("Mode", key="mode")
        tb.add_column("Uptime", key="uptime")
        tb.add_column("Orders", key="orders")
        tb.add_column("Filled", key="filled")
        tb.add_column("PnL (₹)", key="pnl")
        tb.add_column("Loss Limit (₹)", key="loss_limit")

        to = self.query_one("#t-bot-orders", DataTable)
        to.add_column("Order ID", key="order_id")
        to.add_column("Bot ID", key="bot_id")
        to.add_column("Symbol", key="symbol")
        to.add_column("Side", key="side")
        to.add_column("Qty", key="qty")
        to.add_column("Price (₹)", key="price")
        to.add_column("Status", key="status")
        to.add_column("Time", key="time")

        mgr = BotManager.get_instance()
        if not mgr.list_bots():
            # Seed initial configured bot so registry has default instance
            mgr.create_bot(
                strategy=self.initial_strategy,
                symbol=self.initial_symbol,
                paper=self.is_paper,
                capital=self.capital,
                parameters={"spread_bps": 20.0, "daily_loss_limit": 5000.0, "max_order_val": 50000.0},
            )

        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh bot registry table, active orders table, and telemetry gauges."""
        from sktui.services.bot_engine import BotManager

        mgr = BotManager.get_instance()
        bots = mgr.list_bots()
        aggr = mgr.get_aggregated_telemetry()

        pnl = aggr.get("total_pnl", 0.0)
        pnl_style = "bold green" if pnl >= 0 else "bold red"
        status_text = (
            f"  Fleet Status: {aggr['total_bots']} Bots  ·  "
            f"Running: [bold green]{aggr['running_bots']}[/bold green]  ·  "
            f"Paused: [bold yellow]{aggr['paused_bots']}[/bold yellow]  ·  "
            f"Stopped: [bold red]{aggr['stopped_bots']}[/bold red]  ·  "
            f"Fleet PnL: [{pnl_style}]₹{pnl:+,.2f}[/{pnl_style}]  ·  "
            f"Mode: {'PAPER' if self.is_paper else 'LIVE'}"
        )
        try:
            self.query_one("#bot-status-strip", Static).update(status_text)
        except Exception:
            pass

        total_ord = aggr.get("total_orders", 0)
        filled_ord = aggr.get("filled_orders", 0)
        fill_pct = (filled_ord / total_ord * 100.0) if total_ord > 0 else 100.0
        gauges_text = (
            f"  Active Bots: {aggr['running_bots']}/{aggr['total_bots']}  ·  "
            f"Total Orders: {total_ord}  ·  "
            f"Filled: {filled_ord} ({fill_pct:.1f}%)  ·  "
            f"Total PnL: [{pnl_style}]₹{pnl:+,.2f}[/{pnl_style}]  ·  "
            f"Killswitch: [bold green]ARMED[/bold green]"
        )
        try:
            self.query_one("#bot-telemetry-gauges", Static).update(gauges_text)
        except Exception:
            pass

        # Populate Bot Registry DataTable
        try:
            tb = self.query_one("#t-bots-registry", DataTable)
            tb.clear()
            for b in bots:
                telem = b.get_telemetry()
                st = telem.get("state", "INIT")
                st_style = "bold green" if st == "RUNNING" else ("bold yellow" if st == "PAUSED" else "bold red")
                bot_pnl = float(telem.get("pnl", 0.0))
                bp_style = "bold green" if bot_pnl >= 0 else "bold red"
                tb.add_row(
                    b.bot_id,
                    b.strategy.upper(),
                    b.symbol,
                    Text(st, style=st_style),
                    "PAPER" if b.paper else "LIVE",
                    f"{telem.get('uptime_seconds', 0.0):.1f}s",
                    str(telem.get("total_orders", 0)),
                    str(telem.get("filled_orders", 0)),
                    Text(f"₹{bot_pnl:+,.2f}", style=bp_style),
                    f"₹{telem.get('daily_loss_limit', 5000.0):,.2f}",
                    key=b.bot_id,
                )
        except Exception:
            pass

        # Populate Active Orders DataTable
        try:
            to = self.query_one("#t-bot-orders", DataTable)
            to.clear()
            for b in bots:
                for ord_info in getattr(b, "active_orders", []):
                    side = str(ord_info.get("action") or ord_info.get("transactionType") or "B").upper()
                    side_style = "bold green" if side in ("B", "BUY") else "bold red"
                    ts = ord_info.get("timestamp", time.time())
                    time_str = time.strftime("%H:%M:%S", time.localtime(ts)) if isinstance(ts, (int, float)) else str(ts)
                    to.add_row(
                        str(ord_info.get("order_id", "-")),
                        b.bot_id,
                        str(ord_info.get("symbol", b.symbol)),
                        Text(side, style=side_style),
                        str(ord_info.get("qty") or ord_info.get("quantity") or 0),
                        f"₹{float(ord_info.get('price', 0.0)):,.2f}",
                        str(ord_info.get("status", "SUBMITTED")),
                        time_str,
                    )
        except Exception:
            pass

    def _notify(self, message: str, title: str | None = None, severity: str = "information") -> None:
        try:
            if hasattr(self, "app") and hasattr(self.app, "notify"):
                kwargs: dict[str, Any] = {}
                if title:
                    kwargs["title"] = title
                if severity != "information":
                    kwargs["severity"] = severity
                self.app.notify(message, **kwargs)
        except Exception:
            pass

    def action_toggle_bot_start(self) -> None:
        """Start or deploy current bot."""
        from sktui.services.bot_engine import BotManager

        mgr = BotManager.get_instance()
        try:
            strat = str(self.query_one("#select-bot-strategy", Select).value or self.initial_strategy).lower()
            sym = str(self.query_one("#input-bot-symbol", Input).value or self.initial_symbol).strip().upper()
            mode = str(self.query_one("#select-bot-mode", Select).value or "paper")
            is_paper = mode == "paper"
            cap = float(self.query_one("#input-bot-capital", Input).value or self.capital)
        except Exception:
            strat, sym, is_paper, cap = self.initial_strategy, self.initial_symbol, self.is_paper, self.capital

        bot_id = f"bot_{strat}_{sym.replace(',', '_').replace('/', '_')}"
        bot = mgr.get_bot(bot_id)
        if bot is None:
            bot = mgr.create_bot(
                strategy=strat,
                symbol=sym,
                paper=is_paper,
                capital=cap,
                bot_id=bot_id,
                parameters={"spread_bps": 20.0, "daily_loss_limit": 5000.0, "max_order_val": 50000.0},
            )
        bot.start()
        self._notify(f"Bot {bot.name} started successfully.", title="Bot Manager")
        self.refresh_data()

    def action_toggle_bot_pause(self) -> None:
        """Toggle pause/resume on selected or running bots."""
        from sktui.services.bot_engine import BotManager, BotState

        mgr = BotManager.get_instance()
        bots = mgr.list_bots()
        for b in bots:
            if b.state == BotState.RUNNING:
                b.pause()
            elif b.state == BotState.PAUSED:
                b.resume()
        self._notify("Toggled pause/resume on managed bots.", title="Bot Manager")
        self.refresh_data()

    def action_bot_stop(self) -> None:
        """Stop all running/paused bots."""
        from sktui.services.bot_engine import BotManager

        mgr = BotManager.get_instance()
        mgr.stop_all()
        self._notify("Stopped all bots.", title="Bot Manager")
        self.refresh_data()

    def action_panic_cancel_all(self) -> None:
        """Emergency killswitch: cancel all orders across all bots."""
        from sktui.services.bot_engine import BotManager

        mgr = BotManager.get_instance()
        res = mgr.panic_all(mode="CANCEL_ALL")
        self._notify("EMERGENCY: Cancelled all open orders across fleet!", title="Killswitch", severity="warning")
        self.refresh_data()

    def action_panic_flatten_all(self) -> None:
        """Emergency flatten: close positions and halt fleet."""
        from sktui.services.bot_engine import BotManager

        mgr = BotManager.get_instance()
        res = mgr.panic_all(mode="FLATTEN_ALL")
        self._notify("EMERGENCY: Flattened positions and halted all bots!", title="Killswitch", severity="error")
        self.refresh_data()

    def action_refresh_data(self) -> None:
        """Manual refresh."""
        self.refresh_data()

    @on(Button.Pressed, "#btn-bot-deploy-start")
    def on_start_pressed(self) -> None:
        self.action_toggle_bot_start()

    @on(Button.Pressed, "#btn-bot-pause-resume")
    def on_pause_pressed(self) -> None:
        self.action_toggle_bot_pause()

    @on(Button.Pressed, "#btn-bot-stop")
    def on_stop_pressed(self) -> None:
        self.action_bot_stop()

    @on(Button.Pressed, "#btn-bot-panic-cancel")
    def on_panic_cancel_pressed(self) -> None:
        self.action_panic_cancel_all()

    @on(Button.Pressed, "#btn-bot-panic-flatten")
    def on_panic_flatten_pressed(self) -> None:
        self.action_panic_flatten_all()

    @on(Button.Pressed, "#btn-bot-refresh")
    def on_refresh_pressed(self) -> None:
        self.action_refresh_data()

    @on(Button.Pressed, "#btn-bot-close")
    def on_close_pressed(self) -> None:
        self.dismiss(None)


class BrokerVerifyModal(ModalScreen):
    """Interactive Broker Sandbox & Connectivity Verification Diagnostic Modal."""

    BINDINGS = [
        Binding("escape", "dismiss(None)",        "Close"),
        Binding("q",      "dismiss(None)",        "Close", show=False),
        Binding("r",      "rerun_all",            "Rerun All"),
        Binding("c",      "run_crypto_only",      "Crypto Only"),
        Binding("p",      "run_paper_only",       "Paper Only"),
        Binding("e",      "run_endpoints_only",   "Endpoints Only"),
    ]

    def __init__(
        self,
        mode: str | None = None,
        paper: bool = True,
        client: Any = None,
    ) -> None:
        super().__init__()
        self.mode = mode
        if mode == "live":
            self.paper = False
        else:
            self.paper = bool(paper)
        self.client = client
        self.summary: Any = None
        self._results_map: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label("🔒  Broker Sandbox & API Verification Diagnostics", classes="title")
            yield Static(id="verify-status-strip")
            yield Rule()

            # Control Row: Mode, Environment
            with Horizontal(classes="row"):
                yield Label(" Mode: ", classes="field-label")
                yield Select(
                    options=[
                        ("Full Diagnostic Suite", "all"),
                        ("AES-GCM 256 Crypto Auth", "crypto"),
                        ("Paper Trading Sandbox", "paper"),
                        ("Broker Endpoint Probing", "endpoints"),
                    ],
                    value=self.mode if self.mode in ["all", "crypto", "paper", "endpoints"] else "all",
                    id="select-verify-mode",
                )
                yield Label("  Environment: ", classes="field-label")
                yield Select(
                    options=[
                        ("Paper Sandbox Simulation", "sandbox"),
                        ("Live Broker Endpoints", "live"),
                    ],
                    value="sandbox" if self.paper else "live",
                    id="select-verify-env",
                )

            # Button Controls Row
            with Horizontal(classes="row buttons"):
                yield Button("▶ Rerun All (r)", id="btn-verify-all", variant="success")
                yield Button("🔐 Crypto (c)", id="btn-verify-crypto", variant="primary")
                yield Button("📝 Paper (p)", id="btn-verify-paper", variant="primary")
                yield Button("🌐 Endpoints (e)", id="btn-verify-endpoints", variant="primary")
                yield Button("✗ Close (Esc)", id="btn-verify-close")

            yield Rule()

            # KPI / Telemetry gauges strip
            yield Label("  Verification KPI Telemetry & Execution Gauges", classes="field-group-label")
            yield Static(id="verify-telemetry-gauges")
            yield Rule()

            # Diagnostic Check Results Matrix Table
            yield Label("  Diagnostic Check Results Matrix", classes="field-group-label")
            yield DataTable(id="t-verify-results", cursor_type="row")
            yield Rule()

            # Inspection detail trace panel
            yield Label("  Inspection Detail Trace & Diagnostic Telemetry", classes="field-group-label")
            yield Static(id="verify-detail-panel")

            # Hotkey hint footer
            yield Static("  Esc/q = Close · r = Rerun All · c = Crypto Only · p = Paper Only · e = Endpoints Only", classes="hint")

    def on_mount(self) -> None:
        try:
            table = self.query_one("#t-verify-results", DataTable)
            table.add_column("Check Name", key="name")
            table.add_column("Domain", key="domain")
            table.add_column("Status", key="status")
            table.add_column("Latency (ms)", key="latency")
            table.add_column("Message", key="message")
        except Exception:
            pass

        if self.mode == "crypto":
            self.action_run_crypto_only()
        elif self.mode == "paper":
            self.action_run_paper_only()
        elif self.mode in ("endpoints", "live"):
            self.action_run_endpoints_only()
        else:
            self.action_rerun_all()

    def _get_verifier(self) -> Any:
        from sktui.api.client import Client
        from sktui.services.broker_verifier import BrokerVerifier

        target_client = self.client
        if target_client is None:
            if self.paper:
                target_client = Client(
                    api_key="SANDBOX",
                    access_token="SANDBOX",
                    customer_id="123456",
                    paper=True,
                )
            else:
                import sktui.config as cfg
                target_client = Client(
                    api_key=getattr(cfg, "API_KEY", "") or "LIVE_PROBE",
                    access_token=getattr(cfg, "ACCESS_TOKEN", "") or "LIVE_PROBE",
                    customer_id=getattr(cfg, "CUSTOMER_ID", "") or "0",
                    paper=False,
                )
        return BrokerVerifier(client=target_client, paper=self.paper)

    def _display_summary(self, summary: Any) -> None:
        self.summary = summary
        self._results_map.clear()

        # Update status strip
        passed = getattr(summary, "passed", False)
        pass_style = "bold green" if passed else "bold red"
        status_banner = (
            f" [bold white]Mode: {'Paper Sandbox Simulation' if self.paper else 'Live Broker'}[/bold white]  ·  "
            f"Status: [{pass_style}]{'ALL CHECKS PASSED' if passed else 'VERIFICATION FAILED'}[/{pass_style}]  ·  "
            f"Total Checks: [bold cyan]{summary.total_count}[/bold cyan]  ·  "
            f"Passed: [bold green]{summary.passed_count}[/bold green]  ·  "
            f"Failed: [bold red]{summary.failed_count}[/bold red]  ·  "
            f"Skipped: [bold yellow]{summary.skipped_count}[/bold yellow]  ·  "
            f"Total Duration: [bold]{summary.total_latency_ms:.2f} ms[/bold]"
        )
        try:
            self.query_one("#verify-status-strip", Static).update(status_banner)
        except Exception:
            pass

        # Update telemetry gauges
        p = current_palette()
        gauges_text = Text()
        gauges_text.append("  ── Execution Telemetry & Performance Gauges ──────────────────────────────────────────\n\n", style=p.subtle)
        gauges_text.append("  Overall Health:       ", style=p.muted)
        if passed:
            gauges_text.append("✔ 100% HEALTHY (Zero Critical Faults)\n", style="bold green")
        else:
            gauges_text.append(f"✖ FAILING ({summary.failed_count} tests failed)\n", style="bold red")

        gauges_text.append("  Checks Overview:      ", style=p.muted)
        gauges_text.append(f"Pass: {summary.passed_count}  ·  Fail: {summary.failed_count}  ·  Skip: {summary.skipped_count}\n", style=f"bold {p.fg}")

        gauges_text.append("  Latency Metrics:      ", style=p.muted)
        gauges_text.append(f"Avg: {summary.avg_latency_ms:.2f} ms/check  ·  Total: {summary.total_latency_ms:.2f} ms\n", style=f"bold {p.teal}")

        gauges_text.append("  Target Environment:   ", style=p.muted)
        gauges_text.append(f"{'Paper Sandbox Simulation (Zero-Risk Mock Mode)' if self.paper else 'Live Broker Production Network'}\n", style=f"bold {p.primary}")
        try:
            self.query_one("#verify-telemetry-gauges", Static).update(gauges_text)
        except Exception:
            pass

        # Populate DataTable
        first_res = None
        try:
            table = self.query_one("#t-verify-results", DataTable)
            table.clear()
            for r in summary.results:
                self._results_map[r.name] = r
                if first_res is None:
                    first_res = r

                if r.status == "PASS":
                    status_text = Text(" PASS ", style="bold green")
                elif r.status == "FAIL":
                    status_text = Text(" FAIL ", style="bold red")
                else:
                    status_text = Text(" SKIP ", style="bold yellow")

                lat_style = "green" if r.latency_ms < 20.0 else ("yellow" if r.latency_ms < 100.0 else "red")
                lat_text = Text(f"{r.latency_ms:.2f}", style=lat_style)

                table.add_row(
                    Text(r.name, style="bold white"),
                    Text(r.domain, style="cyan"),
                    status_text,
                    lat_text,
                    Text(r.message, style="dim white"),
                    key=r.name,
                )
        except Exception:
            # Fallback if table unmounted or not queryable
            for r in summary.results:
                self._results_map[r.name] = r
                if first_res is None:
                    first_res = r

        if first_res:
            self._display_detail(first_res)

    def _display_detail(self, result: Any) -> None:
        p = current_palette()
        txt = Text()
        txt.append(f"\n  Check: {result.name}  [{result.domain.upper()}]\n", style=f"bold {p.primary}")
        txt.append("  Status: ", style=p.muted)
        if result.status == "PASS":
            txt.append("PASS\n", style="bold green")
        elif result.status == "FAIL":
            txt.append("FAIL\n", style="bold red")
        else:
            txt.append("SKIPPED\n", style="bold yellow")
        txt.append(f"  Latency: {result.latency_ms:.2f} ms\n", style=f"bold {p.teal}")
        txt.append(f"  Message: {result.message}\n", style=p.fg)
        if result.details:
            txt.append("  Trace / Diagnostic Details:\n", style=p.subtle)
            for k, v in result.details.items():
                txt.append(f"    • {k}: {v}\n", style=p.muted)
        try:
            self.query_one("#verify-detail-panel", Static).update(txt)
        except Exception:
            pass

    @on(DataTable.RowSelected, "#t-verify-results")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = str(event.row_key.value) if hasattr(event.row_key, "value") else str(event.row_key)
        res = self._results_map.get(row_key)
        if res:
            self._display_detail(res)

    @on(DataTable.RowHighlighted, "#t-verify-results")
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None:
            row_key = str(event.row_key.value) if hasattr(event.row_key, "value") else str(event.row_key)
            res = self._results_map.get(row_key)
            if res:
                self._display_detail(res)

    @on(Select.Changed, "#select-verify-env")
    def on_env_changed(self, event: Select.Changed) -> None:
        self.paper = (str(event.value) == "sandbox")
        self.action_rerun_all()

    @on(Select.Changed, "#select-verify-mode")
    def on_mode_changed(self, event: Select.Changed) -> None:
        val = str(event.value)
        if val == "crypto":
            self.action_run_crypto_only()
        elif val == "paper":
            self.action_run_paper_only()
        elif val == "endpoints":
            self.action_run_endpoints_only()
        else:
            self.action_rerun_all()

    @on(Button.Pressed, "#btn-verify-all")
    def on_btn_verify_all(self) -> None:
        self.action_rerun_all()

    @on(Button.Pressed, "#btn-verify-crypto")
    def on_btn_verify_crypto(self) -> None:
        self.action_run_crypto_only()

    @on(Button.Pressed, "#btn-verify-paper")
    def on_btn_verify_paper(self) -> None:
        self.action_run_paper_only()

    @on(Button.Pressed, "#btn-verify-endpoints")
    def on_btn_verify_endpoints(self) -> None:
        self.action_run_endpoints_only()

    @on(Button.Pressed, "#btn-verify-close")
    def on_btn_close(self) -> None:
        self.dismiss(None)

    def action_rerun_all(self) -> None:
        """Run full verification suite and refresh UI."""
        verifier = self._get_verifier()
        summary = verifier.run_all_checks(client=verifier.client, sandbox_only=self.paper)
        self._display_summary(summary)

    def action_run_crypto_only(self) -> None:
        """Run only cryptographic checks."""
        import time
        from sktui.services.broker_verifier import VerificationSummary
        verifier = self._get_verifier()
        t0 = time.monotonic()
        results = verifier.verify_crypto()
        dur = round((time.monotonic() - t0) * 1000.0, 2)
        summary = VerificationSummary(results=results, duration_ms=dur)
        self._display_summary(summary)

    def action_run_paper_only(self) -> None:
        """Run only paper trading sandbox simulation checks."""
        import time
        from sktui.services.broker_verifier import VerificationSummary
        verifier = self._get_verifier()
        t0 = time.monotonic()
        results = verifier.verify_paper_sandbox()
        dur = round((time.monotonic() - t0) * 1000.0, 2)
        summary = VerificationSummary(results=results, duration_ms=dur)
        self._display_summary(summary)

    def action_run_endpoints_only(self) -> None:
        """Run only endpoint probes."""
        import time
        from sktui.services.broker_verifier import VerificationSummary
        verifier = self._get_verifier()
        t0 = time.monotonic()
        results = verifier.verify_endpoints(client=verifier.client)
        dur = round((time.monotonic() - t0) * 1000.0, 2)
        summary = VerificationSummary(results=results, duration_ms=dur)
        self._display_summary(summary)



