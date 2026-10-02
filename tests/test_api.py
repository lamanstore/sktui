import json

import pytest

from sktui import api
from sktui.app import build_order, norm_expiry, normalize_scrip

KEY = "txt1XPdoxL4YVMgnJiFkY6xxGE123456"  # 32 chars


@pytest.mark.parametrize("versioned", [True, False])
def test_crypto_roundtrip(versioned):
    enc = api.encrypt_str("123456|abcDEF", KEY, versioned)
    assert api.decrypt_str(enc, KEY, versioned) == "123456|abcDEF"


@pytest.mark.parametrize("versioned", [True, False])
def test_swap_request_token(versioned):
    token = api.encrypt_str("REQID123|272616", KEY, versioned)
    swapped = api.swap_request_token(token, KEY, versioned)
    assert api.decrypt_str(swapped, KEY, versioned) == "272616|REQID123"


def test_clean_request_token_from_url():
    url = "https://x.com/?request_token=ab+cd%2Bef==&state=12345"
    assert api.clean_request_token(url) == "ab+cd+ef=="


def test_bad_key_length():
    with pytest.raises(ValueError):
        api.encrypt_str("x", "short")


def test_login_url():
    u = api.login_url("KEY", "", "1005")
    assert u == "https://api.sharekhan.com/skapi/auth/login.html?api_key=KEY&state=12345&version_id=1005"


def test_jwt_exp():
    import base64
    p = base64.urlsafe_b64encode(json.dumps({"exp": 1631699664}).encode()).decode().rstrip("=")
    assert api.jwt_exp(f"h.{p}.s") == 1631699664


class R:
    def __init__(self, code, body):
        self.status_code, self.content = code, json.dumps(body).encode()
        self._b = body
        self.text = json.dumps(body)

    def json(self):
        return self._b


def test_unwrap_ok_and_errors():
    assert api._unwrap(R(200, {"status": 200, "data": [{"a": 1}]})) == [{"a": 1}]
    assert api._unwrap(R(200, {"status": 204, "data": []})) == []
    with pytest.raises(api.ApiError):
        api._unwrap(R(403, {"status": 403, "message": "Token expired", "errorType": "Token error"}))


def test_norm_expiry_and_scrip():
    assert norm_expiry("2026-10-27") == "27/10/2026"
    assert norm_expiry("27/10/2026") == "27/10/2026"
    n = normalize_scrip("NF", {"scripCode": 60530, "tradingSymbol": "NIFTY", "instType": "FI",
                               "lotSize": 75, "expiry": "2026-10-27", "strike": 0.0, "optionType": "FUT"})
    assert n["expiry"] == "27/10/2026" and n["scripCode"] == 60530


def base_fields(**kw):
    f = {"exchange": "NC", "scripCode": "2475", "tradingSymbol": "ONGC", "transactionType": "B",
         "quantity": "1", "price": "92.50", "triggerPrice": "0", "disclosedQty": "0", "afterHour": "N",
         "validity": "GFD", "productType": "INVESTMENT", "rmsCode": "ANY"}
    f.update(kw)
    return f


def test_build_new_equity_order_matches_docs():
    p, w = build_order(base_fields(), "NEW", 12345, "LOGIN1")
    assert p == {"customerId": 12345, "scripCode": 2475, "tradingSymbol": "ONGC", "exchange": "NC",
                 "transactionType": "B", "quantity": 1, "disclosedQty": 0, "price": "92.50",
                 "triggerPrice": "0", "rmsCode": "ANY", "afterHour": "N", "orderType": "NORMAL",
                 "channelUser": "LOGIN1", "validity": "GFD", "requestType": "NEW",
                 "productType": "INVESTMENT"}
    assert w == []


def test_build_derivative_and_market_warning():
    f = base_fields(exchange="NF", scripCode="60530", tradingSymbol="NIFTY", quantity="75", price="0",
                    instrumentType="FI", optionType="XX", strikePrice="-1", expiry="2026-10-27", lotSize=75)
    p, w = build_order(f, "NEW", 1, "L")
    assert p["expiry"] == "27/10/2026" and p["strikePrice"] == "-1" and p["instrumentType"] == "FI"
    assert any("MARKET" in x for x in w)


def test_build_modify_and_validation():
    p, _ = build_order(base_fields(orderId="245744063", rmsCode="SKSIMNSE1", executedQty=0), "MODIFY", 1, "L")
    assert p["orderId"] == "245744063" and p["rmsCode"] == "SKSIMNSE1"
    with pytest.raises(ValueError):
        build_order(base_fields(quantity="0"), "NEW", 1, "L")
    with pytest.raises(ValueError):
        build_order(base_fields(exchange="NF"), "NEW", 1, "L")  # derivative without expiry
    with pytest.raises(ValueError):
        build_order(base_fields(validity="MyGTD"), "NEW", 1, "L")
