"""Sharekhan REST + websocket client, implemented from the official API documentation.

Endpoints  : https://api.sharekhan.com/skapi/...
Websocket  : wss://stream.sharekhan.com/skstream/api/stream
Login      : request token is AES-256-GCM encrypted with the *secret key*; the
             "RequestId|CustomerId" halves must be swapped and re-encrypted.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
from typing import Any, Callable
from urllib.parse import unquote, urlencode

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

BASE = "https://api.sharekhan.com/skapi"
WS_URL = "wss://stream.sharekhan.com/skstream/api/stream"
IV = bytes(16)  # docs: base64 "AAAAAAAAAAAAAAAAAAAAAA==" == 16 zero bytes
DEFAULT_VERSION = "1005"  # 1005 => Base64-URL encoding; empty => plain Base64


class ApiError(Exception):
    def __init__(self, status: Any, message: str, kind: str = ""):
        self.status, self.message, self.kind = status, message, kind
        super().__init__(f"[{status}] {message}" + (f" ({kind})" if kind else ""))


# --------------------------------------------------------------------------- #
# login crypto
# --------------------------------------------------------------------------- #
def _b64enc(data: bytes, urlsafe: bool) -> str:
    return (base64.urlsafe_b64encode if urlsafe else base64.b64encode)(data).decode()


def _b64dec(s: str, urlsafe: bool) -> bytes:
    s = s.strip()
    s += "=" * (-len(s) % 4)
    return (base64.urlsafe_b64decode if urlsafe else base64.b64decode)(s)


def clean_request_token(raw: str) -> str:
    """Accept the bare token or the whole redirect URL; undo URL mangling."""
    raw = raw.strip()
    m = re.search(r"request_token=([^&#\s]+)", raw)
    if m:
        raw = m.group(1)
    return unquote(raw).replace(" ", "+")


def _aes(secret_key: str) -> AESGCM:
    key = secret_key.encode("utf-8")
    if len(key) != 32:
        raise ValueError(f"Secret key must be exactly 32 characters (got {len(key)})")
    return AESGCM(key)


def encrypt_str(plain: str, secret_key: str, versioned: bool = True) -> str:
    return _b64enc(_aes(secret_key).encrypt(IV, plain.encode(), None), versioned)


def decrypt_str(token: str, secret_key: str, versioned: bool = True) -> str:
    raw = _aes(secret_key).decrypt(IV, _b64dec(token, versioned), None)
    return raw.decode("utf-8").strip("\r\n\0")


def swap_request_token(request_token: str, secret_key: str, versioned: bool = True) -> str:
    """'RequestId|CustomerId' -> 'CustomerId|RequestId', re-encrypted."""
    plain = decrypt_str(clean_request_token(request_token), secret_key, versioned)
    if "|" not in plain:
        raise ValueError("Request token did not decrypt to 'RequestId|CustomerId' - wrong secret key or version?")
    req_id, cust_id = plain.split("|", 1)
    return encrypt_str(f"{cust_id}|{req_id}", secret_key, versioned)


def login_url(api_key: str, vendor_key: str = "", version_id: str = DEFAULT_VERSION,
              state: str = "12345") -> str:
    q = {"api_key": api_key}
    if vendor_key:
        q["vendor_key"] = vendor_key
    q["state"] = state
    if version_id:
        q["version_id"] = version_id
    return f"{BASE}/auth/login.html?{urlencode(q)}"


def jwt_exp(token: str) -> int | None:
    try:
        p = token.split(".")[1]
        p += "=" * (-len(p) % 4)
        return int(json.loads(base64.urlsafe_b64decode(p))["exp"])
    except Exception:
        return None


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


def fetch_access_token(api_key: str, secret_key: str, request_token: str, vendor_key: str = "",
                       version_id: str = DEFAULT_VERSION, state: int = 12345) -> dict:
    """Step 3+4 of the documented login. Returns data: token, customerId, loginId, exchanges, fullName."""
    versioned = bool(version_id)
    body: dict[str, Any] = {
        "apiKey": api_key,
        "requestToken": swap_request_token(request_token, secret_key, versioned),
        "state": state,
    }
    if vendor_key:
        body["vendorKey"] = vendor_key
    if versioned:
        body["versionId"] = int(version_id)
    r = requests.post(f"{BASE}/services/access/token", json=body, timeout=20)
    data = _unwrap(r)
    if not isinstance(data, dict) or not data.get("token"):
        raise ApiError(r.status_code, f"No token in login response: {str(data)[:200]}")
    return data


# --------------------------------------------------------------------------- #
# REST client
# --------------------------------------------------------------------------- #
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

    # reports
    def orders(self) -> list[dict]:
        return as_rows(self._req("GET", f"/services/reports/{self.customer_id}"))

    def positions(self) -> list[dict]:
        return as_rows(self._req("GET", f"/services/trades/{self.customer_id}"))

    def holdings(self) -> list[dict]:
        return as_rows(self._req("GET", f"/services/holdings/{self.customer_id}"))

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

    # orders
    def submit(self, params: dict) -> dict:
        if self.paper:
            return {"paper": True, "sent": False, "params": params}
        data = self._req("POST", "/services/orders", params)
        if isinstance(data, dict) and data.get("errormsg"):
            raise ApiError("order", str(data["errormsg"]))
        return data if isinstance(data, dict) else {"data": data}

    def cancel_by_id(self, order_id: Any) -> dict:
        if self.paper:
            return {"paper": True, "sent": False, "cancel": order_id}
        data = self._req("GET", f"/services/cancelOrder/{order_id}")
        return data if isinstance(data, dict) else {"data": data}

    def logout(self) -> None:
        try:
            self._req("GET", f"/services/logout/{self.customer_id}", timeout=8)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# websocket feed
# --------------------------------------------------------------------------- #
class Feed:
    """Streams quotes ("full" mode) and order acknowledgements.

    Protocol (per docs): connect -> server says message=="connect" -> send subscribe
    {feed, ack} -> on message=="subscribe" send the ack request and one feed request
    per scrip key such as "NC2885".
    """

    def __init__(self, access_token: str, api_key: str, customer_id: Any,
                 keys: Callable[[], list[str]], on_message: Callable[[dict], None],
                 on_status: Callable[[str, bool], None]):
        self.access_token, self.api_key, self.customer_id = access_token, api_key, customer_id
        self.keys, self.on_message, self.on_status = keys, on_message, on_status
        self.ws = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.ready = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

    def send(self, obj: dict) -> None:
        if self.ws and self.ready:
            self.ws.send(json.dumps(obj))

    def subscribe(self, key: str, mode: str = "full") -> None:
        self.send({"action": "feed", "key": [mode], "value": [key]})

    def unsubscribe(self, key: str) -> None:
        self.send({"action": "unsubscribe", "key": ["feed"], "value": [key]})

    def _run(self) -> None:
        import websocket  # websocket-client
        backoff = 2
        url = f"{WS_URL}?ACCESS_TOKEN={self.access_token}&API_KEY={self.api_key}"
        while not self._stop.is_set():
            self.ready = False
            self.ws = websocket.WebSocketApp(
                url,
                on_open=lambda w: self.on_status("Feed: socket open", False),
                on_message=self._on_msg,
                on_error=lambda w, e: self.on_status(f"Feed error: {e}", True),
                on_close=lambda w, c, m: self.on_status("Feed: disconnected", False),
            )
            started = time.time()
            try:
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                self.on_status(f"Feed crashed: {e}", True)
            if self._stop.is_set():
                break
            if time.time() - started > 30:
                backoff = 2
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, 30)

    def _on_msg(self, ws, raw) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return
        kind = msg.get("message") if isinstance(msg, dict) else None
        try:
            if kind == "connect":
                self.ready = True
                ws.send(json.dumps({"action": "subscribe", "key": ["feed", "ack"], "value": [""]}))
                self.on_status("Feed: connected", False)
            elif kind == "subscribe":
                ws.send(json.dumps({"action": "ack", "key": [""], "value": [self.customer_id]}))
                for k in self.keys():
                    ws.send(json.dumps({"action": "feed", "key": ["full"], "value": [k]}))
                self.on_status("Feed: subscribed", False)
        except Exception as e:
            self.on_status(f"Feed send failed: {e}", True)
        self.on_message(msg)
