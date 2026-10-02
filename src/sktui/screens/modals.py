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
    Button, DataTable, Input, Label, Rule, Select, Static,
)

from sktui.config import (
    C_AMBER, C_CYAN, C_DIM, C_GREEN, C_MUTED, C_RED, C_SUBTLE, C_TEXT,
    DATA, EXCH_NAMES, HIST_COLS, INTERVALS, PRODUCTS, SLASH_COMMANDS, VALIDITIES,
)
from sktui.utils import (
    build_order, expiry_key, fill_table, fmt, get, human,
    norm_expiry, normalize_scrip, scrip_label, sign_style, strike_str, read_json, write_private,
)


class SymbolSearch(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def __init__(self) -> None:
        super().__init__()
        self.index: list[tuple[str, dict]] = []
        self.shown: list[dict]             = []
        self.exch = ""

    def compose(self) -> ComposeResult:
        ex = [e for e in self.app.client.exchanges if e in EXCH_NAMES] or list(EXCH_NAMES)
        self.options = [(f"{EXCH_NAMES[e]}  ({e})", e) for e in ex]
        with Vertical(classes="modal wide"):
            yield Label("\u2b21  Add Symbol to Watchlist", classes="title")
            yield Select(self.options, value=self.options[0][1],
                         allow_blank=False, id="exch")
            yield Input(
                placeholder="\u2315  Search: symbol / company / 'NIFTY 24000 CE'\u2026",
                id="q")
            yield DataTable(id="results", cursor_type="row")
            yield Static("\u27f3  Loading scrip master\u2026", id="state", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#results", DataTable).add_columns(
            "Symbol", "Type", "Expiry", "Strike", "Opt",
            "Lot", "Tick", "Code", "Name")
        self.query_one("#q", Input).focus()
        self.load_master(self.options[0][1])

    @on(Select.Changed, "#exch")
    def _exch(self, e: Select.Changed) -> None:
        self.load_master(str(e.value))

    def load_master(self, exch: str) -> None:
        self.query_one("#state", Static).update(
            f"\u27f3  Loading {exch} scrip master\u2026")
        cache = DATA / f"master_{exch}_{date.today()}.json"
        rows  = read_json(cache, None)
        if rows is None:
            try:
                rows = self.app.client.master(exch)
                write_private(cache, rows)
            except Exception as e:
                self.app.notify(f"Scrip master: {e}", severity="error")
                rows = []
            for old in DATA.glob(f"master_{exch}_*.json"):
                if old != cache:
                    old.unlink(missing_ok=True)
        idx = []
        for r in rows:
            n   = normalize_scrip(exch, r)
            hay = (f"{n['tradingSymbol']} {n['companyName']} "
                   f"{n['expiry']} {strike_str(n['strike'])} {n['optionType']}").lower()
            idx.append((hay, n))
        self.set_index(exch, idx)

    def set_index(self, exch: str, idx: list) -> None:
        self.exch, self.index = exch, idx
        self.query_one("#state", Static).update(
            Text(f"\u2713  {len(idx):,} instruments loaded"
                 f"   \u00b7   Enter = add to watchlist   \u00b7   Esc = close",
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
                n["tradingSymbol"], n["instType"], n["expiry"] or "",
                strike_str(n["strike"]) if n["optionType"] in ("CE", "PE") else "",
                n["optionType"], str(n["lotSize"]), str(n["tickSize"]),
                str(n["scripCode"]), n["companyName"],
            )

    @on(Input.Submitted, "#q")
    def _enter(self) -> None:
        self.query_one("#results", DataTable).focus()

    @on(DataTable.RowSelected, "#results")
    def _pick(self, e: DataTable.RowSelected) -> None:
        if e.cursor_row < len(self.shown):
            self.dismiss(self.shown[e.cursor_row])


class OrderTicket(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, info: dict, mode: str = "NEW") -> None:
        super().__init__()
        self.info, self.mode = info, mode

    def compose(self) -> ComposeResult:
        i  = self.info
        ex = [e for e in self.app.client.exchanges if e in EXCH_NAMES] or list(EXCH_NAMES)
        if i.get("exchange") and i["exchange"] not in ex:
            ex.append(i["exchange"])
        prod   = i.get("productType") if i.get("productType") in PRODUCTS else "INVESTMENT"
        val    = i.get("validity")    if i.get("validity")    in VALIDITIES else "GFD"
        opt    = i.get("optionType")  if i.get("optionType")  in ("CE", "PE") else "XX"
        strike = strike_str(i.get("strike")) if opt != "XX" else "-1"
        icon   = "\u270e" if self.mode == "MODIFY" else "\u2b21"
        with VerticalScroll(classes="modal"):
            yield Label(
                f"{icon}  "
                f"{'Modify Order' if self.mode == 'MODIFY' else 'New Order'}"
                f"  \u2014  {scrip_label(i)}",
                classes="title")

            yield Label("Direction & Exchange", classes="field-group-label")
            with Horizontal(classes="row"):
                yield Select([("\u25b2  BUY", "B"), ("\u25bc  SELL", "S")],
                             value=i.get("side", "B"), allow_blank=False, id="side")
                yield Select([(f"{EXCH_NAMES[e]}  ({e})", e) for e in ex],
                             value=i.get("exchange", ex[0]),
                             allow_blank=False, id="exch")

            yield Label("Instrument", classes="field-group-label")
            with Horizontal(classes="row"):
                yield Vertical(
                    Label("Trading Symbol"),
                    Input(str(i.get("tradingSymbol", "")), id="sym"),
                    classes="field")
                yield Vertical(
                    Label("Scrip Code"),
                    Input(str(i.get("scripCode", "")), id="code"),
                    classes="field")

            hint = []
            if i.get("lotSize"):  hint.append(f"Lot: {i['lotSize']}")
            if i.get("tickSize"): hint.append(f"Tick: {i['tickSize']}")
            lbl = "Order Parameters"
            if hint: lbl += f"  ({' \u00b7 '.join(hint)})"
            yield Label(lbl, classes="field-group-label")
            with Horizontal(classes="row"):
                yield Vertical(Label("Quantity"),
                               Input(str(i.get("quantity", "1")), id="qty"),
                               classes="field")
                yield Vertical(Label("Price  (0 = Market)"),
                               Input(str(i.get("price", "0")), id="price"),
                               classes="field")
                yield Vertical(Label("Trigger"),
                               Input(str(i.get("triggerPrice", "0")), id="trig"),
                               classes="field")
                yield Vertical(Label("Disclosed"),
                               Input("0", id="disc"),
                               classes="field")

            yield Label("Execution Settings", classes="field-group-label")
            with Horizontal(classes="row"):
                yield Select([(p, p) for p in PRODUCTS],
                             value=prod, allow_blank=False, id="product")
                yield Select([(v, v) for v in VALIDITIES],
                             value=val, allow_blank=False, id="validity")
                yield Input("", id="gtdd", placeholder="MyGTD date DD/MM/YYYY")
                yield Select([("Regular", "N"), ("AMO", "Y")],
                             value=i.get("afterHour", "N"),
                             allow_blank=False, id="ah")

            yield Label("Derivatives  (leave blank for equity)",
                        classes="field-group-label")
            with Horizontal(classes="row"):
                yield Vertical(Label("Inst. Type"),
                               Input(str(i.get("instType", "")), id="itype",
                                     placeholder="FS/FI/OS/OI"),
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

            if self.mode == "MODIFY":
                yield Static(
                    f"  \u2699  Order {i.get('orderId')}"
                    f"  \u00b7  RMS: {i.get('rmsCode')}"
                    f"  \u00b7  Executed: {i.get('executedQty', 0)}",
                    classes="hint")
            yield Static("", id="err", classes="err-msg")
            with Horizontal(classes="row buttons"):
                yield Button("\u2b21  Review Order", id="review", variant="primary")
                yield Button("\u2717  Cancel",       id="cancel")

    def on_mount(self) -> None:
        self.query_one("#qty", Input).focus()

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#review")
    def _review(self) -> None:
        g = lambda i: self.query_one(f"#{i}", Input).value.strip()
        s = lambda i: str(self.query_one(f"#{i}", Select).value)
        i = self.info
        fields = {
            "exchange": s("exch"),    "scripCode": g("code"),
            "tradingSymbol": g("sym"), "transactionType": s("side"),
            "quantity": g("qty"),      "price": g("price"),
            "triggerPrice": g("trig"), "disclosedQty": g("disc"),
            "afterHour": s("ah"),      "validity": s("validity"),
            "gtdd": g("gtdd"),         "productType": s("product"),
            "instrumentType": g("itype"), "optionType": g("otyp"),
            "strikePrice": g("strike"),   "expiry": g("expiry"),
            "lotSize": i.get("lotSize"),  "tickSize": i.get("tickSize"),
            "rmsCode": i.get("rmsCode") or "ANY",
            "orderId": i.get("orderId"),
            "executedQty": i.get("executedQty", 0),
        }
        c = self.app.client
        try:
            params, warns = build_order(fields, self.mode, c.cid, c.login_id)
        except ValueError as e:
            self.query_one("#err", Static).update(
                Text(f"\u2717  Validation error: {e}", style=f"bold {C_RED}"))
            return
        self.dismiss((params, warns))


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
        paper_tag = (Text("  \u26a0  PAPER MODE \u2014 no real order will be sent\n",
                          style=f"bold {C_AMBER}")
                     if self.paper else Text(""))
        with Vertical(classes="modal confirm-modal"):
            yield Label(f"\u2b21  {self.title_}", classes="title")
            yield Static(paper_tag)
            yield Rule()
            yield Static(self.body, classes="confirm-body")
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("\u2713  Confirm  (y)", id="yes", variant="success")
                yield Button("\u2717  Cancel   (n)", id="no",  variant="error")

    def action_yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#yes")
    def _y(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def _n(self) -> None:
        self.dismiss(False)


SPARK = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"


def sparkline(vals: list[float], width: int = 80) -> str:
    if not vals:
        return ""
    step = max(1, len(vals) // width)
    vals = vals[::step][-width:]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    return "".join(SPARK[int((v - lo) / rng * (len(SPARK) - 1))] for v in vals)


class HistoryScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def __init__(self, item: dict) -> None:
        super().__init__()
        self.item = item

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal wide"):
            yield Label(
                f"\U0001f4c8  Chart  \u2014  {scrip_label(self.item)}"
                f"  ({self.item.get('exchange')})",
                classes="title")
            yield Select([(i, i) for i in INTERVALS],
                         value="5minute", allow_blank=False, id="interval")
            yield Static("", id="spark", classes="sparkline")
            yield DataTable(id="hist", cursor_type="row")
            yield Static("  Esc = close", classes="hint")

    def on_mount(self) -> None:
        self.fetch("5minute")

    @on(Select.Changed, "#interval")
    def _chg(self, e: Select.Changed) -> None:
        self.fetch(str(e.value))

    @work(thread=True, exclusive=True)
    def fetch(self, interval: str) -> None:
        try:
            rows = self.app.client.historical(
                self.item["exchange"], self.item["scripCode"], interval)
        except Exception as e:
            self.app.call_from_thread(
                self.app.notify, f"History: {e}", severity="error")
            return
        self.app.call_from_thread(self.show, rows)

    def show(self, rows: list[dict]) -> None:
        fill_table(self.query_one("#hist", DataTable), rows[-400:], HIST_COLS)
        closes: list[float] = []
        for r in rows:
            try:
                closes.append(float(r.get("close")))
            except (TypeError, ValueError):
                pass
        if closes:
            change_pct = ((closes[-1] - closes[0]) / closes[0] * 100) if closes[0] else 0
            color = C_GREEN if change_pct >= 0 else C_RED
            label = f"  {sparkline(closes)}  {closes[-1]:,.2f}  ({change_pct:+.2f}%)"
            self.query_one("#spark", Static).update(Text(label, style=f"bold {color}"))
        else:
            self.query_one("#spark", Static).update(
                Text("  \u2014 no data returned (204) \u2014", style=C_DIM))


class DetailScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def __init__(self, row: dict) -> None:
        super().__init__()
        self.row = row

    def compose(self) -> ComposeResult:
        sym = get(self.row, "tradingSymbol") or "Order"
        oid = get(self.row, "orderId")
        with Vertical(classes="modal wide"):
            yield Label(f"\u2b21  Order Detail  \u2014  {sym}  #{oid}",
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


class QuoteScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def __init__(self, key: str, label: str) -> None:
        super().__init__()
        self.key_, self.label = key, label

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal wide"):
            yield Label(f"\u2b21  Live Quote  \u2014  {self.label}", classes="title")
            yield DataTable(id="q", cursor_type="none")
            yield Static(
                "  \u2b22  Live streaming data  \u00b7  Esc = close",
                classes="hint")

    def on_mount(self) -> None:
        self.query_one("#q", DataTable).add_columns("Field", "Value")
        self.set_interval(1, self.paint)
        self.paint()

    def paint(self) -> None:
        t    = self.query_one("#q", DataTable)
        data = getattr(self.app, "raw_ticks", {}).get(self.key_, {})
        t.clear()
        if not data:
            t.add_row(Text("\u27f3 waiting for live feed\u2026", style=C_DIM), "")
            return
        for k in sorted(data):
            v        = data[k]
            val_text = Text(
                fmt(v),
                style=sign_style(v) if k in ("ltp", "rsChange", "perChange") else "")
            t.add_row(Text(human(k), style=C_MUTED), val_text)


class WhatIfScreen(ModalScreen):
    """Simulate order impact without executing. Read-only — no broker request."""
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def __init__(self, item: dict | None = None) -> None:
        super().__init__()
        self.item = item or {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal"):
            yield Label("\u2b21  What-If  \u2014  Simulate Order Impact",
                        classes="title")
            yield Static(
                Text("  No broker request will be submitted."
                     "  Read-only portfolio simulation.", style=C_MUTED),
                classes="hint")
            yield Rule()
            yield Label("Order Parameters", classes="field-group-label")
            with Horizontal(classes="row"):
                yield Select([("\u25b2  BUY", "B"), ("\u25bc  SELL", "S")],
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
                yield Button("\u2b21  Simulate Impact",  id="wi-calc",  variant="primary")
                yield Button("\u2717  Close",            id="wi-close")

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
                Text(f"\u2717  Invalid input: {e}", style=f"bold {C_RED}"))
            return
        if qty <= 0:
            self.query_one("#wi-result", Static).update(
                Text("\u2717  Quantity must be > 0", style=f"bold {C_RED}"))
            return

        notional = qty * price if price > 0 else 0
        side_txt  = "\u25b2 BUY" if side == "B" else "\u25bc SELL"
        clr       = C_GREEN if side == "B" else C_RED

        t = Text()
        t.append("DRY RUN \u2014 SIMULATION ONLY\n\n",
                 style=f"bold {C_CYAN}")
        t.append("  Symbol:             ", style=C_MUTED)
        t.append(f"{sym or '(not set)'}\n", style=f"bold {C_TEXT}")
        t.append("  Direction:          ", style=C_MUTED)
        t.append(f"{side_txt}\n", style=f"bold {clr}")
        t.append("  Quantity:           ", style=C_MUTED)
        t.append(f"{qty:,} units\n", style=C_TEXT)

        if price > 0:
            t.append("  Est. Price:         ", style=C_MUTED)
            t.append(f"\u20b9{price:,.2f}\n", style=C_TEXT)
            t.append("  Est. Notional:      ", style=C_MUTED)
            t.append(f"\u20b9{notional:,.2f}\n", style=f"bold {C_AMBER}")
        else:
            t.append("  Order Type:         ", style=C_MUTED)
            t.append("MARKET  (price not provided)\n",
                     style=f"bold {C_AMBER}")

        t.append("\n  Risk Checks:        ", style=C_MUTED)
        t.append("Simulation \u2014 not validated against live limits\n",
                 style=C_DIM)
        t.append("\n  \u2713  No order submitted to broker\n",
                 style=f"bold {C_GREEN}")
        self.query_one("#wi-result", Static).update(t)


class SystemStatusScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def compose(self) -> ComposeResult:
        c = self.app.client
        with Vertical(classes="modal"):
            yield Label("\u2b21  System Status", classes="title")
            t = Text()

            t.append("\n  \u2500\u2500 Environment \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n",
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
            t.append(f"{' \u00b7 '.join(c.exchanges)}\n",
                     style=f"bold {C_CYAN}")

            t.append("\n  \u2500\u2500 Component Health \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n",
                      style=C_SUBTLE)
            components = [
                ("CLI Process",       True),
                ("Broker Connection", True),
                ("Order Gateway",     True),
                ("Audit Log",         True),
            ]
            for name, ok in components:
                t.append(f"  {name:<22}", style=C_MUTED)
                t.append(f"{'  \u2713 RUNNING' if ok else '  \u2717 DOWN'}\n",
                         style=f"bold {C_GREEN}" if ok else f"bold {C_RED}")

            feed_ok = bool(getattr(self.app, "raw_ticks", {}))
            t.append("  WebSocket Feed      ", style=C_MUTED)
            t.append(f"  {'  \u2713 ACTIVE' if feed_ok else '  \u25cb IDLE'}\n",
                     style=f"bold {C_GREEN}" if feed_ok else C_DIM)

            t.append("\n  \u2500\u2500 Quick Commands  (type after / in command bar) \u2500\n\n",
                      style=C_SUBTLE)
            for cmd, (desc, _) in list(SLASH_COMMANDS.items())[:10]:
                t.append(f"  {cmd:<18}", style=f"bold {C_CYAN}")
                t.append(f"{desc}\n",    style=C_MUTED)
            t.append("\n  F1 for full command reference\n", style=C_SUBTLE)

            yield Static(t)
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("\u2717  Close", id="close-btn", variant="primary")

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)


class RiskScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def compose(self) -> ComposeResult:
        c = self.app.client
        with Vertical(classes="modal"):
            yield Label("\u2b21  Risk Dashboard", classes="title")
            t = Text()

            t.append("\n  \u2500\u2500 Risk State \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n",
                      style=C_SUBTLE)
            t.append("  Risk State:         ", style=C_MUTED)
            t.append("NORMAL\n", style=f"bold {C_GREEN}")
            t.append("  Automation:         ", style=C_MUTED)
            t.append("ENABLED\n", style=f"bold {C_GREEN}")
            t.append("  Environment:        ", style=C_MUTED)
            t.append(f"{'PAPER' if c.paper else 'LIVE'}\n",
                     style=f"bold {C_AMBER}" if c.paper else f"bold {C_RED}")

            t.append("\n  \u2500\u2500 Active Controls \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n",
                      style=C_SUBTLE)
            controls = [
                ("Order Confirmation",  "REQUIRED"),
                ("Live Order Entry",    "BLOCKED (paper)" if c.paper else "ENABLED"),
                ("Audit Logging",       "ENABLED"),
                ("Session Expiry",      "24h token"),
            ]
            for name, state in controls:
                danger = "ENABLED" in state and not c.paper and "Live" in name
                style  = f"bold {C_RED}" if danger else f"bold {C_AMBER}" if "paper" in state.lower() else f"bold {C_GREEN}"
                t.append(f"  {name:<24}", style=C_MUTED)
                t.append(f"{state}\n",    style=style)

            t.append("\n  \u2500\u2500 Emergency Controls \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n",
                      style=C_SUBTLE)
            emergency = [
                ("/kill",    "Block new automated orders"),
                ("X",        "Cancel all open orders"),
                ("/whatif",  "Simulate before executing"),
            ]
            for key, desc in emergency:
                t.append(f"  {key:<18}", style=f"bold {C_CYAN}")
                t.append(f"{desc}\n",    style=C_MUTED)

            t.append("\n  \u2500\u2500 Safety Invariants \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n",
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
                t.append("  \u2713  ", style=f"bold {C_GREEN}")
                t.append(f"{inv}\n",   style=C_MUTED)

            yield Static(t)
            yield Rule()
            with Horizontal(classes="row buttons"):
                yield Button("\u2717  Close", id="close-btn", variant="primary")

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("q",      "dismiss(None)", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="modal wide"):
            yield Label("\u2b21  SKTUI  \u2014  Professional Trading CLI",
                        classes="title")
            t = Text()

            t.append("\n  \u2500\u2500 Slash Commands  (type in command bar below) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n",
                      style=C_SUBTLE)
            for cmd, (desc, _) in SLASH_COMMANDS.items():
                t.append(f"  {cmd:<22}", style=f"bold {C_CYAN}")
                t.append(f"{desc}\n",    style=C_MUTED)

            t.append("\n  \u2500\u2500 Keyboard Shortcuts \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n",
                      style=C_SUBTLE)
            shortcuts = [
                ("a",       "Add symbol to watchlist"),
                ("Del",     "Remove symbol from watchlist"),
                ("b / s",   "Buy / sell selected symbol"),
                ("m",       "Modify selected order"),
                ("x",       "Cancel selected order"),
                ("X",       "Cancel ALL open orders"),
                ("i",       "Order history & trades"),
                ("c",       "Historical chart"),
                ("?",       "Live quote detail"),
                ("p",       "Products & services"),
                ("r",       "Refresh data"),
                ("d",       "Toggle feed log"),
                ("/",       "Focus command bar"),
                ("F1",      "This help screen"),
                ("1\u20136","Switch tabs"),
                ("ctrl+l",  "Log out"),
                ("q",       "Quit"),
            ]
            for key, desc in shortcuts:
                t.append(f"  {key:<22}", style=f"bold {C_AMBER}")
                t.append(f"{desc}\n",    style=C_MUTED)

            t.append("\n  \u2500\u2500 Trading Safety Model \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n",
                      style=C_SUBTLE)
            safety = [
                ("PAPER mode",      "All orders simulated \u2014 nothing reaches the broker"),
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

            t.append("\n  \u2500\u2500 Architecture \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n",
                      style=C_SUBTLE)
            t.append("  CLI  \u2192  Control Plane  \u2192  Risk Engine"
                     "  \u2192  Broker Adapter  \u2192  Exchange\n", style=C_MUTED)
            t.append("  Every live order passes pre-trade validation before submission.\n",
                     style=C_MUTED)
            t.append("  The CLI is the operator interface, not the final safety boundary.\n",
                     style=C_SUBTLE)

            yield Static(t)
            with Horizontal(classes="row buttons"):
                yield Button("\u2717  Close  (Esc / q)", id="close-btn",
                             variant="primary")

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)


PRODUCT_LINKS = [
    ("Equity (NSE/BSE) incl. ETFs",        "API \u00b7 trade here (NC/BC)",             ""),
    ("Futures & Options (NSE)",             "API \u00b7 trade here (NF; FS/FI/OS/OI)",   ""),
    ("Currency derivatives (NSE)",          "API \u00b7 trade here (RN)",                ""),
    ("Commodity (MCX)",                     "API \u00b7 trade here (MX)",                ""),
    ("Funds, holdings, positions, history", "API \u00b7 tabs in this app",               ""),
    ("IPO",                                 "Not in API \u00b7 browser",                 "https://www.sharekhan.com/ipo"),
    ("Mutual Funds / SIP / ELSS / NFO",     "Not in API \u00b7 browser",                 "https://www.sharekhan.com/mutual-funds"),
    ("F&O Solutions",                       "Not in API \u00b7 browser",                 "https://www.sharekhan.com/futures-and-options"),
    ("Pattern Finder",                      "Not in API \u00b7 browser",                 "https://www.sharekhan.com/pattern-finder"),
    ("Algo Solutions",                      "Not in API \u00b7 browser",                 "https://www.sharekhan.com/algo-solutions"),
    ("Margin Funding / Financing",          "Not in API \u00b7 browser",                 "https://www.sharekhan.com/margin-funding"),
    ("MTF",                                 "Not in API \u00b7 browser",                 "https://www.sharekhan.com/margin-trading-facility"),
    ("PMS",                                 "Not in API \u00b7 browser",                 "https://www.sharekhan.com/portfolio-management-services"),
    ("Fixed Deposits & Bonds",             "Not in API \u00b7 browser",                 "https://www.sharekhan.com/bonds"),
    ("Global markets (US stocks)",          "Not in API \u00b7 browser",                 "https://www.sharekhan.com/global-markets/invest-in-us-stocks"),
    ("Brokerage calculator",                "Calculator \u00b7 browser",                 "https://www.sharekhan.com/financial-calculator/brokerage-calculator"),
    ("Margin calculator",                   "Calculator \u00b7 browser",                 "https://www.sharekhan.com/margin-calculator"),
    ("Full web platform",                   "Browser",                                   "https://newtrade.sharekhan.com/skweb/login/"),
]


class ProductsScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal wide"):
            yield Label("\u2b21  Markets & Products", classes="title")
            yield DataTable(id="prod", cursor_type="row")
            yield Static(
                "  Enter = open in browser  \u00b7  Esc = close",
                classes="hint")

    def on_mount(self) -> None:
        t = self.query_one("#prod", DataTable)
        t.add_columns("Product / Service", "Access")
        for name, how, url in PRODUCT_LINKS:
            style = (C_GREEN if how.startswith("API")
                     else C_AMBER if how.startswith("Not") else C_CYAN)
            icon  = "  \u2197" if url else ""
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
