#!/usr/bin/env python3
"""SKTUI - Professional Terminal Trading CLI for Mirae Asset Sharekhan API."""
from __future__ import annotations

import argparse
import json
import os
import time
import webbrowser
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button, Checkbox, DataTable, Footer, Header, Input, Label,
    RichLog, Rule, Select, Static, TabbedContent, TabPane,
)

from sktui import api

# ── Design tokens ──────────────────────────────────────────────────────────────
C_CYAN   = "#00f0ff"
C_GREEN  = "#10b981"
C_RED    = "#ef4444"
C_AMBER  = "#f59e0b"
C_DIM    = "#71717a"
C_PANEL  = "#18181b"
C_BG     = "#09090b"
C_BORDER = "#1a1a20"
C_TEXT   = "#e4e4e7"
C_MUTED  = "#a1a1aa"
C_SUBTLE = "#52525b"

# ── Storage paths ──────────────────────────────────────────────────────────────
CONF         = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "sktui"
DATA         = Path(os.environ.get("XDG_DATA_HOME",   Path.home() / ".local/share")) / "sktui"
CONFIG_FILE  = CONF / "config.json"
SESSION_FILE = DATA / "session.json"
WATCH_FILE   = CONF / "watchlist.json"

EXCH_NAMES = {"NC": "NSE Equity", "BC": "BSE Equity", "NF": "NSE F&O",
              "RN": "NSE Currency", "MX": "MCX"}
CASH       = ("NC", "BC")
PRODUCTS   = ["INVESTMENT", "BIGTRADE", "BIGTRADE+"]
VALIDITIES = ["GFD", "MyGTD", "IOC"]
INTERVALS  = ["1minute", "3minute", "5minute", "10minute", "15minute", "30minute",
              "60minute", "90minute", "daily", "weekly", "monthly",
              "quarterly", "halfyearly", "yearly"]

# ── Slash command registry ─────────────────────────────────────────────────────
SLASH_COMMANDS: dict[str, tuple[str, str]] = {
    "/dashboard":  ("Open portfolio + market overview",       "tab:watch"),
    "/watchlist":  ("Manage watchlist symbols",               "tab:watch"),
    "/orders":     ("View and manage orders",                 "tab:orders"),
    "/positions":  ("View open positions",                    "tab:positions"),
    "/holdings":   ("View holdings",                          "tab:holdings"),
    "/funds":      ("View funds & margin",                    "tab:funds"),
    "/activity":   ("View activity & audit log",              "tab:activity"),
    "/buy":        ("Prepare a BUY order (select symbol first)", "trade:B"),
    "/sell":       ("Prepare a SELL order (select symbol first)", "trade:S"),
    "/cancel":     ("Cancel selected open order",             "cancel_order"),
    "/modify":     ("Modify selected order",                  "modify"),
    "/chart":      ("Open price chart for selected symbol",   "chart"),
    "/quote":      ("Live quote for selected symbol",         "quote"),
    "/products":   ("Browse markets & product links",         "products"),
    "/whatif":     ("Simulate order impact (read-only)",      "whatif"),
    "/risk":       ("Risk dashboard & safety controls",       "risk"),
    "/status":     ("System & broker health status",          "status"),
    "/help":       ("Full command reference & key bindings",  "help"),
    "/feed":       ("Toggle live WebSocket feed log",         "toggle_log"),
    "/refresh":    ("Refresh all account data",               "refresh_all"),
    "/kill":       ("EMERGENCY: block new automated orders",  "kill"),
    "/logout":     ("Log out and clear session",              "logout"),
}

# ── Helpers ────────────────────────────────────────────────────────────────────
def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_private(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd  = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def get(d: dict, *names: str, default: Any = "") -> Any:
    low = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        v = low.get(n.lower())
        if v is not None and v != "":
            return v
    return default


def fmt(v: Any) -> str:
    if v is None:
        return "\u2014"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int) and abs(v) >= 10000:
        return f"{v:,}"
    s = str(v)
    return s if s else "\u2014"


def human(k: str) -> str:
    out = ""
    for i, c in enumerate(str(k)):
        out += (" " + c) if c.isupper() and i and not str(k)[i - 1].isupper() else c
    return out[:1].upper() + out[1:]


