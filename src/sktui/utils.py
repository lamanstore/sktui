"""Utility functions, order builders, data formatting, and file I/O for SKTUI."""
from __future__ import annotations

import json
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests
from rich.text import Text
from textual.widgets import DataTable

from sktui.config import (
    C_AMBER, C_CYAN, C_DIM, C_GREEN, C_RED, CASH, EXCH_NAMES,
)


def get_public_ip() -> str:
    """Fetch machine public IP address for Sharekhan whitelisting diagnostics."""
    endpoints = [
        "https://api.ipify.org?format=json",
        "https://ifconfig.me/ip",
        "https://api.myip.com",
    ]
    for url in endpoints:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                if "json" in r.headers.get("Content-Type", "").lower():
                    ip = str(r.json().get("ip", "")).strip()
                    if ip:
                        return ip
                s = r.text.strip()
                if s and ("." in s or ":" in s):
                    return s
        except Exception:
            pass
    return "Unavailable"


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
        if "fully" in sl:
            style = f"bold {C_GREEN}"
        elif "reject" in sl or "cancel" in sl or "fail" in sl:
            style = f"bold {C_RED}"
        else:
            style = f"bold {C_AMBER}"
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


def default_tick_size(exch: str) -> Decimal:
    e = str(exch).upper()
    if e == "RN":
        return Decimal("0.0025")
    elif e == "MX":
        return Decimal("0.1")
    return Decimal("0.05")


def round_to_tick(val: Decimal, tick: Decimal) -> Decimal:
    if val <= 0 or tick <= 0:
        return val
    try:
        steps = (val / tick).quantize(Decimal("1"), rounding="ROUND_HALF_UP")
        return steps * tick
    except Exception:
        return val


def build_order(f: dict, mode: str, customer_id: Any,
                login_id: str) -> tuple[dict, list[str]]:
    warns: list[str] = []
    exch = f["exchange"].strip().upper()
    if exch not in EXCH_NAMES:
        raise ValueError(f"exchange must be one of {', '.join(EXCH_NAMES)}")
    try:
        code = int(f["scripCode"])
    except (TypeError, ValueError):
        raise ValueError("scrip code must be an integer (select a valid instrument)")
    try:
        qty = int(f["quantity"])
    except (TypeError, ValueError):
        raise ValueError("quantity must be an integer")
    if qty <= 0:
        raise ValueError("quantity must be > 0")
    price = dec(f.get("price") or "0")
    trig  = dec(f.get("triggerPrice") or "0")
    target_price = dec(f.get("targetPrice") or "0")
    trailing_sl  = dec(f.get("trailingSl") or "0")
    order_type   = str(f.get("orderType") or "NORMAL").upper()

    if price < 0 or trig < 0 or target_price < 0 or trailing_sl < 0:
        raise ValueError("price / trigger / target cannot be negative")

    # ── Auto-round prices to exact tick size boundary to prevent API errors ──
    try:
        raw_tick = Decimal(str(f.get("tickSize") or 0))
        tick = raw_tick if raw_tick > 0 else default_tick_size(exch)
    except Exception:
        tick = default_tick_size(exch)

    if price > 0:
        price = round_to_tick(price, tick)
    if trig > 0:
        trig = round_to_tick(trig, tick)
    if target_price > 0:
        target_price = round_to_tick(target_price, tick)
    if trailing_sl > 0:
        trailing_sl = round_to_tick(trailing_sl, tick)

    dec_places = 4 if exch == "RN" else 2
    fmt_str = f"{{:.{dec_places}f}}"

    p: dict[str, Any] = {
        "customerId":      customer_id,
        "scripCode":       code,
        "tradingSymbol":   f["tradingSymbol"].strip(),
        "exchange":        exch,
        "transactionType": f["transactionType"],
        "quantity":        qty,
        "disclosedQty":    int(f.get("disclosedQty") or 0),
        "price":           fmt_str.format(price) if price > 0 else "0",
        "triggerPrice":    fmt_str.format(trig) if trig > 0 else "0",
        "targetPrice":     fmt_str.format(target_price) if target_price > 0 else "0",
        "trailingSl":      fmt_str.format(trailing_sl) if trailing_sl > 0 else "0",
        "rmsCode":         f.get("rmsCode") or "ANY",
        "afterHour":       f.get("afterHour") or "N",
        "orderType":       order_type,
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

    # Stop-loss validation & warning
    if order_type in ("SL", "SL-M") or trig > 0:
        if trig <= 0:
            raise ValueError("Stop-Loss (SL / SL-M) order requires Trigger Price > 0")
        warns.append(f"🛑 STOP LOSS ORDER — Triggers at ₹{trig}")
    if target_price > 0:
        warns.append(f"🎯 TARGET / TAKE PROFIT — Target set at ₹{target_price}")

    if price == 0 and order_type != "SL-M":
        warns.append("Price 0 = MARKET order")
    return p, warns


def order_summary(p: dict, warns: list[str] | None = None) -> Text:
    side = {"B": "BUY", "S": "SELL"}.get(
        p.get("transactionType", ""), p.get("transactionType", ""))
    t = Text()
    t.append(f"{p['requestType']}  ", style=f"bold {C_CYAN}")
    t.append(f"{side} ",  style=f"bold {C_GREEN}" if side == "BUY" else f"bold {C_RED}")
    t.append(f"{p['quantity']} × {p['tradingSymbol']} ({p['exchange']})\n")
    ord_t = p.get("orderType", "NORMAL")
    if ord_t != "NORMAL":
        t.append(f"Type: {ord_t}  ", style=f"bold {C_AMBER}")
    t.append(f"price {p['price']}  trigger {p['triggerPrice']}"
             f"  {p['productType']}  {p['validity']}")
    if float(p.get("targetPrice") or 0) > 0:
        t.append(f"\n🎯 Target Price: ₹{p['targetPrice']}", style=f"bold {C_GREEN}")
    if p.get("instrumentType"):
        t.append(f"\n{p['instrumentType']} {p.get('expiry')}"
                 f" {p.get('optionType')} strike {p.get('strikePrice')}")
    if p.get("orderId"):
        t.append(f"\norder id {p['orderId']}  rms {p['rmsCode']}")
    if p.get("afterHour") == "Y":
        t.append("\nAFTER-MARKET ORDER", style=f"bold {C_AMBER}")
    for w in warns or []:
        t.append(f"\n⚠ {w}", style=f"bold {C_AMBER}")
    return t


def is_open_order(row: dict) -> bool:
    s = str(get(row, "orderStatus", default="")).lower()
    return not any(x in s for x in ("fully", "cancel", "reject", "expire", "fail"))
