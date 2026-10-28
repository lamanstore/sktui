"""Paper-trading helpers separated from the raw API client."""
from __future__ import annotations

from typing import Any


class PaperTradingMixin:
    """Small, reusable mixin for the paper-trading order ledger."""

    @staticmethod
    def _paper_position_key(sym: str, exch: str) -> str:
        return f"{exch}:{sym}"

    def apply_paper_order(self, params: dict) -> dict:
        self._paper_counter += 1
        order_id = f"POP-{self._paper_counter}"
        side = str(params.get("transactionType", "B")).upper()
        qty = int(params.get("quantity") or 1)
        sym = str(params.get("tradingSymbol", "SCRIP"))
        exch = str(params.get("exchange", "NC"))
        prod = str(params.get("productType", "INVESTMENT"))
        price = str(params.get("price") or "0")

        p_order = {
            "orderId": order_id,
            "scripCode": params.get("scripCode"),
            "tradingSymbol": sym,
            "exchange": exch,
            "buySell": side,
            "orderQty": qty,
            "execQty": qty,
            "orderPrice": price,
            "execPrice": price if float(price) > 0 else "LTP",
            "orderStatus": "Fully Executed",
            "requestStatus": "SUCCESS",
            "priceType": params.get("orderType", "NORMAL"),
            "lastModTime": __import__("datetime").datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "rmsCode": "PAPER",
            "productType": prod,
        }
        self._paper_orders.insert(0, p_order)

        key = self._paper_position_key(sym, exch)
        pos = next((p for p in self._paper_positions if self._paper_position_key(str(p.get("tradingSymbol", "")), str(p.get("exchange", ""))) == key), None)
        if not pos:
            pos = {
                "tradingSymbol": sym,
                "scripCode": params.get("scripCode"),
                "exchange": exch,
                "productType": prod,
                "buyQty": 0, "buyRate": 0.0,
                "sellQty": 0, "sellRate": 0.0,
                "netQty": 0, "avgPrice": 0.0,
                "bpl": 0.0, "mtm": 0.0,
            }
            self._paper_positions.append(pos)

        px = float(price) if float(price) > 0 else 100.0
        if side == "B":
            old_bqty = int(pos["buyQty"])
            new_bqty = old_bqty + qty
            pos["buyRate"] = round(((old_bqty * float(pos["buyRate"])) + (qty * px)) / new_bqty, 2)
            pos["buyQty"] = new_bqty
        else:
            old_sqty = int(pos["sellQty"])
            new_sqty = old_sqty + qty
            pos["sellRate"] = round(((old_sqty * float(pos["sellRate"])) + (qty * px)) / new_sqty, 2)
            pos["sellQty"] = new_sqty

        pos["netQty"] = int(pos["buyQty"]) - int(pos["sellQty"])
        pos["avgPrice"] = pos["buyRate"] if pos["netQty"] > 0 else pos["sellRate"]

        if prod in ("INVESTMENT", "CNC") and side == "B":
            h = next((h for h in self._paper_holdings if h.get("tradingSymbol") == sym), None)
            if not h:
                h = {
                    "tradingSymbol": sym,
                    "exchange": exch,
                    "scripCode": params.get("scripCode"),
                    "aval": qty,
                    "cncqty": qty,
                    "invstQty": qty,
                    "holdPrice": px,
                    "dp": 0, "pledge": 0, "mf": 0, "receivable": 0,
                    "tradingAllowed": "Y",
                }
                self._paper_holdings.append(h)
            else:
                h["aval"] = int(h["aval"]) + qty
                h["cncqty"] = int(h["cncqty"]) + qty
                h["invstQty"] = int(h["invstQty"]) + qty

        return {"paper": True, "sent": True, "orderId": order_id, "data": p_order}