def sign_style(v: Any) -> str:
    try:
        x = float(str(v).replace(",", ""))
    except ValueError:
        return ""
    return f"bold {C_GREEN}" if x > 0 else f"bold {C_RED}" if x < 0 else C_DIM


def cell(key: str, v: Any) -> Text:
    s = fmt(v)
    k = key.lower()
    style = ""
    if k in ("buysell", "transactiontype"):
        style = (f"bold {C_GREEN}" if s.upper().startswith("B")
                 else f"bold {C_RED}"  if s.upper().startswith("S") else "")
    elif k == "orderstatus":
        sl = s.lower()
        if "fully"  in sl:                            style = f"bold {C_GREEN}"
        elif "reject" in sl or "cancel" in sl or "fail" in sl:
                                                       style = f"bold {C_RED}"
        else:                                          style = f"bold {C_AMBER}"
    elif k in ("bpl", "mtm", "netqty", "rschange", "perchange", "chg", "pct"):
        style = sign_style(v)
    return Text(s, style=style)


def fill_table(t: DataTable, rows: list[dict],
               cols: list[tuple[str, str]] | None = None) -> None:
    t.clear(columns=True)
    if not rows:
        return
    present: list[tuple[str, str]] = []
    if cols:
        lowkeys = {str(k).lower() for r in rows for k in r}
        present = [(k, lab) for k, lab in cols if k.lower() in lowkeys]
    if not present:
        keys: list[str] = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        present = [(k, human(k)) for k in keys[:14]]
    for k, lab in present:
        t.add_column(lab, key=k)
    for r in rows:
        t.add_row(*[cell(k, get(r, k, default=None)) for k, _ in present])


def norm_expiry(v: Any) -> str:
    if not v:
        return ""
    s = str(v).strip()
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d%b%Y",
              "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
              "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(s, f).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return s


def expiry_key(v: Any) -> tuple:
    try:
        return (0, datetime.strptime(norm_expiry(v), "%d/%m/%Y"))
    except ValueError:
        return (1, datetime.max)


