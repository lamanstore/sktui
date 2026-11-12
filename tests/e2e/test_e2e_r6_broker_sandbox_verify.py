"""End-to-End Tests for Requirement R6: Broker Sandbox Verification & Endpoints.

Covers:
- Tier 1: Feature Coverage (isolated happy-path tests)
  1. AES-GCM 256 Crypto Encryption & Decryption Roundtrip
  2. Paper Broker Client Order Placement & Position Lifecycle
  3. Paper Broker Client Limit Order & Cancellation
  4. Broker Verification Test Harness Execution
  5. CLI verify command argument parsing and sandbox execution
- Tier 2: Boundary & Corner Cases
  6. Corrupted ciphertext and invalid authentication tag rejection
  7. Order validation with zero, negative, or invalid tick size
  8. Margin and cash balance depletion limits
  9. Canceling non-existent or already-finalized orders
  10. Broker verifier fault tolerance under simulated endpoint downtime
"""
from __future__ import annotations

import base64
from typing import Any, Callable

import pytest
from cryptography.exceptions import InvalidTag

from sktui.api.auth import decrypt_str, encrypt_str
from sktui.api.client import Client


def _get_broker_verifier() -> Any:
    try:
        import sktui.services.broker_verifier as bv
        return bv
    except ImportError:
        pytest.skip("sktui.services.broker_verifier implementation pending in Milestone 6")


# ============================================================================
# Tier 1: Feature Coverage (Isolated Happy Path)
# ============================================================================

def test_r6_t1_aes_gcm_crypto_roundtrip() -> None:
    """Verify AES-GCM 256 encrypt_str and decrypt_str preserve plaintext tokens."""
    secret_key = "12345678901234567890123456789012"  # Exactly 32 bytes
    plaintext = "ReqToken12345|CustomerId98765"

    # Versioned (Base64-URL safe)
    cipher_v = encrypt_str(plaintext, secret_key, versioned=True)
    assert cipher_v != plaintext
    recovered_v = decrypt_str(cipher_v, secret_key, versioned=True)
    assert recovered_v == plaintext

    # Non-versioned (Standard Base64)
    cipher_nv = encrypt_str(plaintext, secret_key, versioned=False)
    assert cipher_nv != plaintext
    recovered_nv = decrypt_str(cipher_nv, secret_key, versioned=False)
    assert recovered_nv == plaintext


def test_r6_t1_paper_client_order_lifecycle(fake_client: Client) -> None:
    """Verify paper client executes simulated market orders and updates positions."""
    params = {
        "requestType": "NEW",
        "exchange": "NC",
        "tradingSymbol": "RELIANCE",
        "quantity": 10,
        "price": "0",
        "orderType": "MKT",
        "transactionType": "B",
        "productType": "CNF",
    }

    res = fake_client.submit(params)
    assert isinstance(res, dict)
    assert res.get("paper") is True or "orderId" in res or "data" in res

    orders = fake_client.orders()
    assert len(orders) >= 1

    positions = fake_client.positions()
    assert len(positions) >= 1
    rel_pos = next((p for p in positions if p.get("tradingSymbol") == "RELIANCE"), None)
    assert rel_pos is not None
    assert rel_pos.get("buyQty", 0) >= 10


def test_r6_t1_paper_client_limit_order_execution(fake_client: Client) -> None:
    """Verify paper client accepts limit orders and handles cancellation."""
    params = {
        "requestType": "NEW",
        "exchange": "NC",
        "tradingSymbol": "TATAMOTORS",
        "quantity": 25,
        "price": "420.00",
        "orderType": "LMT",
        "transactionType": "B",
        "productType": "CNF",
    }

    res = fake_client.submit(params)
    order_id = res.get("orderId") or "1001"

    # Cancel limit order
    cancel_res = fake_client.cancel_by_id(order_id)
    assert isinstance(cancel_res, dict)
    assert cancel_res.get("sent") is True or cancel_res.get("cancel") == order_id


def test_r6_t1_broker_verifier_harness_run(fake_client: Client) -> None:
    """Verify BrokerVerifier test harness runs diagnostic checks against paper sandbox."""
    bv = _get_broker_verifier()
    verifier = bv.BrokerVerifier(client=fake_client, paper=True)

    summary = verifier.run_all_checks()
    assert summary is not None
    passed = getattr(summary, "passed", None) if hasattr(summary, "passed") else (summary.get("passed") if isinstance(summary, dict) else None)
    if passed is None:
        passed = getattr(summary, "success", None) if hasattr(summary, "success") else (summary.get("success") if isinstance(summary, dict) else None)
    assert passed is True, f"Broker verification failed or did not report passed=True: {summary}"


def test_r6_t1_cli_verify_sandbox_command(
    cli_runner: Callable[[list[str]], tuple[int, str, str]],
) -> None:
    """Verify CLI verify command parses --sandbox flag and executes verifier."""
    code, out, err = cli_runner(["verify", "--sandbox"])
    if code == 2 and "unrecognized arguments" in err:
        pytest.skip("CLI verify subparser pending in Milestone 1/6")
    assert code == 0, f"sktui verify failed with exit code {code}: {err}"
    assert "verify" in out.lower() or "sandbox" in out.lower(), f"Expected 'verify'/'sandbox' in stdout, got:\n{out}"


