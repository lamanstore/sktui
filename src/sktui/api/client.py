"""Sharekhan REST client — data fetching and order submission."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

BASE = "https://api.sharekhan.com/skapi"


class ApiError(Exception):
    def __init__(self, status: Any, message: str, kind: str = ""):
        self.status, self.message, self.kind = status, message, kind
        super().__init__(f"[{status}] {message}" + (f" ({kind})" if kind else ""))


def _unwrap(resp: requests.Response) -> Any:
    """Apply the documented response contract and return `data`."""
    if resp.status_code == 204 or not resp.content:
        return []
    try:
        j = resp.json()
    except ValueError:
        raise ApiError(resp.status_code, resp.text[:200] or "non-JSON response")
    if isinstance(j, dict):
        st = j.get("status", resp.status_code)
        if resp.status_code >= 400 or (isinstance(st, int) and st >= 400):
            raise ApiError(st, str(j.get("message", "")), str(j.get("errorType", "")))
        if st == 204:
            return []
        return j.get("data", j)
    if resp.status_code >= 400:
        raise ApiError(resp.status_code, str(j)[:200])
    return j


def as_rows(data: Any) -> list[dict]:
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


class Client:
    """Sharekhan REST API client.

    Handles all HTTP communication with api.sharekhan.com, including the
    paper-trading simulation path (paper=True) which mirrors live responses
    in memory without touching the real API.
    """

    def __init__(
        self,
        api_key: str,
        access_token: str,
        customer_id: str,
        login_id: str = "",
        vendor_key: str = "",
        exchanges: list[str] | None = None,
        full_name: str = "",
        paper: bool = False,
    ):
        self.api_key, self.access_token = api_key, access_token
        self.customer_id = str(customer_id)
        self.login_id = login_id or self.customer_id
        self.vendor_key, self.full_name = vendor_key, full_name
        self.exchanges = exchanges or []
        self.paper = paper
        # Paper trading state — see paper_trading.py for mutation logic
        self._paper_orders: list[dict] = []
        self._paper_orders_by_id: dict[str, dict] = {}
        self._paper_positions: list[dict] = []
        self._paper_positions_by_key: dict[tuple[str, str], dict] = {}
        self._paper_holdings: list[dict] = []
        self._paper_holdings_by_sym: dict[str, dict] = {}
        self._paper_counter: int = 1001
        self.s = requests.Session()
        self.s.headers.update(
            {
                "Content-Type": "application/json",
                "access-token": access_token,
                "api-key": api_key,
            }
        )
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

    # ── Reports ───────────────────────────────────────────────────────────────
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
        return as_rows(
            self._req("GET", f"/services/limitstmt/{exchange}/{self.customer_id}")
        )

    def order_history(self, exchange: str, order_id: Any) -> list[dict]:
        return as_rows(
            self._req(
                "GET",
                f"/services/reports/{exchange}/{self.customer_id}/{order_id}",
            )
        )

    def order_trades(self, exchange: str, order_id: Any) -> list[dict]:
        return as_rows(
            self._req(
                "GET",
                f"/services/reports/{exchange}/{self.customer_id}/{order_id}/trades",
            )
        )

    def historical(self, exchange: str, scrip_code: Any, interval: str) -> list[dict]:
        return as_rows(
            self._req(
                "GET",
                f"/services/historical/{exchange}/{scrip_code}/{interval}",
                timeout=30,
            )
        )

    def master(self, exchange: str) -> list[dict]:
        return as_rows(
            self._req("GET", f"/services/master/{exchange}", timeout=90)
        )

    # ── Orders ────────────────────────────────────────────────────────────────
    def submit(self, params: dict) -> dict:
        """Submit a new or modify order.

        In paper mode the order is simulated in memory by paper_trading logic.
        In live mode the order is posted to the REST API.
        """
        if self.paper:
            from sktui.api.paper_trading import simulate_submit
            return simulate_submit(self, params)

        data = self._req("POST", "/services/orders", params)
        if isinstance(data, dict) and data.get("errormsg"):
            raise ApiError("order", str(data["errormsg"]))
        return data if isinstance(data, dict) else {"data": data}

    def cancel_by_id(self, order_id: Any) -> dict:
        if self.paper:
            oid_str = str(order_id)
            o = self._paper_orders_by_id.get(oid_str)
            if o is not None:
                o["orderStatus"] = "Cancelled"
                o["requestStatus"] = "CANCELLED"
            else:
                for o in self._paper_orders:
                    if str(o.get("orderId")) == oid_str:
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