def strike_str(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "-1"
    return str(int(x)) if x.is_integer() else str(x)


def normalize_scrip(exchange: str, r: dict) -> dict:
    opt  = str(get(r, "optionType", default="")).upper()
    inst = str(get(r, "instType",   default="")).upper()
    return {
        "exchange":      exchange,
        "scripCode":     get(r, "scripCode",     default=None),
        "tradingSymbol": get(r, "tradingSymbol", default=""),
        "companyName":   get(r, "companyName",   default=""),
        "instType":      inst,
        "lotSize":       get(r, "lotSize",        default=0),
        "tickSize":      get(r, "tickSize",       default=0),
        "expiry":        norm_expiry(get(r, "expiry", default="")),
        "strike":        get(r, "strike",         default=0),
        "optionType":    opt,
    }


def scrip_label(i: dict) -> str:
    s = str(i.get("tradingSymbol", ""))
    if i.get("exchange") not in CASH and i.get("expiry"):
        s += f" {i['expiry']}"
        if i.get("optionType") in ("CE", "PE"):
            s += f" {strike_str(i.get('strike'))} {i['optionType']}"
        else:
            s += " FUT"
    return s


def dec(v: Any) -> Decimal:
    try:
        return Decimal(str(v).strip() or "0")
    except InvalidOperation:
        raise ValueError(f"'{v}' is not a number")


def build_order(f: dict, mode: str, customer_id: Any,
                login_id: str) -> tuple[dict, list[str]]:
    warns: list[str] = []
    exch = f["exchange"].strip().upper()
    if exch not in EXCH_NAMES:
        raise ValueError(f"exchange must be one of {', '.join(EXCH_NAMES)}")
    try:
        code = int(f["scripCode"])
    except (TypeError, ValueError):
        raise ValueError("scrip code must be an integer")
    try:
        qty = int(f["quantity"])
    except (TypeError, ValueError):
        raise ValueError("quantity must be an integer")
    if qty <= 0:
        raise ValueError("quantity must be > 0")
    price = dec(f.get("price") or "0")
    trig  = dec(f.get("triggerPrice") or "0")
    if price < 0 or trig < 0:
        raise ValueError("price / trigger cannot be negative")
    p: dict[str, Any] = {
        "customerId":      customer_id,
        "scripCode":       code,
        "tradingSymbol":   f["tradingSymbol"].strip(),
        "exchange":        exch,
        "transactionType": f["transactionType"],
        "quantity":        qty,
        "disclosedQty":    int(f.get("disclosedQty") or 0),
        "price":           str(price),
        "triggerPrice":    str(trig),
        "rmsCode":         f.get("rmsCode") or "ANY",
        "afterHour":       f.get("afterHour") or "N",
        "orderType":       "NORMAL",
        "channelUser":     login_id,
        "validity":        f.get("validity") or "GFD",
        "requestType":     mode,
        "productType":     f.get("productType") or "INVESTMENT",
    }
    if not p["tradingSymbol"]:
        raise ValueError("trading symbol is required")
    if p["validity"] == "MyGTD":
        if not f.get("gtdd"):
            raise ValueError("MyGTD validity needs a date (DD/MM/YYYY)")
        p["gtdd"] = norm_expiry(f["gtdd"])
    if mode != "NEW":
        if not f.get("orderId"):
            raise ValueError("order id missing")
        p["orderId"]     = str(f["orderId"])
        p["executedQty"] = int(f.get("executedQty") or 0)
        if p["rmsCode"] == "ANY":
            warns.append("Modify/cancel should carry the order's own RMS code (it is still 'ANY')")
    if exch not in CASH:
        if not f.get("expiry") or not f.get("instrumentType"):
            raise ValueError("derivatives need instrument type and expiry")
        opt = (f.get("optionType") or "XX").upper()
        p.update({
            "instrumentType": f["instrumentType"].strip().upper(),
            "optionType":     opt,
            "strikePrice":    "-1" if opt == "XX" else (f.get("strikePrice") or "-1"),
            "expiry":         norm_expiry(f["expiry"]),
        })
    try:
        lot = int(float(f.get("lotSize") or 0))
        if lot > 1 and qty % lot:
            warns.append(f"Quantity {qty} is not a multiple of lot size {lot}")
    except ValueError:
        pass
    try:
        tick = Decimal(str(f.get("tickSize") or 0))
        if tick > 0 and price > 0 and (price / tick) % 1 != 0:
            warns.append(f"Price {price} may not be a multiple of tick size {tick}")
    except InvalidOperation:
        pass
    if price == 0:
        warns.append("Price 0 = MARKET order")
    return p, warns


def order_summary(p: dict, warns: list[str] | None = None) -> Text:
    side = {"B": "BUY", "S": "SELL"}.get(
        p.get("transactionType", ""), p.get("transactionType", ""))
    t = Text()
    t.append(f"{p['requestType']}  ", style=f"bold {C_CYAN}")
    t.append(f"{side} ",  style=f"bold {C_GREEN}" if side == "BUY" else f"bold {C_RED}")
    t.append(f"{p['quantity']} \u00d7 {p['tradingSymbol']} ({p['exchange']})\n")
    t.append(f"price {p['price']}  trigger {p['triggerPrice']}"
             f"  {p['productType']}  {p['validity']}")
    if p.get("instrumentType"):
        t.append(f"\n{p['instrumentType']} {p.get('expiry')}"
                 f" {p.get('optionType')} strike {p.get('strikePrice')}")
    if p.get("orderId"):
        t.append(f"\norder id {p['orderId']}  rms {p['rmsCode']}")
    if p.get("afterHour") == "Y":
        t.append("\nAFTER-MARKET ORDER", style=f"bold {C_AMBER}")
    for w in warns or []:
        t.append(f"\n\u26a0 {w}", style=f"bold {C_AMBER}")
    return t


def is_open_order(row: dict) -> bool:
    s = str(get(row, "orderStatus", default="")).lower()
    return not any(x in s for x in ("fully", "cancel", "reject", "expire", "fail"))


# ── Login screen ───────────────────────────────────────────────────────────────
LOGIN_LOGO = """\
 \u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557
 \u2551   \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\u2588\u2588\u2557  \u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\u2588\u2588\u2557   \u2588\u2588\u2557 \u2551
 \u2551   \u2588\u2588\u2554\u2550\u2550\u2550\u2550\u255d\u2588\u2588\u2551 \u2588\u2588\u2554\u255d\u255a\u2550\u2550\u2588\u2588\u2554\u2550\u2550\u255d\u2588\u2588\u2551   \u2588\u2588\u2551 \u2551
 \u2551   \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2588\u2554\u255d    \u2588\u2588\u2551   \u2588\u2588\u2551   \u2588\u2588\u2551 \u2551
 \u2551   \u255a\u2550\u2550\u2550\u2550\u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2588\u2588\u2557    \u2588\u2588\u2551   \u2588\u2588\u2551   \u2588\u2588\u2551 \u2551
 \u2551   \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551\u2588\u2588\u2551  \u2588\u2588\u2557   \u2588\u2588\u2551   \u255a\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d \u2551
 \u2551   \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u255d\u255a\u2550\u255d  \u255a\u2550\u255d   \u255a\u2550\u255d    \u255a\u2550\u2550\u2550\u2550\u2550\u255d  \u2551
 \u2560\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2563
 \u2551    Mirae Asset Sharekhan Terminal    \u2551
 \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d"""


class LoginScreen(Screen):
    def compose(self) -> ComposeResult:
        with VerticalScroll(id="login-scroll"):
            with Vertical(id="login"):
                yield Static(LOGIN_LOGO, id="login-logo")
                yield Rule()
                yield Label(
                    "\u2500\u2500\u2500 CREDENTIALS \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
                    classes="section-label")
                yield Input(placeholder="API Key", id="api_key")
                yield Input(placeholder="Secret Key  (32 chars)",
                            password=True, id="secret")
                yield Input(placeholder="Vendor Key  (partners only, leave blank otherwise)",
                            id="vendor")
                yield Select(
                    [("v1005  (Base64-URL \u2014 recommended)", "1005"),
                     ("No version  (Base64)", "")],
                    value="1005", allow_blank=False, id="ver",
                )
                yield Rule()
                yield Label(
                    "\u2500\u2500\u2500 AUTH FLOW \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
                    classes="section-label")
                yield Button(
                    "\u2b21  Step 1 \u00b7 Open Login Page in Browser",
                    id="geturl", classes="btn-step")
                yield Static("", id="url", classes="url-display")
                yield Input(
                    placeholder="Step 2 \u00b7 Paste request token or full redirect URL",
                    id="reqtok")
                yield Rule()
                yield Checkbox(" \U0001f512  Remember credentials on this machine",
                               id="remember")
                yield Button(
                    "\u2b22  Connect to Sharekhan",
                    id="go", variant="primary", classes="btn-connect")
                yield Static("", id="msg", classes="login-msg")

    def on_mount(self) -> None:
        cfg, env = read_json(CONFIG_FILE, {}), os.environ
        self.query_one("#api_key",  Input).value  = (env.get("SK_API_KEY")    or cfg.get("api_key", ""))
        self.query_one("#secret",   Input).value  = (env.get("SK_SECRET_KEY") or cfg.get("secret", ""))
        self.query_one("#vendor",   Input).value  = (env.get("SK_VENDOR_KEY") or cfg.get("vendor", ""))
        self.query_one("#ver",      Select).value = env.get("SK_VERSION_ID", cfg.get("version", "1005"))
        self.query_one("#remember", Checkbox).value = bool(cfg)
        s   = read_json(SESSION_FILE, {})
        exp = api.jwt_exp(s.get("access_token", "")) if s else None
        if s and ((exp and exp > time.time() + 120)
                  or (not exp and s.get("date") == str(date.today()))):
            self.msg("\u26a1 Resuming saved session\u2026")
            self.finish(s)

    def msg(self, text: str, error: bool = False) -> None:
        style  = f"bold {C_RED}"   if error else f"bold {C_GREEN}"
        prefix = "\u2717 "         if error else "\u2713 "
        self.query_one("#msg", Static).update(Text(prefix + text, style=style))

    def fields(self) -> dict:
        g = lambda i: self.query_one(f"#{i}", Input).value.strip()
        return {
            "api_key": g("api_key"), "secret": g("secret"),
            "vendor":  g("vendor"),  "reqtok": g("reqtok"),
            "version": str(self.query_one("#ver", Select).value or ""),
        }

    @on(Button.Pressed, "#geturl")
    def _geturl(self) -> None:
        f = self.fields()
        if not f["api_key"]:
            return self.msg("API key is required", True)
        url = api.login_url(f["api_key"], f["vendor"], f["version"])
        self.query_one("#url", Static).update(Text(url, style=C_DIM))
        try:
            webbrowser.open(url)
        except Exception:
            pass
        self.msg("Browser opened \u2014 log in, then paste the request token below.")

    @on(Button.Pressed, "#go")
    def _go(self) -> None:
        f = self.fields()
        if not all([f["api_key"], f["secret"], f["reqtok"]]):
            return self.msg("API key, secret, and request token are all required", True)
        self.msg("\u27f3  Authenticating \u2014 please wait\u2026")
        self.authenticate(f)

    @work(thread=True)
    def authenticate(self, f: dict) -> None:
        try:
            d = api.fetch_access_token(
                f["api_key"], f["secret"], f["reqtok"], f["vendor"], f["version"])
        except Exception as e:
            self.app.call_from_thread(self.msg, f"Authentication failed: {e}", True)
            return
        sess = {
            "date":         str(date.today()),
            "api_key":      f["api_key"],
            "vendor":       f["vendor"],
            "access_token": d["token"],
            "customer_id":  str(d.get("customerId", "")),
            "login_id":     str(d.get("loginId", "")),
            "exchanges":    d.get("exchanges", []),
            "full_name":    d.get("fullName", ""),
        }
        self.app.call_from_thread(self.after_auth, f, sess)

    def after_auth(self, f: dict, sess: dict) -> None:
        if self.query_one("#remember", Checkbox).value:
            write_private(CONFIG_FILE, {
                "api_key": f["api_key"], "secret": f["secret"],
                "vendor":  f["vendor"],  "version": f["version"],
            })
        write_private(SESSION_FILE, sess)
        self.finish(sess)

    def finish(self, s: dict) -> None:
        self.app.client = api.Client(
            s["api_key"], s["access_token"], s["customer_id"],
            s.get("login_id", ""), s.get("vendor", ""),
            s.get("exchanges", []), s.get("full_name", ""), self.app.paper,
        )
        self.app.switch_screen(MainScreen())


# ── SymbolSearch ───────────────────────────────────────────────────────────────
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

    @work(thread=True, exclusive=True)
    def load_master(self, exch: str) -> None:
        self.app.call_from_thread(
            self.query_one("#state", Static).update,
            f"\u27f3  Loading {exch} scrip master\u2026")
        cache = DATA / f"master_{exch}_{date.today()}.json"
        rows  = read_json(cache, None)
        if rows is None:
            try:
                rows = self.app.client.master(exch)
                write_private(cache, rows)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Scrip master: {e}", severity="error")
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
        self.app.call_from_thread(self.set_index, exch, idx)

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


# ── OrderTicket ────────────────────────────────────────────────────────────────
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


# ── Confirm ────────────────────────────────────────────────────────────────────
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


# ── Sparkline & chart ──────────────────────────────────────────────────────────
SPARK = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"


def sparkline(vals: list[float], width: int = 80) -> str:
    if not vals:
        return ""
    step = max(1, len(vals) // width)
    vals = vals[::step][-width:]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    return "".join(SPARK[int((v - lo) / rng * (len(SPARK) - 1))] for v in vals)


HIST_COLS = [
    ("tradeDate", "Date"), ("tradeTime", "Time"),
    ("open", "Open"), ("high", "High"), ("low", "Low"),
    ("close", "Close"), ("qty", "Qty"), ("tradedValue", "Value"),
]


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


# ── DetailScreen ───────────────────────────────────────────────────────────────
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


# ── QuoteScreen ────────────────────────────────────────────────────────────────
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


# ── WhatIfScreen ───────────────────────────────────────────────────────────────
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


# ── SystemStatusScreen ─────────────────────────────────────────────────────────
class SystemStatusScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss(None)", "Close")]

    def compose(self) -> ComposeResult:
        c = self.app.client
        with Vertical(classes="modal"):
            yield Label("\u2b21  System Status", classes="title")
            t = Text()

            # Environment
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

            # Component health
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

            # Command reference (top 10)
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


# ── RiskScreen ─────────────────────────────────────────────────────────────────
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


# ── HelpScreen ─────────────────────────────────────────────────────────────────
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


# ── Products ───────────────────────────────────────────────────────────────────
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


# ── NavSidebar widget ──────────────────────────────────────────────────────────
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
TABS = ["watch", "orders", "positions", "holdings", "funds", "activity"]


# ── MainScreen ─────────────────────────────────────────────────────────────────
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

    # ── layout ────────────────────────────────────────────────────────────────
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

    # ── mount ─────────────────────────────────────────────────────────────────
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

    # ── helpers ───────────────────────────────────────────────────────────────
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

    # ── command bar ───────────────────────────────────────────────────────────
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

    # ── data loading ──────────────────────────────────────────────────────────
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

    # ── actions ───────────────────────────────────────────────────────────────
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

    # ── live feed ─────────────────────────────────────────────────────────────
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


# ── CSS ────────────────────────────────────────────────────────────────────────
CSS = """
/* ─── Base ──────────────────────────────────────────────────────── */
Screen { background: #09090b; color: #e4e4e7; }

/* ─── Header & Footer ───────────────────────────────────────────── */
Header { background: #0c0c0f; color: #00f0ff; text-style: bold;
         border-bottom: tall #1a1a20; height: 3; }
Header > .header--title     { color: #00f0ff; text-style: bold; }
Header > .header--sub-title { color: #52525b; }
Footer { background: #0c0c0f; color: #52525b; border-top: solid #1a1a20; }
Footer > .footer--key { color: #00f0ff; text-style: bold; }

/* ─── Account bar ───────────────────────────────────────────────── */
#account { height: 3; padding: 0 2; background: #111115;
           border-bottom: solid #1a1a20; content-align: left middle; }

/* ─── Main body ─────────────────────────────────────────────────── */
#main-body { height: 1fr; }

/* ─── Sidebar ───────────────────────────────────────────────────── */
#sidebar { width: 22; background: #0c0c0f;
           border-right: solid #1a1a20; }
#nav     { width: 22; height: 1fr; background: #0c0c0f; padding: 1 0; }
.nav-section-header { color: #3f3f46; text-style: bold;
                      padding: 1 2 0 2; }
.nav-item        { color: #52525b; padding: 0 2; }
.nav-safety      { color: #7f1d1d; }

/* ─── Content area ──────────────────────────────────────────────── */
#content-area { width: 1fr; }

/* ─── Tabs ──────────────────────────────────────────────────────── */
TabbedContent { height: 1fr; margin: 0; }
TabbedContent > ContentSwitcher { border: none; }
TabPane { padding: 0; }
Tabs { border-bottom: solid #1a1a20; background: #0c0c0f; }
Tab { color: #3f3f46; padding: 1 3; }
Tab.-active { color: #00f0ff; text-style: bold;
              border-bottom: tall #00f0ff; background: #111115; }

/* ─── DataTable ─────────────────────────────────────────────────── */
DataTable { height: 1fr; border: none; background: #09090b; }
DataTable > .datatable--header    { background: #0c0c0f; color: #00f0ff;
                                    text-style: bold; }
DataTable > .datatable--cursor    { background: #0f2030; color: #e4e4e7;
                                    text-style: bold; }
DataTable > .datatable--hover     { background: #111115; }
DataTable > .datatable--even-row  { background: #0b0b0e; }

/* ─── Command bar ───────────────────────────────────────────────── */
#cmd-bar    { height: 3; background: #0c0c0f; border-top: solid #1a1a20; }
#cmd-prefix { color: #00f0ff; text-style: bold; content-align: center middle;
              height: 3; width: 5; background: #111115;
              border-right: solid #1a1a20; }
#cmd-input  { background: #0c0c0f; border: none; color: #71717a; height: 3; }
#cmd-input:focus { border: none; background: #111115; color: #e4e4e7; }

/* ─── Status bar ────────────────────────────────────────────────── */
#status { height: 3; padding: 0 2; dock: bottom; background: #09090b;
          border-top: solid #1a1a20; color: #52525b;
          content-align: left middle; }

/* ─── Feed / activity logs ──────────────────────────────────────── */
#feedlog      { height: 10; border-top: tall #00f0ff; background: #09090b;
                color: #10b981; padding: 0 1; }
#activity-log { color: #71717a; padding: 0 1; height: 1fr; }

/* ─── Modals ────────────────────────────────────────────────────── */
ModalScreen { align: center middle; }
.modal { width: 110; max-width: 100%; height: auto; max-height: 92%;
         background: #0e0e12; border: tall #00f0ff; padding: 2 4; }
.modal.wide   { width: 148; height: 88%; }
.confirm-modal { width: 80; height: auto; }
.whatif-result { padding: 1 0; }

/* ─── Modal internals ───────────────────────────────────────────── */
.title { text-style: bold; color: #00f0ff; margin-bottom: 1;
         border-bottom: solid #1a1a20; padding-bottom: 1; }
.field-group-label { color: #52525b; text-style: italic; margin: 1 0 0 0; }
.section-label     { color: #52525b; text-style: italic; margin-bottom: 0; }
.confirm-body      { padding: 1 0; }
.row               { height: auto; margin-bottom: 1; }
.row > Input, .row > Select { width: 1fr; margin-right: 1; }
.field             { width: 1fr; height: auto; }
.field > Label     { color: #52525b; margin-bottom: 0; }
.buttons           { margin-top: 2; align: right middle; }
.buttons > Button  { margin-left: 2; min-width: 20; }
.sparkline         { padding: 0 1; height: 3; content-align: center middle; }
.err-msg           { color: #ef4444; margin-top: 1; }
.url-display       { color: #52525b; text-style: italic;
                     padding: 0 1; margin-bottom: 1; }
.login-msg         { margin-top: 1; padding: 0 1; height: 3; }
.hint              { color: #52525b; text-style: italic; margin-top: 1; }

/* ─── Inputs & Selects ──────────────────────────────────────────── */
Input  { background: #18181b; border: solid #27272a; color: #e4e4e7; }
Input:focus { border: tall #00f0ff; }
Select { background: #18181b; border: solid #27272a; }
Select:focus { border: tall #00f0ff; }
Checkbox { color: #a1a1aa; }

/* ─── Buttons ───────────────────────────────────────────────────── */
Button { border: solid #27272a; min-width: 14; }
Button.-primary { background: #0b3a4d; color: #00f0ff;
                  text-style: bold; border: solid #00f0ff; }
Button.-success { background: #052e22; color: #10b981; border: solid #10b981; }
Button.-error   { background: #3a0808; color: #ef4444; border: solid #ef4444; }
.btn-step    { background: #111115; color: #71717a;
               border: solid #27272a; width: 100%; }
.btn-connect { background: #0b3a4d; color: #00f0ff; text-style: bold;
               border: solid #00f0ff; width: 100%; }

/* ─── Rule ──────────────────────────────────────────────────────── */
Rule { color: #1a1a20; margin: 1 0; }

/* ─── Login ─────────────────────────────────────────────────────── */
#login-scroll { align: center middle; background: #09090b; }
#login { width: 82; max-width: 100%; height: auto; margin: 1 2;
         padding: 2 4; border: tall #00f0ff; background: #0e0e12; }
#login-logo { color: #00f0ff; text-align: center;
              text-style: bold; margin-bottom: 0; }
#login Input, #login Select { margin-bottom: 1; width: 100%; }
"""


# ── App ────────────────────────────────────────────────────────────────────────
class SKApp(App):
    TITLE     = "SKTUI  \u00b7  Sharekhan Terminal"
    SUB_TITLE = "Mirae Asset  \u00b7  Professional Trading CLI"
    CSS       = CSS

    def __init__(self, paper: bool = False) -> None:
        super().__init__()
        self.paper       = paper
        self.client:     api.Client | None = None
        self.raw_ticks:  dict[str, dict]   = {}
        self.enable_feed = True

    def on_mount(self) -> None:
        self.push_screen(LoginScreen())


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SKTUI \u2014 professional terminal trading CLI for Mirae Asset Sharekhan")
    ap.add_argument("--paper", action="store_true",
                    help="dry-run: never send or cancel orders")
    args = ap.parse_args()
    SKApp(paper=args.paper or os.environ.get("SKTUI_PAPER") == "1").run()


if __name__ == "__main__":
    main()
