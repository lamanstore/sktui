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
    bars_count: int = 60,
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

    # Deterministic base price from scrip_code if base_price not provided
    if base_price is None or base_price <= 0:
        base_price = 150.0 + (code_num % 1800)

    now = datetime.now()
    step_minutes = 5
    iv_lower = interval.lower()
    if "1min" in iv_lower:
        step_minutes = 1
    elif "3min" in iv_lower:
        step_minutes = 3
    elif "10min" in iv_lower:
        step_minutes = 10
    elif "15min" in iv_lower:
        step_minutes = 15
    elif "30min" in iv_lower:
        step_minutes = 30
    elif "60min" in iv_lower or "1h" in iv_lower:
        step_minutes = 60
    elif "daily" in iv_lower or "1d" in iv_lower:
        step_minutes = 1440
    elif "week" in iv_lower:
        step_minutes = 1440 * 7
    elif "month" in iv_lower:
        step_minutes = 1440 * 30

    rows: list[dict] = []
    rng = random.Random(code_num + step_minutes)

    current_p = float(base_price)
    start_time = now - timedelta(minutes=step_minutes * bars_count)

    for i in range(bars_count):
        bar_time = start_time + timedelta(minutes=step_minutes * i)
        volat = current_p * rng.uniform(0.002, 0.012)
        drift = rng.uniform(-volat, volat)
        o = current_p
        c = max(1.0, round(o + drift, 2))
        h = round(max(o, c) + rng.uniform(0.05, max(0.1, volat * 0.8)), 2)
        l = max(0.5, round(min(o, c) - rng.uniform(0.05, max(0.1, volat * 0.8)), 2))
        v = int(rng.uniform(1000, 50000))

        rows.append({
            "tradeDate": bar_time.strftime("%d/%m/%Y"),
            "tradeTime": bar_time.strftime("%H:%M:%S"),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
            "exchange": exchange,
            "scripCode": code_num,
        })
        current_p = c

    return rows
