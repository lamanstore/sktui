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
