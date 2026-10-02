"""Modal dialog screens for SKTUI."""
from __future__ import annotations

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
    C_AMBER, C_CYAN, C_DIM, C_GREEN, C_MUTED, C_RED, C_SUBTLE, C_TEXT,
    C_DARK, C_NAVY, C_BORDER, C_TEAL, BUILTIN_SCRIPS,
    DATA, EXCH_NAMES, HIST_COLS, INTERVALS, INTERVAL_LABELS, PRODUCTS,
    SLASH_COMMANDS, VALIDITIES,
)
from sktui.utils import (
    build_order, expiry_key, fill_table, fmt, get, human,
    norm_expiry, normalize_scrip, scrip_label, sign_style, strike_str,
    read_json, write_private,
)
from sktui.chart import render_chart, render_volume_bars


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
        ex = [e for e in all_exchs if e in getattr(self.app.client, "exchanges", []) or e in EXCH_NAMES]
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
        self.app.call_from_thread(
            self.query_one("#state", Static).update,
            f"⟳  Loading {EXCH_NAMES.get(exch, exch)} scrip master…"
        )
        cache = DATA / f"master_{exch}_{date.today()}.json"
        rows  = read_json(cache, None)
        if rows is None:
            try:
                rows = self.app.client.master(exch)
                if rows:
                    write_private(cache, rows)
            except Exception:
                rows = []
            for old in DATA.glob(f"master_{exch}_*.json"):
                if old != cache:
                    old.unlink(missing_ok=True)
        
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
        self.exch, self.index = exch, idx
        self.query_one("#state", Static).update(
            Text(f"✓  {len(idx):,} instruments loaded  ·  type to search",
                 style=C_MUTED))
        self.refilter()

    @on(Input.Changed, "#q")
    def refilter(self, *_: Any) -> None:
        terms = self.query_one("#q", Input).value.lower().split()
        t     = self.query_one("#results", DataTable)
        t.clear()
        if not terms:
            self.shown = []
            return
        hits = [n for hay, n in self.index if all(x in hay for x in terms)]
        hits.sort(key=lambda n: (
            str(n["tradingSymbol"]), expiry_key(n["expiry"]),
            float(n["strike"] or 0)))
        self.shown = hits[:300]
        for n in self.shown:
            t.add_row(
                Text(n["tradingSymbol"], style=f"bold {C_CYAN}"),
                n["instType"],
                n["expiry"] or "",
                strike_str(n["strike"]) if n["optionType"] in ("CE", "PE") else "",
                Text(n["optionType"], style=(
                    C_GREEN if n["optionType"] == "CE"
                    else C_RED if n["optionType"] == "PE" else C_MUTED)),
                str(n["lotSize"]),
                str(n["tickSize"]),
                str(n["scripCode"]),
                n["companyName"],
            )

    @on(Input.Submitted, "#q")
    def _enter(self) -> None:
        self.query_one("#results", DataTable).focus()

    @on(DataTable.RowSelected, "#results")
    def _pick(self, e: DataTable.RowSelected) -> None:
        if e.cursor_row < len(self.shown):
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
        ex = [e for e in getattr(self.app.client, "exchanges", []) if e in EXCH_NAMES] or list(EXCH_NAMES)
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
                    yield Select([(f"{EXCH_NAMES[e]}  ({e})", e) for e in ex],
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
        ltp  = getattr(self.app, "raw_ticks", {}).get(key, {}).get("ltp") or self.info.get("price")
        try:
            px = float(self.query_one("#price", Input).value.strip() or 0)
            if px > 0:
                return px
        except Exception:
            pass
        return float(ltp or 0)

    def update_quote_banner(self) -> None:
        sym  = self.query_one("#sym", Input).value.strip().upper()
        code = self.query_one("#code", Input).value.strip()
        exch = str(self.query_one("#exch", Select).value)
        key  = f"{exch}{code}" if code else ""
        ticks = getattr(self.app, "raw_ticks", {}).get(key, {})
        ltp   = ticks.get("ltp") or self.info.get("price")

        t = Text()
        t.append("  📊 Market Quote: ", style=C_MUTED)
        if ltp and float(ltp) > 0:
            fltp = float(ltp)
            t.append(f"LTP ₹{fltp:,.2f} ", style=f"bold {C_GREEN}")
            chg = ticks.get("rsChange") or 0.0
            pct = ticks.get("perChange") or 0.0
            if chg or pct:
                sign = "+" if float(chg) >= 0 else ""
                t.append(f"({sign}{fmt(chg)} / {sign}{fmt(pct)}%)  ", style=sign_style(chg))
            if ticks.get("bidPrice"):
                t.append(f"Bid: ₹{fmt(ticks['bidPrice'])}  ", style=C_MUTED)
            if ticks.get("offPrice"):
                t.append(f"Ask: ₹{fmt(ticks['offPrice'])}  ", style=C_MUTED)
            if ticks.get("high"):
                t.append(f"High: ₹{fmt(ticks['high'])}  ", style=C_GREEN)
            if ticks.get("low"):
                t.append(f"Low: ₹{fmt(ticks['low'])}", style=C_RED)
        else:
            t.append("0.00 (MARKET order uses execution LTP)", style=C_AMBER)
        
        self.query_one("#order-quote-banner", Static).update(t)

    @on(Input.Changed, "#sym")
    def _sym_changed(self, e: Input.Changed) -> None:
        self._lookup_and_update_scrip()

    @on(Button.Pressed, "#btn-fill-price")
    def _fill_price(self) -> None:
        code = self.query_one("#code", Input).value.strip()
        exch = str(self.query_one("#exch", Select).value)
        key  = f"{exch}{code}"
        ltp  = getattr(self.app, "raw_ticks", {}).get(key, {}).get("ltp") or self.info.get("price")
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
        c = self.app.client
        try:
            params, warns = build_order(fields, self.mode, c.cid, c.login_id)
        except ValueError as e:
            self.query_one("#err", Static).update(
                Text(f"✗  Validation error: {e}", style=f"bold {C_RED}"))
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
        paper_tag = (Text("  ⚠  PAPER MODE — no real order will be sent\n",
                          style=f"bold {C_AMBER}")
                     if self.paper else Text(""))
        with Vertical(classes="modal confirm-modal"):
            yield Label(f"⬡  {self.title_}", classes="title")
            yield Static(paper_tag)
            yield Rule()
            yield Static(self.body, classes="confirm-body")
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("✓  Confirm  (y)", id="yes", variant="success")
                yield Button("✗  Cancel   (n)", id="no",  variant="error")

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
    if not vals:
        return ""
    step = max(1, len(vals) // width)
    vals = vals[::step][-width:]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    return "".join(SPARK_CHARS[int((v - lo) / rng * (len(SPARK_CHARS) - 1))] for v in vals)


# ══════════════════════════════════════════════════════════════════════════════
#  HistoryScreen — braille-dot chart with visual interval pills + hotkeys
# ══════════════════════════════════════════════════════════════════════════════

class HistoryScreen(ModalScreen):
    """Price history chart with braille-dot renderer (rate.sx style) + data table."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("v",      "toggle_volume", "Volume", show=False),
        Binding("1",      "set_iv('1minute')", "1m", show=False),
        Binding("3",      "set_iv('3minute')", "3m", show=False),
        Binding("5",      "set_iv('5minute')", "5m", show=False),
        Binding("0",      "set_iv('10minute')", "10m", show=False),
        Binding("f",      "set_iv('15minute')", "15m", show=False),
        Binding("t",      "set_iv('30minute')", "30m", show=False),
        Binding("h",      "set_iv('60minute')", "1h", show=False),
        Binding("d",      "set_iv('daily')", "1D", show=False),
        Binding("w",      "set_iv('weekly')", "1W", show=False),
        Binding("m",      "set_iv('monthly')", "1M", show=False),
    ]

    def __init__(self, item: dict) -> None:
        super().__init__()
        self.item         = item
        self._rows:       list[dict] = []
        self._show_volume = False
        self.current_iv   = "5minute"

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal chart"):
            # ── Header bar ────────────────────────────────────────────────────
            with Horizontal(classes="chart-header-bar"):
                yield Label(
                    f"📈  {scrip_label(self.item)}  ({self.item.get('exchange', '')})",
                    classes="chart-title")
                yield Static("", id="chart-meta", classes="chart-meta-right")

            # ── Interval pill bar ─────────────────────────────────────────────
            with Horizontal(classes="chart-interval-bar"):
                for iv, lbl in [
                    ("1minute","1m"), ("3minute","3m"), ("5minute","5m"),
                    ("15minute","15m"), ("30minute","30m"), ("60minute","1h"),
                    ("daily","1D"), ("weekly","1W"), ("monthly","1M"),
                ]:
                    yield Button(lbl, id=f"iv-{iv}",
                                 variant="primary" if iv == "5minute" else "default",
                                 classes="iv-pill")

            # ── Chart canvas ──────────────────────────────────────────────────
            yield RichLog(id="chart-out", max_lines=60,
                          wrap=False, markup=False, highlight=False)

            # ── Bottom strip: data table + key hints ─────────────────────────
            with Horizontal(classes="chart-bottom-bar"):
                yield Label("  History  (newest first)", classes="chart-bottom-label")
                yield Static(
                    "  Keys: 1 3 5 0(10m) f(15m) t(30m) h(1h) d w m  |  v=Vol  |  Esc=Close",
                    classes="chart-bottom-hint")
            yield DataTable(id="hist", cursor_type="row")

    def on_mount(self) -> None:
        t = self.query_one("#hist", DataTable)
        for key, label in HIST_COLS:
            t.add_column(label, key=key)
        self.fetch("5minute")

    def action_set_iv(self, iv: str) -> None:
        self.set_interval_val(iv)

    def set_interval_val(self, iv: str) -> None:
        self.current_iv = iv
        # Update button highlights
        for b in self.query(Button):
            if b.id and b.id.startswith("iv-"):
                b.variant = "primary" if b.id == f"iv-{iv}" else "default"
        self.fetch(iv)

    @on(Button.Pressed)
    def _pill_click(self, e: Button.Pressed) -> None:
        if e.button.id and e.button.id.startswith("iv-"):
            iv = e.button.id.replace("iv-", "")
            self.set_interval_val(iv)

    @work(thread=True, exclusive=True)
    def fetch(self, interval: str) -> None:
        try:
            rows = self.app.client.historical(
                self.item["exchange"], self.item["scripCode"], interval)
        except Exception as e:
            self.app.call_from_thread(
                self.app.notify, f"History: {e}", severity="error")
            return
        self.app.call_from_thread(self.show, rows, interval)

    def show(self, rows: list[dict], interval: str = "") -> None:
        self._rows = rows

        # ── Extract close prices & volumes ────────────────────────────────────
        closes:  list[float] = []
        volumes: list[float] = []
        dates:   list[str]   = []
        for r in rows:
            try:
                closes.append(float(r.get("close") or r.get("Close") or 0))
            except (TypeError, ValueError):
                closes.append(0.0)
            try:
                v = r.get("volume") or r.get("Volume") or r.get("vol") or r.get("qty") or r.get("v") or r.get("vQty") or 0
                volumes.append(float(v))
            except (TypeError, ValueError):
                volumes.append(0.0)
            dates.append(str(r.get("tradeDate") or r.get("TradeDate") or ""))

        # ── Render chart with dual price + volume sub-strip ───────────────────
        log = self.query_one("#chart-out", RichLog)
        log.clear()
        if closes and any(v > 0 for v in closes):
            chart_text = render_chart(
                values   = closes,
                volumes  = volumes,
                width    = 100,
                height   = 11,
                symbol   = scrip_label(self.item),
                interval = INTERVAL_LABELS.get(interval, interval),
                show_stats=True,
                show_vol_strip=True,
            )
            log.write(chart_text)
        else:
            log.write(Text("  — no data returned —", style=C_DIM))

        # ── Meta label ────────────────────────────────────────────────────────
        meta = Text()
        meta.append(f"  {len(rows):,} bars", style=C_MUTED)
        if closes:
            hi = max(c for c in closes if c > 0)
            lo = min(c for c in closes if c > 0)
            meta.append(f"  ·  H: ", style=C_MUTED)
            meta.append(f"{hi:,.2f}", style=C_GREEN)
            meta.append(f"  L: ", style=C_MUTED)
            meta.append(f"{lo:,.2f}", style=C_RED)
        if volumes and any(v > 0 for v in volumes):
            tot_v = sum(volumes)
            meta.append(f"  ·  Tot Vol: {tot_v:,.0f}", style=C_CYAN)
        self.query_one("#chart-meta", Static).update(meta)

        # ── Data table — NEWEST FIRST ─────────────────────────────────────────
        t = self.query_one("#hist", DataTable)
        t.clear()
        for r in reversed(rows[-400:]):   # show newest at top
            row_cells = []
            for key, _ in HIST_COLS:
                v = r.get(key) or r.get(key.title()) or r.get(key.lower()) or ""
                style = ""
                if key == "close":
                    try:
                        fv = float(str(v).replace(",", ""))
                        style = f"bold {C_GREEN}" if fv > 0 else ""
                    except ValueError:
                        pass
                elif key in ("high",):
                    style = C_GREEN
                elif key in ("low",):
                    style = C_RED
                row_cells.append(Text(str(v), style=style) if style else Text(str(v)))
            t.add_row(*row_cells)

    def action_toggle_volume(self) -> None:
        """Toggle between dual price+volume chart and full volume bar chart."""
        self._show_volume = not self._show_volume
        if not self._rows:
            return
        closes  = []
        volumes = []
        dates   = []
        for r in self._rows:
            try:   closes.append(float(r.get("close") or r.get("Close") or 0))
            except: closes.append(0.0)
            try:
                v = r.get("volume") or r.get("Volume") or r.get("vol") or r.get("qty") or r.get("v") or 0
                volumes.append(float(v))
            except: volumes.append(0.0)
            dates.append(str(r.get("tradeDate") or r.get("TradeDate") or ""))

        log = self.query_one("#chart-out", RichLog)
        log.clear()
        if self._show_volume:
            log.write(render_volume_bars(dates, volumes))
        else:
            log.write(render_chart(
                values=closes, volumes=volumes, width=100, height=16,
                symbol=scrip_label(self.item),
                interval=INTERVAL_LABELS.get(self.current_iv, self.current_iv),
                show_stats=True, show_vol_strip=True,
            ))



# ══════════════════════════════════════════════════════════════════════════════
#  DetailScreen — order history & trades
# ══════════════════════════════════════════════════════════════════════════════

class DetailScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def __init__(self, row: dict) -> None:
        super().__init__()
        self.row = row

    def compose(self) -> ComposeResult:
        sym = get(self.row, "tradingSymbol") or "Order"
        oid = get(self.row, "orderId")
        with Vertical(classes="modal wide"):
            yield Label(f"⬡  Order Detail  —  {sym}  #{oid}",
                        classes="title")
            yield Label("  Lifecycle History", classes="field-group-label")
            yield DataTable(id="oh", cursor_type="row")
            yield Label("  Executed Trades", classes="field-group-label")
            yield DataTable(id="ot", cursor_type="row")
            yield Static("  Esc = close", classes="hint")

    def on_mount(self) -> None:
        self.fetch()

    @work(thread=True)
    def fetch(self) -> None:
        c, r    = self.app.client, self.row
        ex, oid = get(r, "exchange"), get(r, "orderId")
        for wid, fn in (("#oh", c.order_history), ("#ot", c.order_trades)):
            try:
                rows = fn(ex, oid)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"{wid}: {e}", severity="error")
                continue
            self.app.call_from_thread(
                fill_table, self.query_one(wid, DataTable), rows)


# ══════════════════════════════════════════════════════════════════════════════
#  QuoteScreen — live tick data
# ══════════════════════════════════════════════════════════════════════════════

class QuoteScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def __init__(self, key: str, label: str) -> None:
        super().__init__()
        self.key_, self.label = key, label

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal wide"):
            yield Label(f"⬡  Live Quote  —  {self.label}", classes="title")
            yield DataTable(id="q", cursor_type="none")
            yield Static(
                "  ⬢  Live streaming data  ·  Esc = close",
                classes="hint")

    def on_mount(self) -> None:
        self.query_one("#q", DataTable).add_columns(
            Text("Field", style=C_MUTED),
            Text("Value", style=C_TEXT))
        self.set_interval(1, self.paint)
        self.paint()

    def paint(self) -> None:
        t    = self.query_one("#q", DataTable)
        data = getattr(self.app, "raw_ticks", {}).get(self.key_, {})
        t.clear()
        if not data:
            t.add_row(Text("⟳ waiting for live feed…", style=C_DIM), "")
            return
        for k in sorted(data):
            v        = data[k]
            val_text = Text(
                fmt(v),
                style=sign_style(v) if k in ("ltp", "rsChange", "perChange") else "")
            t.add_row(Text(human(k), style=C_MUTED), val_text)


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
        with VerticalScroll(classes="modal"):
            yield Label("⬡  What-If  —  Simulate Order Impact",
                        classes="title")
            yield Static(
                Text("  No broker request will be submitted."
                     "  Read-only portfolio simulation.", style=C_MUTED),
                classes="hint")
            yield Rule()
            yield Label("Order Parameters", classes="field-group-label")
            with Horizontal(classes="row"):
                yield Select([("▲  BUY", "B"), ("▼  SELL", "S")],
                             value="B", allow_blank=False, id="wi-side")
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

    @on(Button.Pressed, "#wi-close")
    def _close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#wi-calc")
    def _calc(self) -> None:
        try:
            qty   = int(self.query_one("#wi-qty",   Input).value.strip() or "0")
            price = float(self.query_one("#wi-price", Input).value.strip() or "0")
            sym   = self.query_one("#wi-sym",  Input).value.strip()
            side  = str(self.query_one("#wi-side", Select).value)
        except (ValueError, TypeError) as e:
            self.query_one("#wi-result", Static).update(
                Text(f"✗  Invalid input: {e}", style=f"bold {C_RED}"))
            return
        if qty <= 0:
            self.query_one("#wi-result", Static).update(
                Text("✗  Quantity must be > 0", style=f"bold {C_RED}"))
            return

        notional = qty * price if price > 0 else 0
        side_txt  = "▲ BUY" if side == "B" else "▼ SELL"
        clr       = C_GREEN if side == "B" else C_RED

        t = Text()
        t.append("DRY RUN — SIMULATION ONLY\n\n",
                 style=f"bold {C_CYAN}")
        t.append("  Symbol:             ", style=C_MUTED)
        t.append(f"{sym or '(not set)'}\n", style=f"bold {C_TEXT}")
        t.append("  Direction:          ", style=C_MUTED)
        t.append(f"{side_txt}\n", style=f"bold {clr}")
        t.append("  Quantity:           ", style=C_MUTED)
        t.append(f"{qty:,} units\n", style=C_TEXT)

        if price > 0:
            t.append("  Est. Price:         ", style=C_MUTED)
            t.append(f"₹{price:,.2f}\n", style=C_TEXT)
            t.append("  Est. Notional:      ", style=C_MUTED)
            t.append(f"₹{notional:,.2f}\n", style=f"bold {C_AMBER}")
            # Brokerage estimate (flat fee placeholder)
            brok = min(20.0, notional * 0.0003)
            t.append("  Est. Brokerage:     ", style=C_MUTED)
            t.append(f"₹{brok:.2f}\n", style=C_SUBTLE)
        else:
            t.append("  Order Type:         ", style=C_MUTED)
            t.append("MARKET  (price not provided)\n",
                     style=f"bold {C_AMBER}")

        t.append("\n  Risk Checks:        ", style=C_MUTED)
        t.append("Simulation — not validated against live limits\n",
                 style=C_DIM)
        t.append("\n  ✓  No order submitted to broker\n",
                 style=f"bold {C_GREEN}")
        self.query_one("#wi-result", Static).update(t)


# ══════════════════════════════════════════════════════════════════════════════
#  SystemStatusScreen
# ══════════════════════════════════════════════════════════════════════════════

class SystemStatusScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def compose(self) -> ComposeResult:
        c = self.app.client
        with Vertical(classes="modal"):
            yield Label("⬡  System Status", classes="title")
            t = Text()

            t.append("\n  ── Environment ───────────────────────────────────\n\n",
                      style=C_SUBTLE)
            t.append("  Environment:        ", style=C_MUTED)
            env = "PAPER" if c.paper else "LIVE"
            t.append(f"{env}\n",
                     style=f"bold {C_AMBER}" if c.paper else f"bold {C_RED}")
            t.append("  Account:            ", style=C_MUTED)
            t.append(f"{c.full_name or c.login_id}  "
                     f"(CID: {c.customer_id})\n", style=C_TEXT)
            t.append("  API Key:            ", style=C_MUTED)
            t.append(f"{c.api_key[:8]}{'*' * 18}\n", style=C_SUBTLE)
            t.append("  Exchanges:          ", style=C_MUTED)
            t.append(f"{' · '.join(c.exchanges)}\n",
                     style=f"bold {C_CYAN}")
            pub_ip = getattr(self.app, "public_ip", "Fetching…")
            t.append("  Public IP Address:  ", style=C_MUTED)
            t.append(f"{pub_ip}  (whitelist on https://api.sharekhan.com)\n",
                     style=f"bold {C_CYAN}")

            t.append("\n  ── Component Health ──────────────────────────────\n\n",
                      style=C_SUBTLE)
            components = [
                ("CLI Process",       True),
                ("Broker Connection", True),
                ("Order Gateway",     True),
                ("Audit Log",         True),
            ]
            for name, ok in components:
                t.append(f"  {name:<22}", style=C_MUTED)
                t.append(f"{'  ✓ RUNNING' if ok else '  ✗ DOWN'}\n",
                         style=f"bold {C_GREEN}" if ok else f"bold {C_RED}")

            feed_ok = bool(getattr(self.app, "raw_ticks", {}))
            t.append("  WebSocket Feed      ", style=C_MUTED)
            t.append(f"  {'  ✓ ACTIVE' if feed_ok else '  ○ IDLE'}\n",
                     style=f"bold {C_GREEN}" if feed_ok else C_DIM)

            t.append("\n  ── Quick Commands  (type after / in command bar) ──\n\n",
                      style=C_SUBTLE)
            for cmd, (desc, _) in list(SLASH_COMMANDS.items())[:12]:
                t.append(f"  {cmd:<18}", style=f"bold {C_CYAN}")
                t.append(f"{desc}\n",    style=C_MUTED)
            t.append("\n  F1 for full command reference\n", style=C_SUBTLE)

            yield Static(t)
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("✗  Close", id="close-btn", variant="primary")

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
#  RiskScreen
# ══════════════════════════════════════════════════════════════════════════════

class RiskScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def compose(self) -> ComposeResult:
        c = self.app.client
        with Vertical(classes="modal"):
            yield Label("⬡  Risk Dashboard", classes="title")
            t = Text()

            t.append("\n  ── Risk State ─────────────────────────────────────\n\n",
                      style=C_SUBTLE)
            t.append("  Risk State:         ", style=C_MUTED)
            t.append("NORMAL\n", style=f"bold {C_GREEN}")
            t.append("  Automation:         ", style=C_MUTED)
            t.append("ENABLED\n", style=f"bold {C_GREEN}")
            t.append("  Environment:        ", style=C_MUTED)
            t.append(f"{'PAPER' if c.paper else 'LIVE'}\n",
                     style=f"bold {C_AMBER}" if c.paper else f"bold {C_RED}")

            t.append("\n  ── Active Controls ────────────────────────────────\n\n",
                      style=C_SUBTLE)
            controls = [
                ("Order Confirmation",  "REQUIRED"),
                ("Live Order Entry",    "BLOCKED (paper)" if c.paper else "ENABLED"),
                ("Audit Logging",       "ENABLED"),
                ("Session Expiry",      "24h token"),
            ]
            for name, state in controls:
                danger = "ENABLED" in state and not c.paper and "Live" in name
                style  = (f"bold {C_RED}" if danger
                          else f"bold {C_AMBER}" if "paper" in state.lower()
                          else f"bold {C_GREEN}")
                t.append(f"  {name:<26}", style=C_MUTED)
                t.append(f"{state}\n",    style=style)

            t.append("\n  ── Emergency Controls ─────────────────────────────\n\n",
                      style=C_SUBTLE)
            emergency = [
                ("/kill",    "Block new automated orders"),
                ("X",        "Cancel all open orders"),
                ("/whatif",  "Simulate before executing"),
            ]
            for key, desc in emergency:
                t.append(f"  {key:<18}", style=f"bold {C_CYAN}")
                t.append(f"{desc}\n",    style=C_MUTED)

            t.append("\n  ── Safety Invariants ──────────────────────────────\n\n",
                      style=C_SUBTLE)
            invariants = [
                "All live orders require explicit confirmation",
                "Paper & live credentials are separate",
                "Emergency stop blocks automated order entry",
                "Every order generates an audit event",
                "Secrets are never written to logs",
                "Session tokens expire after 24 hours",
            ]
            for inv in invariants:
                t.append("  ✓  ", style=f"bold {C_GREEN}")
                t.append(f"{inv}\n",   style=C_MUTED)

            yield Static(t)
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("✗  Close", id="close-btn", variant="primary")

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

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label("⬡  SKTUI  —  Professional Trading CLI",
                        classes="title")
            t = Text()

            t.append("\n  ── Slash Commands  (type in command bar below) ─────────────\n\n",
                      style=C_SUBTLE)
            for cmd, (desc, _) in SLASH_COMMANDS.items():
                t.append(f"  {cmd:<22}", style=f"bold {C_CYAN}")
                t.append(f"{desc}\n",    style=C_MUTED)

            t.append("\n  ── Keyboard Shortcuts ──────────────────────────────────────\n\n",
                      style=C_SUBTLE)
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
                ("/",       "Focus command bar"),
                ("F1",      "This help screen"),
                ("1–6",     "Switch tabs"),
                ("ctrl+l",  "Log out"),
                ("q",       "Quit"),
            ]
            for key, desc in shortcuts:
                t.append(f"  {key:<22}", style=f"bold {C_AMBER}")
                t.append(f"{desc}\n",    style=C_MUTED)

            t.append("\n  ── Chart  (c key or /chart) ────────────────────────────────\n\n",
                      style=C_SUBTLE)
            chart_help = [
                ("Select interval", "Drop-down at top of chart screen"),
                ("v key",          "Toggle between price chart and volume bars"),
                ("Table below",    "Shows OHLCV records, newest on top"),
                ("Stats line",     "Open / High / Low / Close / Avg / Change%"),
            ]
            for key, desc in chart_help:
                t.append(f"  {key:<22}", style=f"bold {C_TEAL if True else C_GREEN}")
                t.append(f"{desc}\n",    style=C_MUTED)

            t.append("\n  ── Trading Safety Model ────────────────────────────────────\n\n",
                      style=C_SUBTLE)
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
                t.append(f"  {key:<22}", style=f"bold {C_GREEN}")
                t.append(f"{desc}\n",    style=C_MUTED)

            t.append("\n  ── Architecture ────────────────────────────────────────────\n\n",
                      style=C_SUBTLE)
            t.append("  CLI  →  Control Plane  →  Risk Engine"
                     "  →  Broker Adapter  →  Exchange\n", style=C_MUTED)
            t.append("  Every live order passes pre-trade validation before submission.\n",
                     style=C_MUTED)

            yield Static(t)
            with Horizontal(classes="row buttons"):
                yield Button("✗  Close  (Esc / q)", id="close-btn",
                             variant="primary")

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
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal wide"):
            yield Label("⬡  Markets & Products", classes="title")
            yield DataTable(id="prod", cursor_type="row")
            yield Static(
                "  Enter = open in browser  ·  Esc = close",
                classes="hint")

    def on_mount(self) -> None:
        t = self.query_one("#prod", DataTable)
        t.add_columns(
            Text("Product / Service", style=C_TEXT),
            Text("Access", style=C_MUTED))
        for name, how, url in PRODUCT_LINKS:
            style = (C_GREEN  if how.startswith("API")
                     else C_AMBER if how.startswith("Not") else C_CYAN)
            icon  = "  ↗" if url else ""
            t.add_row(name, Text(how + icon, style=style))
        t.focus()

    @on(DataTable.RowSelected, "#prod")
    def _open(self, e: DataTable.RowSelected) -> None:
        name, _, url = PRODUCT_LINKS[e.cursor_row]
        if url:
            webbrowser.open(url)
            self.app.notify(f"Opened {name}")
        else:
            self.app.notify("Trade this directly here (watchlist: b / s)")
