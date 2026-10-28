"""Sharekhan authentication helpers and login token utilities."""
from __future__ import annotations

import base64
import json
import re
from urllib.parse import unquote, urlencode

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

BASE = "https://api.sharekhan.com/skapi"
DEFAULT_VERSION = "1005"
IV = bytes(16)


class ApiError(Exception):
    def __init__(self, status, message: str, kind: str = ""):
        self.status = status
        self.message = message
        self.kind = kind
        super().__init__(f"[{status}] {message}" + (f" ({kind})" if kind else ""))


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
    """Swap RequestId|CustomerId halves and re-encrypt."""
    plain = decrypt_str(clean_request_token(request_token), secret_key, versioned)
    if "|" not in plain:
        raise ValueError("Request token did not decrypt to 'RequestId|CustomerId' - wrong secret key or version?")
    req_id, cust_id = plain.split("|", 1)
    return encrypt_str(f"{cust_id}|{req_id}", secret_key, versioned)


def login_url(api_key: str, vendor_key: str = "", version_id: str = DEFAULT_VERSION, state: str = "12345") -> str:
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


def _unwrap(resp: requests.Response):
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
    versioned = bool(version_id)
    body = {
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
