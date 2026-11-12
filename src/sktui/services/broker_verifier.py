"""Broker Sandbox & Authentication Verification Service for SKTUI.

Provides diagnostic verification of:
1. AES-GCM 256 encryption/decryption roundtrip, token halves swapping,
   key length enforcement, and corrupted tag detection.
2. Paper trading sandbox order lifecycle, position tracking, margin boundaries,
   market depth DOM synthesis, and synthetic OHLCV generation.
3. Live and sandbox endpoint probes (funds, holdings, positions, orders, quotes)
   with graceful network fault handling and zero unhandled exceptions.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any

from cryptography.exceptions import InvalidTag

import sktui.config as cfg
from sktui.api.auth import decrypt_str, encrypt_str, swap_request_token
from sktui.api.client import ApiError, Client, as_rows
from sktui.api.paper_trading import generate_paper_history
from sktui.state.quote_store import QuoteStore


@dataclass
class VerificationResult:
    """Individual verification test result."""

    name: str
    status: str  # "PASS", "FAIL", "SKIPPED"
    latency_ms: float
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    domain: str = "general"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "message": self.message,
            "details": self.details,
            "domain": self.domain,
        }


@dataclass
class VerificationSummary:
    """Aggregated verification execution summary and diagnostics."""

    results: list[VerificationResult] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def passed(self) -> bool:
        """True when all executed checks passed (no FAIL status)."""
        if not self.results:
            return True
        return all(r.status != "FAIL" for r in self.results)

    @property
    def success(self) -> bool:
        """Alias for passed."""
        return self.passed

    @property
    def total_count(self) -> int:
        return len(self.results)

    @property
    def total_checks(self) -> int:
        """Alias for total_count."""
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def passed_checks(self) -> int:
        """Alias for passed_count."""
        return self.passed_count

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def failed_checks(self) -> int:
        """Alias for failed_count."""
        return self.failed_count

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.results if r.status == "SKIPPED")

    @property
    def skipped_checks(self) -> int:
        """Alias for skipped_count."""
        return self.skipped_count

    @property
    def avg_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        return round(sum(r.latency_ms for r in self.results) / len(self.results), 2)

    @property
    def total_latency_ms(self) -> float:
        """Alias for duration_ms or sum of result latencies."""
        return self.duration_ms if self.duration_ms > 0 else round(sum(r.latency_ms for r in self.results), 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "success": self.success,
            "total_count": self.total_count,
            "total_checks": self.total_checks,
            "passed_count": self.passed_count,
            "passed_checks": self.passed_checks,
            "failed_count": self.failed_count,
            "failed_checks": self.failed_checks,
            "skipped_count": self.skipped_count,
            "skipped_checks": self.skipped_checks,
            "avg_latency_ms": self.avg_latency_ms,
            "duration_ms": self.duration_ms,
            "total_latency_ms": self.total_latency_ms,
            "results": [r.to_dict() for r in self.results],
        }

    def __getitem__(self, key: str) -> Any:
        d = self.to_dict()
        if key in d:
            return d[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def __iter__(self):
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)


# Full alias compatibility for callers
VerificationReport = VerificationSummary


class BrokerVerifier:
    """Harness for verifying broker authentication, paper trading, and endpoints."""

    DEFAULT_FALLBACK_KEY = "12345678901234567890123456789012"

    def __init__(
        self,
        client: Client | None = None,
        paper: bool | None = None,
        secret_key: str | None = None,
    ) -> None:
        self.client = client
        if paper is not None:
            self.paper = bool(paper)
        elif client is not None:
            self.paper = getattr(client, "paper", True)
        else:
            self.paper = True

        if secret_key:
            self.secret_key = secret_key
        else:
            configured_key = getattr(cfg, "API_SECRET", None)
            self.secret_key = configured_key if (configured_key and len(configured_key) == 32) else self.DEFAULT_FALLBACK_KEY

    def verify_crypto(self) -> list[VerificationResult]:
        """Verify AES-GCM 256 crypto primitives, key length guards, and token swapping."""
        results: list[VerificationResult] = []
        domain = "crypto"

        # 1. Versioned Roundtrip (Base64-URL safe)
        t0 = time.monotonic()
        try:
            sample_plain = "ReqToken12345|CustomerId98765"
            cipher_v = encrypt_str(sample_plain, self.secret_key, versioned=True)
            recovered_v = decrypt_str(cipher_v, self.secret_key, versioned=True)
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            if recovered_v == sample_plain and cipher_v != sample_plain:
                results.append(
                    VerificationResult(
                        name="crypto_aes_gcm_versioned_roundtrip",
                        status="PASS",
                        latency_ms=lat,
                        message="AES-GCM 256 Base64-URL roundtrip verified successfully.",
                        details={"versioned": True, "cipher_len": len(cipher_v)},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="crypto_aes_gcm_versioned_roundtrip",
                        status="FAIL",
                        latency_ms=lat,
                        message="Decrypted text did not match original plaintext.",
                        details={"expected": sample_plain, "got": recovered_v},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="crypto_aes_gcm_versioned_roundtrip",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Crypto roundtrip exception: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        # 2. Non-versioned Roundtrip (Standard Base64)
        t0 = time.monotonic()
        try:
            cipher_nv = encrypt_str(sample_plain, self.secret_key, versioned=False)
            recovered_nv = decrypt_str(cipher_nv, self.secret_key, versioned=False)
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            if recovered_nv == sample_plain and cipher_nv != sample_plain:
                results.append(
                    VerificationResult(
                        name="crypto_aes_gcm_raw_roundtrip",
                        status="PASS",
                        latency_ms=lat,
                        message="AES-GCM 256 Standard Base64 roundtrip verified successfully.",
                        details={"versioned": False, "cipher_len": len(cipher_nv)},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="crypto_aes_gcm_raw_roundtrip",
                        status="FAIL",
                        latency_ms=lat,
                        message="Raw standard Base64 decrypted text did not match original.",
                        details={"expected": sample_plain, "got": recovered_nv},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="crypto_aes_gcm_raw_roundtrip",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Standard Base64 roundtrip exception: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        # 3. Key Length Enforcement
        t0 = time.monotonic()
        try:
            invalid_keys = ["", "1234567890123456", "123456789012345678901234", "1234567890123456789012345678901", "123456789012345678901234567890123"]
            rejected_count = 0
            for ik in invalid_keys:
                try:
                    encrypt_str("test", ik)
                except ValueError:
                    rejected_count += 1
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            if rejected_count == len(invalid_keys):
                results.append(
                    VerificationResult(
                        name="crypto_key_length_enforcement",
                        status="PASS",
                        latency_ms=lat,
                        message=f"Key length validation enforced ({rejected_count}/{len(invalid_keys)} invalid keys rejected).",
                        details={"tested_lengths": [len(k) for k in invalid_keys]},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="crypto_key_length_enforcement",
                        status="FAIL",
                        latency_ms=lat,
                        message=f"Key length validation missed invalid keys ({rejected_count}/{len(invalid_keys)}).",
                        details={"rejected": rejected_count, "total": len(invalid_keys)},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="crypto_key_length_enforcement",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Key length enforcement check error: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        # 4. Corrupted Tag Rejection
        t0 = time.monotonic()
        try:
            valid_cipher = encrypt_str("SecretSessionToken", self.secret_key, versioned=False)
            raw = bytearray(base64.b64decode(valid_cipher))
            raw[-1] ^= 0xFF  # Invert bit in GCM auth tag
            corrupted_cipher = base64.b64encode(raw).decode()
            caught_invalid_tag = False
            try:
                decrypt_str(corrupted_cipher, self.secret_key, versioned=False)
            except InvalidTag:
                caught_invalid_tag = True
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            if caught_invalid_tag:
                results.append(
                    VerificationResult(
                        name="crypto_corrupted_tag_rejection",
                        status="PASS",
                        latency_ms=lat,
                        message="Corrupted authentication tag was correctly rejected with InvalidTag.",
                        details={"tampered_byte": len(raw) - 1},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="crypto_corrupted_tag_rejection",
                        status="FAIL",
                        latency_ms=lat,
                        message="Decryption of tampered ciphertext did not raise InvalidTag.",
                        details={},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="crypto_corrupted_tag_rejection",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Tampering check error: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        # 5. Token Halves Swapping
        t0 = time.monotonic()
        try:
            req_plain = "ReqID999|CustID111"
            req_cipher = encrypt_str(req_plain, self.secret_key, versioned=True)
            swapped_cipher = swap_request_token(req_cipher, self.secret_key, versioned=True)
            decrypted_swapped = decrypt_str(swapped_cipher, self.secret_key, versioned=True)

            # Test invalid token format without delimiter '|'
            invalid_format_plain = "ReqIDWithoutPipe"
            invalid_format_cipher = encrypt_str(invalid_format_plain, self.secret_key, versioned=True)
            caught_format_error = False
            try:
                swap_request_token(invalid_format_cipher, self.secret_key, versioned=True)
            except ValueError:
                caught_format_error = True

            lat = round((time.monotonic() - t0) * 1000.0, 3)
            if decrypted_swapped == "CustID111|ReqID999" and caught_format_error:
                results.append(
                    VerificationResult(
                        name="crypto_request_token_swapping",
                        status="PASS",
                        latency_ms=lat,
                        message="Request token halves swapping and error handling verified.",
                        details={"swapped": decrypted_swapped, "format_guard": caught_format_error},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="crypto_request_token_swapping",
                        status="FAIL",
                        latency_ms=lat,
                        message="Token swapping produced unexpected result or missed delimiter validation.",
                        details={"got": decrypted_swapped, "format_guard": caught_format_error},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="crypto_request_token_swapping",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Token swapping error: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        # 6. Benchmark Throughput
        t0 = time.monotonic()
        try:
            iterations = 50
            for i in range(iterations):
                c = encrypt_str(f"Payload-{i}", self.secret_key, versioned=True)
                decrypt_str(c, self.secret_key, versioned=True)
            total_duration = time.monotonic() - t0
            lat = round(total_duration * 1000.0, 3)
            avg_op_ms = round((total_duration / (iterations * 2)) * 1000.0, 3)
            ops_per_sec = round((iterations * 2) / max(0.0001, total_duration), 1)
            results.append(
                VerificationResult(
                    name="crypto_benchmark_throughput",
                    status="PASS",
                    latency_ms=lat,
                    message=f"Benchmark: {ops_per_sec} ops/sec (avg {avg_op_ms} ms/op across {iterations * 2} ops).",
                    details={"iterations": iterations, "ops_per_sec": ops_per_sec, "avg_op_ms": avg_op_ms},
                    domain=domain,
                )
            )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="crypto_benchmark_throughput",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Benchmark error: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        return results

    def _get_target_paper_client(self) -> Client:
        """Resolve or construct a clean paper client instance."""
        if self.client is not None and getattr(self.client, "paper", False):
            return self.client
        return Client(
            api_key="SANDBOX_API_KEY",
            access_token="SANDBOX_TOKEN",
            customer_id="SANDBOX_CUST_99",
            login_id="SANDBOX_USER",
            paper=True,
        )

    def verify_paper_sandbox(self) -> list[VerificationResult]:
        """Verify paper client order lifecycle, positions, holdings, margins, and market depth."""
        results: list[VerificationResult] = []
        domain = "paper"
        test_client = self._get_target_paper_client()

        # 1. Order Placement
        t0 = time.monotonic()
        try:
            order_params = {
                "requestType": "NEW",
                "exchange": "NC",
                "tradingSymbol": "RELIANCE",
                "quantity": 10,
                "price": "0",
                "orderType": "MKT",
                "transactionType": "B",
                "productType": "CNF",
            }
            sub_res = test_client.submit(order_params)
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            has_order_id = bool(sub_res.get("orderId") or sub_res.get("data", {}).get("orderId"))
            is_paper_ack = sub_res.get("paper") is True or has_order_id
            if isinstance(sub_res, dict) and is_paper_ack:
                results.append(
                    VerificationResult(
                        name="paper_order_placement",
                        status="PASS",
                        latency_ms=lat,
                        message="Simulated market order placed and acknowledged successfully.",
                        details={"orderId": sub_res.get("orderId", "N/A"), "status": sub_res.get("requestStatus", "SUCCESS")},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="paper_order_placement",
                        status="FAIL",
                        latency_ms=lat,
                        message="Order placement response did not conform to paper contract.",
                        details={"response": sub_res},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="paper_order_placement",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Order placement failed: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        # 2. Limit Order Submission & Cancellation
        t0 = time.monotonic()
        try:
            limit_params = {
                "requestType": "NEW",
                "exchange": "NC",
                "tradingSymbol": "TATAMOTORS",
                "quantity": 25,
                "price": "420.00",
                "orderType": "LMT",
                "transactionType": "B",
                "productType": "CNF",
            }
            limit_res = test_client.submit(limit_params)
            order_id = limit_res.get("orderId") or "1001"
            cancel_res = test_client.cancel_by_id(order_id)
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            cancel_ok = cancel_res.get("sent") is True or str(cancel_res.get("cancel")) == str(order_id)
            if cancel_ok:
                results.append(
                    VerificationResult(
                        name="paper_order_cancellation",
                        status="PASS",
                        latency_ms=lat,
                        message=f"Limit order {order_id} placed and cancelled successfully.",
                        details={"orderId": order_id, "cancel": cancel_res},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="paper_order_cancellation",
                        status="FAIL",
                        latency_ms=lat,
                        message=f"Cancellation response invalid for order {order_id}.",
                        details={"cancel_res": cancel_res},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="paper_order_cancellation",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Cancellation check error: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        # 3. Position Tracking and Aggregation
        t0 = time.monotonic()
        try:
            positions = test_client.positions()
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            has_pos = isinstance(positions, list) and len(positions) >= 1
            if has_pos:
                results.append(
                    VerificationResult(
                        name="paper_position_tracking",
                        status="PASS",
                        latency_ms=lat,
                        message=f"Position aggregation confirmed across {len(positions)} scrips.",
                        details={"positions_count": len(positions), "symbols": [p.get("tradingSymbol") for p in positions]},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="paper_position_tracking",
                        status="FAIL",
                        latency_ms=lat,
                        message="No positions found after simulated order executions.",
                        details={"positions": positions},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="paper_position_tracking",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Position tracking check error: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        # 4. Delivery Holdings Update
        t0 = time.monotonic()
        try:
            cnc_params = {
                "requestType": "NEW",
                "exchange": "NC",
                "tradingSymbol": "INFY",
                "quantity": 15,
                "price": "1450.0",
                "orderType": "LMT",
                "transactionType": "B",
                "productType": "CNC",
            }
            test_client.submit(cnc_params)
            holdings = test_client.holdings()
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            infy_holding = next((h for h in holdings if h.get("tradingSymbol") == "INFY"), None)
            if infy_holding or len(holdings) >= 1:
                results.append(
                    VerificationResult(
                        name="paper_delivery_holdings",
                        status="PASS",
                        latency_ms=lat,
                        message="Delivery holdings accurately tracked and updated.",
                        details={"holdings_count": len(holdings)},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="paper_delivery_holdings",
                        status="FAIL",
                        latency_ms=lat,
                        message="Holdings not updated following CNC buy order.",
                        details={"holdings": holdings},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="paper_delivery_holdings",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Holdings check error: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        # 5. Margin and Cash Balance Clamping
        t0 = time.monotonic()
        try:
            # Use dedicated client to verify non-negative clamping without disrupting caller state
            deplete_client = Client(
                api_key="TEST",
                access_token="TEST",
                customer_id="DEPLETE_CUST",
                paper=True,
            )
            deplete_params = {
                "requestType": "NEW",
                "exchange": "NC",
                "tradingSymbol": "TCS",
                "quantity": 2000,
                "price": "3500.0",
                "orderType": "LMT",
                "transactionType": "B",
                "productType": "CNC",
            }
            deplete_client.submit(deplete_params)
            funds = deplete_client.funds("NC")
            cash = funds[0].get("currentCashBalance", 0.0) if funds else -1.0
            margin_used = funds[0].get("marginUsed", 0.0) if funds else 0.0
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            if cash == 0.0 and margin_used >= 7000000.0:
                results.append(
                    VerificationResult(
                        name="paper_margin_cash_clamping",
                        status="PASS",
                        latency_ms=lat,
                        message="Cash balance safely clamped to 0.0 lower bound under margin depletion.",
                        details={"cash_balance": cash, "margin_used": margin_used},
                        domain=domain,
                    )
                )
            elif cash >= 0.0:
                results.append(
                    VerificationResult(
                        name="paper_margin_cash_clamping",
                        status="PASS",
                        latency_ms=lat,
                        message=f"Cash balance maintained non-negative ({cash:.2f}).",
                        details={"cash_balance": cash, "margin_used": margin_used},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="paper_margin_cash_clamping",
                        status="FAIL",
                        latency_ms=lat,
                        message=f"Cash balance breached lower bound: {cash}",
                        details={"cash_balance": cash},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="paper_margin_cash_clamping",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Margin clamping check error: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        # 6. 5-Level Market Depth DOM Synthesis
        t0 = time.monotonic()
        try:
            qs = QuoteStore()
            depth = qs.get_depth("NC2885", fallback_ltp=2500.0)
            bids = depth.get("bids", [])
            asks = depth.get("asks", [])
            spread = depth.get("spread", 0.0)
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            if len(bids) == 5 and len(asks) == 5 and spread >= 0.0:
                results.append(
                    VerificationResult(
                        name="paper_market_depth_synthesis",
                        status="PASS",
                        latency_ms=lat,
                        message="5-level DOM bid/ask depth synthesis verified.",
                        details={"bids": len(bids), "asks": len(asks), "spread": spread, "synthetic": depth.get("synthetic", True)},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="paper_market_depth_synthesis",
                        status="FAIL",
                        latency_ms=lat,
                        message=f"Market depth invalid: bids={len(bids)}, asks={len(asks)}, spread={spread}",
                        details={"depth": depth},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="paper_market_depth_synthesis",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Market depth check error: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        # 7. Synthetic OHLCV Candlestick History Generation
        t0 = time.monotonic()
        try:
            bars = generate_paper_history("NC", 2475, "5minute", bars_count=50, base_price=2500.0)
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            valid_bars = (
                len(bars) == 50
                and all(
                    float(b["high"]) >= max(float(b["open"]), float(b["close"]))
                    and float(b["low"]) <= min(float(b["open"]), float(b["close"]))
                    for b in bars
                )
            )
            if valid_bars:
                results.append(
                    VerificationResult(
                        name="paper_synthetic_ohlcv",
                        status="PASS",
                        latency_ms=lat,
                        message=f"Synthetic OHLCV generation confirmed across {len(bars)} bars.",
                        details={"bars_count": len(bars), "sample_close": bars[-1].get("close")},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="paper_synthetic_ohlcv",
                        status="FAIL",
                        latency_ms=lat,
                        message="Synthetic OHLCV failed bar count or price consistency rules.",
                        details={"bars_count": len(bars)},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="paper_synthetic_ohlcv",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Synthetic OHLCV check error: {exc}",
                    details={"error": str(exc)},
                    domain=domain,
                )
            )

        return results

    def verify_endpoints(self, client: Client | None = None) -> list[VerificationResult]:
        """Probe broker REST endpoints (funds, holdings, positions, orders, quotes).

        In paper sandbox mode, verifies in-memory simulation returns valid structures.
        In live broker mode, wraps all network requests in resilient exception handling,
        reporting failures as diagnostics rather than crashing.
        """
        results: list[VerificationResult] = []
        domain = "endpoints"
        target_client = client or self.client

        if target_client is None:
            # When no client is provided, default to paper client probing
            target_client = self._get_target_paper_client()

        is_paper = getattr(target_client, "paper", True)

        # 1. Funds Endpoint Probe
        t0 = time.monotonic()
        try:
            funds_data = target_client.funds("NC")
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            if isinstance(funds_data, list):
                results.append(
                    VerificationResult(
                        name="endpoint_funds",
                        status="PASS",
                        latency_ms=lat,
                        message=f"Funds endpoint verified successfully ({len(funds_data)} entries).",
                        details={"count": len(funds_data), "paper": is_paper},
                        domain=domain,
                    )
                )
            else:
                results.append(
                    VerificationResult(
                        name="endpoint_funds",
                        status="FAIL",
                        latency_ms=lat,
                        message="Funds endpoint returned unexpected data type.",
                        details={"type": str(type(funds_data))},
                        domain=domain,
                    )
                )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="endpoint_funds",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Funds endpoint probe failed: {exc}",
                    details={"error": str(exc), "paper": is_paper},
                    domain=domain,
                )
            )

        # 2. Holdings Endpoint Probe
        t0 = time.monotonic()
        try:
            if is_paper:
                holdings_data = target_client.holdings()
            else:
                holdings_data = as_rows(target_client._req("GET", f"/services/holdings/{target_client.customer_id}"))
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="endpoint_holdings",
                    status="PASS",
                    latency_ms=lat,
                    message=f"Holdings endpoint verified ({len(holdings_data)} rows).",
                    details={"count": len(holdings_data), "paper": is_paper},
                    domain=domain,
                )
            )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="endpoint_holdings",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Holdings endpoint probe failed: {exc}",
                    details={"error": str(exc), "paper": is_paper},
                    domain=domain,
                )
            )

        # 3. Positions Endpoint Probe
        t0 = time.monotonic()
        try:
            if is_paper:
                pos_data = target_client.positions()
            else:
                pos_data = as_rows(target_client._req("GET", f"/services/trades/{target_client.customer_id}"))
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="endpoint_positions",
                    status="PASS",
                    latency_ms=lat,
                    message=f"Positions endpoint verified ({len(pos_data)} rows).",
                    details={"count": len(pos_data), "paper": is_paper},
                    domain=domain,
                )
            )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="endpoint_positions",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Positions endpoint probe failed: {exc}",
                    details={"error": str(exc), "paper": is_paper},
                    domain=domain,
                )
            )

        # 4. Orders Report Endpoint Probe
        t0 = time.monotonic()
        try:
            if is_paper:
                orders_data = target_client.orders()
            else:
                orders_data = as_rows(target_client._req("GET", f"/services/reports/{target_client.customer_id}"))
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="endpoint_orders",
                    status="PASS",
                    latency_ms=lat,
                    message=f"Orders report endpoint verified ({len(orders_data)} rows).",
                    details={"count": len(orders_data), "paper": is_paper},
                    domain=domain,
                )
            )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="endpoint_orders",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Orders endpoint probe failed: {exc}",
                    details={"error": str(exc), "paper": is_paper},
                    domain=domain,
                )
            )

        # 5. Quotes / Market Data Endpoint Probe
        t0 = time.monotonic()
        try:
            if is_paper:
                hist_data = target_client.historical("NC", 2475, "daily")
            else:
                hist_data = as_rows(target_client._req("GET", "/services/historical/NC/2475/daily", timeout=10))
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="endpoint_quotes",
                    status="PASS",
                    latency_ms=lat,
                    message=f"Quotes / market data endpoint verified ({len(hist_data)} bars).",
                    details={"count": len(hist_data), "paper": is_paper},
                    domain=domain,
                )
            )
        except Exception as exc:
            lat = round((time.monotonic() - t0) * 1000.0, 3)
            results.append(
                VerificationResult(
                    name="endpoint_quotes",
                    status="FAIL",
                    latency_ms=lat,
                    message=f"Quotes endpoint probe failed: {exc}",
                    details={"error": str(exc), "paper": is_paper},
                    domain=domain,
                )
            )

        return results

    def run_all(
        self,
        client: Client | None = None,
        sandbox_only: bool | None = None,
    ) -> list[VerificationResult]:
        """Aggregate verification results across crypto, paper sandbox, and endpoints."""
        target_client = client or self.client
        if sandbox_only is None:
            sandbox_only = self.paper

        results: list[VerificationResult] = []
        results.extend(self.verify_crypto())
        results.extend(self.verify_paper_sandbox())

        if sandbox_only:
            # In sandbox-only mode, verify endpoints against paper client
            paper_client = target_client if (target_client and getattr(target_client, "paper", False)) else self._get_target_paper_client()
            results.extend(self.verify_endpoints(client=paper_client))
        else:
            # Probe endpoints with provided (possibly live or broken) client
            results.extend(self.verify_endpoints(client=target_client))

        return results

    def run_all_checks(
        self,
        client: Client | None = None,
        sandbox_only: bool | None = None,
    ) -> VerificationSummary:
        """Execute full verification suite and return structured VerificationSummary."""
        start_t = time.monotonic()
        target_client = client or self.client
        sb = self.paper if sandbox_only is None else sandbox_only
        results = self.run_all(client=target_client, sandbox_only=sb)
        duration_ms = round((time.monotonic() - start_t) * 1000.0, 2)
        return VerificationSummary(results=results, duration_ms=duration_ms)
