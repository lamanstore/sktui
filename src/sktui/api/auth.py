"""Sharekhan login crypto and token helpers.

Login flow (per official docs):
  1. Build the login URL with login_url().
  2. User logs in; browser redirects with ?request_token=...
  3. clean_request_token() strips URL noise.
  4. swap_request_token() decrypts "RequestId|CustomerId", swaps halves,
     re-encrypts — this is what the /access/token endpoint expects.
  5. fetch_access_token() posts to the API and returns the session dict.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import unquote, urlencode

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from sktui.api.client import _unwrap, ApiError

BASE = "https://api.sharekhan.com/skapi"
IV = bytes(16)  # docs: base64 "AAAAAAAAAAAAAAAAAAAAAA==" == 16 zero bytes
DEFAULT_VERSION = "1005"  # 1005 => Base64-URL encoding; empty => plain Base64


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
        raise ValueError(
            "Request token did not decrypt to 'RequestId|CustomerId' - wrong secret key or version?"
        )
    req_id, cust_id = plain.split("|", 1)
    return encrypt_str(f"{cust_id}|{req_id}", secret_key, versioned)


def login_url(
    api_key: str,
    vendor_key: str = "",
    version_id: str = DEFAULT_VERSION,
    state: str = "12345",
) -> str:
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


def fetch_access_token(
    api_key: str,
    secret_key: str,
    request_token: str,
    vendor_key: str = "",
    version_id: str = DEFAULT_VERSION,
    state: int = 12345,
) -> dict:
    """Step 3+4 of the documented login.

    Returns data: token, customerId, loginId, exchanges, fullName.
    """
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