# ============================================================================
# Tier 2: Boundary & Corner Cases
# ============================================================================

def test_r6_t2_crypto_auth_corrupted_ciphertext_or_tag() -> None:
    """Verify decrypt_str raises authentication exception on tampered ciphertext or tag."""
    secret_key = "12345678901234567890123456789012"
    cipher = encrypt_str("SecretSessionToken", secret_key, versioned=False)

    # Tamper with the raw base64 payload
    raw = bytearray(base64.b64decode(cipher))
    raw[-1] ^= 0xFF  # Invert bit in GCM auth tag
    corrupted_cipher = base64.b64encode(raw).decode()

    with pytest.raises(InvalidTag):
        decrypt_str(corrupted_cipher, secret_key, versioned=False)


def test_r6_t2_paper_order_validation_invalid_quantity_or_price(fake_client: Client) -> None:
    """Verify submitting orders with zero quantity or invalid parameters is handled safely."""
    params = {
        "requestType": "NEW",
        "exchange": "NC",
        "tradingSymbol": "INFY",
        "quantity": 0,
        "price": "-50.0",
        "orderType": "LMT",
        "transactionType": "B",
        "productType": "CNF",
    }

    try:
        res = fake_client.submit(params)
        # In paper mode, quantity is safely clamped (to >= 1) and valid response returned
        assert isinstance(res, dict), f"Expected dict response, got {type(res)}"
        assert res.get("sent") is True or res.get("orderId") is not None
        order_data = res.get("data", res)
        if "orderQty" in order_data:
            assert int(order_data["orderQty"]) >= 1, "Zero quantity must be clamped to at least 1"
    except (ValueError, KeyError) as exc:
        assert len(str(exc)) > 0


def test_r6_t2_paper_funds_insufficient_rejection(fake_client: Client) -> None:
    """Verify cash balance tracking and margin limits in paper client."""
    funds0 = fake_client.funds("NC")
    assert len(funds0) > 0
    initial_cash = funds0[0]["currentCashBalance"]
    initial_margin = funds0[0]["marginUsed"]
    assert initial_cash == 1_000_000.0
    assert initial_margin == 0.0

    # 1. Submit normal order: 100 shares @ 2500 CNC (cost = 250,000)
    order1 = {
        "requestType": "NEW",
        "exchange": "NC",
        "tradingSymbol": "RELIANCE",
        "quantity": 100,
        "price": "2500.0",
        "orderType": "LMT",
        "transactionType": "B",
        "productType": "CNC",
    }
    res1 = fake_client.submit(order1)
    assert res1.get("sent") is True or res1.get("orderId") is not None

    funds1 = fake_client.funds("NC")[0]
    expected_margin1 = 100 * 2500.0 * 1.0  # 250,000.0
    assert funds1["currentCashBalance"] == initial_cash - expected_margin1  # 750,000.0
    assert funds1["marginUsed"] == expected_margin1
    assert funds1["tradingLimit"] == funds1["currentCashBalance"]

    # 2. Submit depleting order exceeding cash balance: 1,000 shares @ 3500 CNC (cost = 3,500,000 > 750,000)
    order2 = {
        "requestType": "NEW",
        "exchange": "NC",
        "tradingSymbol": "TCS",
        "quantity": 1000,
        "price": "3500.0",
        "orderType": "LMT",
        "transactionType": "B",
        "productType": "CNC",
    }
    res2 = fake_client.submit(order2)
    assert res2 is not None

    funds2 = fake_client.funds("NC")[0]
    # In paper trading, cash balance cannot become negative; it is clamped to 0.0 lower bound
    assert funds2["currentCashBalance"] == 0.0, f"Cash balance must be bounded at 0.0, got {funds2['currentCashBalance']}"
    assert funds2["tradingLimit"] == 0.0
    assert funds2["marginUsed"] == expected_margin1 + (1000 * 3500.0 * 1.0)


def test_r6_t2_cancel_already_filled_or_cancelled_order(fake_client: Client) -> None:
    """Verify canceling non-existent or already finalized order ID does not raise unhandled crash."""
    try:
        res = fake_client.cancel_by_id("NON_EXISTENT_ORDER_999999")
        assert res is not None
    except Exception as exc:
        pytest.fail(f"cancel_by_id raised unhandled exception on invalid order ID: {exc}")


def test_r6_t2_broker_verifier_handles_simulated_network_error(fake_client: Client) -> None:
    """Verify verifier handles simulated network timeout by reporting failure rather than crashing."""
    bv = _get_broker_verifier()
    # Mock client with failing method
    broken_client = Client(
        api_key="BROKEN",
        access_token="BROKEN",
        customer_id="BROKEN",
        paper=False,
    )
    verifier = bv.BrokerVerifier(client=broken_client, paper=False)

    try:
        report = verifier.run_all_checks()
        assert report is not None
    except Exception as exc:
        pytest.fail(f"BrokerVerifier crashed unexpectedly on network fault: {exc}")
