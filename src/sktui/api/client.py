"""REST client for Sharekhan accounts, reports, and paper-trading flows."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from .auth import ApiError, _unwrap

BASE = "https://api.sharekhan.com/skapi"


def as_rows(data: Any) -> list[dict]:
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


class Client:
    def __init__(self, api_key: str, access_token: str, customer_id: str, login_id: str = "",
                 vendor_key: str = "", exchanges: list[str] | None = None, full_name: str = "",
                 paper: bool = False):
        self.api_key, self.access_token = api_key, access_token
        self.customer_id = str(customer_id)
        self.login_id = login_id or self.customer_id
        self.vendor_key, self.full_name = vendor_key, full_name
        self.exchanges = exchanges or []
        self.paper = paper
        self._paper_orders: list[dict] = []
        self._paper_positions: list[dict] = []
        self._paper_holdings: list[dict] = []
        self._paper_counter: int = 1001
        self.s = requests.Session()
        self.s.headers.update({"Content-Type": "application/json",
                               "access-token": access_token, "api-key": api_key})
        if vendor_key:
            self.s.headers["vendor-key"] = vendor_key

    @property
    def cid(self) -> Any:
        return int(self.customer_id) if self.customer_id.isdigit() else self.customer_id

    def _req(self, method: str, path: str, body: Any = None, timeout: int = 20) -> Any:
        try:
            r = self.s.request(method, BASE + path, json=body, timeout=timeout)
        except requests.RequestException as e:
            raise ApiError("network", str(e))
        return _unwrap(r)

    def orders(self) -> list[dict]:
        if self.paper:
            return self._paper_orders
        try:
            return as_rows(self._req("GET", f"/services/reports/{self.customer_id}"))
        except Exception:
            return self._paper_orders

    def positions(self) -> list[dict]:
        if self.paper:
            return self._paper_positions
        try:
            return as_rows(self._req("GET", f"/services/trades/{self.customer_id}"))
        except Exception:
            return self._paper_positions

    def holdings(self) -> list[dict]:
        if self.paper:
            return self._paper_holdings
        try:
            return as_rows(self._req("GET", f"/services/holdings/{self.customer_id}"))
        except Exception:
            return self._paper_holdings

    def funds(self, exchange: str) -> list[dict]:
        return as_rows(self._req("GET", f"/services/limitstmt/{exchange}/{self.customer_id}"))

    def order_history(self, exchange: str, order_id: Any) -> list[dict]:
        return as_rows(self._req("GET", f"/services/reports/{exchange}/{self.customer_id}/{order_id}"))

    def order_trades(self, exchange: str, order_id: Any) -> list[dict]:
        return as_rows(self._req("GET", f"/services/reports/{exchange}/{self.customer_id}/{order_id}/trades"))

    def historical(self, exchange: str, scrip_code: Any, interval: str) -> list[dict]:
        return as_rows(self._req("GET", f"/services/historical/{exchange}/{scrip_code}/{interval}", timeout=30))

    def master(self, exchange: str) -> list[dict]:
        return as_rows(self._req("GET", f"/services/master/{exchange}", timeout=90))

    def submit(self, params: dict) -> dict:
        if self.paper:
            order_id = f"POP-{self._paper_counter}"
            self._paper_counter += 1
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            price = str(params.get("price") or "0")
            side = str(params.get("transactionType", "B")).upper()
            qty = int(params.get("quantity") or 1)
            sym = str(params.get("tradingSymbol", "SCRIP"))
            exch = str(params.get("exchange", "NC"))
            prod = str(params.get("productType", "INVESTMENT"))

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
                "lastModTime": now_str,
                "rmsCode": "PAPER",
                "productType": prod,
            }
            self._paper_orders.insert(0, p_order)

            pos = next((p for p in self._paper_positions if p.get("tradingSymbol") == sym and p.get("exchange") == exch), None)
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

        data = self._req("POST", "/services/orders", params)
        if isinstance(data, dict) and data.get("errormsg"):
            raise ApiError("order", str(data["errormsg"]))
        return data if isinstance(data, dict) else {"data": data}

    def cancel_by_id(self, order_id: Any) -> dict:
        if self.paper:
            for o in self._paper_orders:
                if str(o.get("orderId")) == str(order_id):
                    o["orderStatus"] = "Cancelled"
                    o["requestStatus"] = "CANCELLED"
                    break
            return {"paper": True, "sent": True, "cancel": order_id}
        data = self._req("GET", f"/services/cancelOrder/{order_id}")
        return data if isinstance(data, dict) else {"data": data}

    def logout(self) -> None:
        try:
            self._req("GET", f"/services/logout/{self.customer_id}", timeout=8)
        except Exception:
            pass
