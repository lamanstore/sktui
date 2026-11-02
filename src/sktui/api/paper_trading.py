"""Paper trading simulation — in-memory order/position/holdings updates.

This module is called by Client.submit() when paper=True.  Keeping it
separate means the REST client stays thin and all paper-mode bookkeeping
can be read and tested in one place.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sktui.api.client import Client


def simulate_submit(client: "Client", params: dict) -> dict:
    """Simulate order execution and update paper positions/holdings in-place."""
    order_id = f"POP-{client._paper_counter}"
    client._paper_counter += 1
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    price = str(params.get("price") or "0")
    side  = str(params.get("transactionType", "B")).upper()
    qty   = int(params.get("quantity") or 1)
    sym   = str(params.get("tradingSymbol", "SCRIP"))
    exch  = str(params.get("exchange", "NC"))
    prod  = str(params.get("productType", "INVESTMENT"))

    p_order = {
        "orderId":       order_id,
        "scripCode":     params.get("scripCode"),
        "tradingSymbol": sym,
        "exchange":      exch,
        "buySell":       side,
        "orderQty":      qty,
        "execQty":       qty,
        "orderPrice":    price,
        "execPrice":     price if float(price) > 0 else "LTP",
        "orderStatus":   "Fully Executed",
        "requestStatus": "SUCCESS",
        "priceType":     params.get("orderType", "NORMAL"),
        "lastModTime":   now_str,
        "rmsCode":       "PAPER",
        "productType":   prod,
    }
    client._paper_orders.insert(0, p_order)
    if hasattr(client, "_paper_orders_by_id"):
        client._paper_orders_by_id[str(order_id)] = p_order

    # ── Update paper position (O(1) lookup with list fallback) ────────────────
    pos_key = (sym, exch)
    pos = (
        client._paper_positions_by_key.get(pos_key)
        if hasattr(client, "_paper_positions_by_key")
        else None
    )
    if not pos:
        pos = next(
            (p for p in client._paper_positions
             if p.get("tradingSymbol") == sym and p.get("exchange") == exch),
            None,
        )
    if not pos:
        pos = {
            "tradingSymbol": sym,
            "scripCode":     params.get("scripCode"),
            "exchange":      exch,
            "productType":   prod,
            "buyQty":        0, "buyRate":  0.0,
            "sellQty":       0, "sellRate": 0.0,
            "netQty":        0, "avgPrice": 0.0,
            "bpl":           0.0, "mtm":   0.0,
        }
        client._paper_positions.append(pos)
        if hasattr(client, "_paper_positions_by_key"):
            client._paper_positions_by_key[pos_key] = pos

    px = float(price) if float(price) > 0 else 100.0
    if side == "B":
        old_bqty = int(pos["buyQty"])
        new_bqty = old_bqty + qty
        pos["buyRate"] = round(
            ((old_bqty * float(pos["buyRate"])) + (qty * px)) / new_bqty, 2
        )
        pos["buyQty"] = new_bqty
    else:
        old_sqty = int(pos["sellQty"])
        new_sqty = old_sqty + qty
        pos["sellRate"] = round(
            ((old_sqty * float(pos["sellRate"])) + (qty * px)) / new_sqty, 2
        )
        pos["sellQty"] = new_sqty

    pos["netQty"]  = int(pos["buyQty"]) - int(pos["sellQty"])
    pos["avgPrice"] = pos["buyRate"] if pos["netQty"] > 0 else pos["sellRate"]

    # ── Realistic paper margin deduction / release (Phase A) ──────────────────
    is_deriv = exch.upper() not in ("NC", "BC")
    margin_rate = 0.15 if is_deriv else (0.20 if prod.upper() in ("BIGTRADE", "BIGTRADE+", "MIS", "INTRADAY") else 1.00)
    margin_delta = round(qty * px * margin_rate, 2)
    if hasattr(client, "_paper_cash_balance") and hasattr(client, "_paper_margin_used"):
        if side == "B" or (is_deriv and pos["netQty"] != 0):
            client._paper_cash_balance = max(0.0, round(client._paper_cash_balance - margin_delta, 2))
            client._paper_margin_used = round(client._paper_margin_used + margin_delta, 2)
        else:
            # Selling / reducing exposure releases margin
            client._paper_cash_balance = round(client._paper_cash_balance + margin_delta, 2)
            client._paper_margin_used = max(0.0, round(client._paper_margin_used - margin_delta, 2))

    # ── Update paper holdings for INVESTMENT / CNC buys (O(1) lookup) ─────────
    if prod in ("INVESTMENT", "CNC") and side == "B":
        h = (
            client._paper_holdings_by_sym.get(sym)
            if hasattr(client, "_paper_holdings_by_sym")
            else None
        )
        if not h:
            h = next(
                (h for h in client._paper_holdings if h.get("tradingSymbol") == sym), None
            )
        if not h:
            h = {
                "tradingSymbol": sym,
                "exchange":      exch,
                "scripCode":     params.get("scripCode"),
                "aval":          qty,
                "cncqty":        qty,
                "invstQty":      qty,
                "holdPrice":     px,
                "dp":            0, "pledge": 0, "mf": 0, "receivable": 0,
                "tradingAllowed": "Y",
            }
            client._paper_holdings.append(h)
            if hasattr(client, "_paper_holdings_by_sym"):
                client._paper_holdings_by_sym[sym] = h
        else:
            h["aval"]     = int(h["aval"])     + qty
            h["cncqty"]   = int(h["cncqty"])   + qty
            h["invstQty"] = int(h["invstQty"]) + qty

    return {"paper": True, "sent": True, "orderId": order_id, "data": p_order}


def generate_paper_history(
    exchange: str = "NC",
    scrip_code: Any = 2475,
    interval: str = "5minute",
    bars_count: int = 80,
    base_price: float | None = None,
) -> list[dict]:
    """Generate realistic OHLCV historical candlestick data for paper/offline chart rendering."""
    import random
    from datetime import datetime, timedelta

    code_num = 2475
    try:
        code_num = int(scrip_code) if scrip_code is not None else 2475
    except Exception:
        code_num = sum(ord(c) for c in str(scrip_code)) if scrip_code else 2475

    explicit_anchor = base_price is not None and base_price > 0
    if not explicit_anchor:
        from sktui.config import KNOWN_BASE_PRICES
        from sktui.utils import resolve_symbol
        sym = resolve_symbol(scrip_code, exchange=exchange)
        if sym in KNOWN_BASE_PRICES:
            base_price = KNOWN_BASE_PRICES[sym]
        elif str(exchange).upper() == "RN" or any(k in str(sym) for k in ("USD", "EUR", "JPY", "GBP")):
            base_price = 84.40 if "USD" in str(sym) else (1.08 if "EUR" in str(sym) else (0.55 if "JPY" in str(sym) else 1.0))
        else:
            base_price = 100.0

    now = datetime.now()
    iv_lower = interval.lower()
    step_seconds = 300
    if iv_lower in ("tick", "1second", "1s"):
        step_seconds = 1
    elif iv_lower in ("5second", "5s"):
        step_seconds = 5
    elif iv_lower in ("15second", "15s"):
        step_seconds = 15
    elif iv_lower in ("30second", "30s"):
        step_seconds = 30
    elif "1min" in iv_lower:
        step_seconds = 60
    elif "3min" in iv_lower:
        step_seconds = 180
    elif "10min" in iv_lower:
        step_seconds = 600
    elif "15min" in iv_lower:
        step_seconds = 900
    elif "30min" in iv_lower:
        step_seconds = 1800
    elif "60min" in iv_lower or "1h" in iv_lower:
        step_seconds = 3600
    elif "90min" in iv_lower:
        step_seconds = 5400
    elif "daily" in iv_lower or "1d" in iv_lower:
        step_seconds = 86400
    elif "week" in iv_lower:
        step_seconds = 86400 * 7
    elif "month" in iv_lower:
        step_seconds = 86400 * 30

    rows: list[dict] = []
    rng = random.Random(code_num + step_seconds)

    # Scale per-bar volatility realistically by square-root of time step
    volat_scale = 0.0012 if step_seconds <= 30 else (0.004 if step_seconds <= 900 else 0.01)
    current_p = float(base_price)
    aligned_now = datetime.fromtimestamp(int(now.timestamp() // max(1, step_seconds)) * max(1, step_seconds))
    start_time = aligned_now - timedelta(seconds=step_seconds * max(0, bars_count - 1))

    raw_bars: list[tuple[datetime, float, float, float, float, int]] = []
    for i in range(bars_count):
        bar_time = start_time + timedelta(seconds=step_seconds * i)
        volat = max(0.05, current_p * rng.uniform(volat_scale * 0.35, volat_scale))
        drift = rng.uniform(-volat, volat)
        o = current_p
        c = max(1.0, round(o + drift, 2))
        h = round(max(o, c) + rng.uniform(0.02, max(0.05, volat * 0.7)), 2)
        l = max(0.5, round(min(o, c) - rng.uniform(0.02, max(0.05, volat * 0.7)), 2))
        v = int(rng.uniform(120, 4500) if step_seconds <= 30 else rng.uniform(1000, 50000))
        raw_bars.append((bar_time, o, h, l, c, v))
        current_p = c

    # If caller provided an explicit live anchor price, shift series so latest close aligns smoothly
    shift = (float(base_price) - raw_bars[-1][4]) if (explicit_anchor and raw_bars) else 0.0
    for bar_time, o, h, l, c, v in raw_bars:
        so = max(0.5, round(o + shift, 2))
        sc = max(0.5, round(c + shift, 2))
        sh = max(so, sc, round(h + shift, 2))
        sl = max(0.25, min(so, sc, round(l + shift, 2)))
        rows.append({
            "tradeDate": bar_time.strftime("%d/%m/%Y"),
            "tradeTime": bar_time.strftime("%H:%M:%S"),
            "open": so,
            "high": sh,
            "low": sl,
            "close": sc,
            "volume": v,
            "exchange": exchange,
            "scripCode": code_num,
        })

    return rows
