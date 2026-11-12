"""Comprehensive Unit and Integration Tests for Broker Sandbox Verification (Milestone 6).

Sections:
1. Dataclass & Serialization Fidelity (VerificationResult, VerificationSummary)
2. AES-GCM 256 Crypto Auth Verification (verify_crypto)
3. Paper Sandbox Simulation Verification (verify_paper_sandbox)
4. Live & Mock Broker Endpoint Probing (verify_endpoints)
5. Aggregated Verification Engine (run_all and run_all_checks)
6. Headless CLI sktui verify Subcommand (argparse, handle_verify, JSON, file output)
7. TUI BrokerVerifyModal Lifecycle & Actions (composition, bindings, actions, table updates)
8. Slash Command Routing & MainScreen Integration (/verify dispatch and action)
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from cryptography.exceptions import InvalidTag
from textual.app import App
from textual.widgets import DataTable, Label, Select, Static

from sktui.api.auth import decrypt_str, encrypt_str, swap_request_token
from sktui.api.client import Client, as_rows
from sktui.config import SLASH_COMMANDS
from sktui.screens.main import MainScreen
from sktui.screens.modals import BrokerVerifyModal
from sktui.services.broker_verifier import (
    BrokerVerifier,
    VerificationReport,
    VerificationResult,
    VerificationSummary,
)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Dataclass & Serialization Fidelity
# ══════════════════════════════════════════════════════════════════════════════

def test_s1_verification_result_defaults_and_serialization() -> None:
    """VerificationResult initializes with defaults and serializes cleanly to dict."""
    res = VerificationResult(
        name="test_check",
        status="PASS",
        latency_ms=12.34,
        message="Check completed successfully",
    )
    assert res.name == "test_check"
    assert res.status == "PASS"
    assert res.latency_ms == 12.34
    assert res.message == "Check completed successfully"
    assert res.domain == "general"
    assert res.details == {}

    d = res.to_dict()
    assert d == {
        "name": "test_check",
        "status": "PASS",
        "latency_ms": 12.34,
        "message": "Check completed successfully",
        "details": {},
        "domain": "general",
    }


def test_s1_verification_summary_counts_and_metrics() -> None:
    """VerificationSummary accurately calculates passed, counts, and latencies."""
    r1 = VerificationResult(name="c1", status="PASS", latency_ms=10.0, message="ok")
    r2 = VerificationResult(name="c2", status="FAIL", latency_ms=20.0, message="failed")
    r3 = VerificationResult(name="c3", status="SKIPPED", latency_ms=0.0, message="skip")

    summary = VerificationSummary(results=[r1, r2, r3], duration_ms=30.0)

    assert summary.passed is False
    assert summary.success is False
    assert summary.total_count == 3
    assert summary.total_checks == 3
    assert summary.passed_count == 1
    assert summary.passed_checks == 1
    assert summary.failed_count == 1
    assert summary.failed_checks == 1
    assert summary.skipped_count == 1
    assert summary.skipped_checks == 1
    assert summary.avg_latency_ms == 10.0
    assert summary.total_latency_ms == 30.0

    d = summary.to_dict()
    assert d["passed"] is False
    assert d["total_count"] == 3
    assert d["passed_count"] == 1
    assert d["failed_count"] == 1
    assert len(d["results"]) == 3


def test_s1_verification_summary_all_pass_and_empty() -> None:
    """VerificationSummary returns passed=True when all checks pass or list is empty."""
    empty_summary = VerificationSummary()
    assert empty_summary.passed is True
    assert empty_summary.total_count == 0
    assert empty_summary.avg_latency_ms == 0.0

    r1 = VerificationResult(name="c1", status="PASS", latency_ms=5.0, message="ok")
    r2 = VerificationResult(name="c2", status="SKIPPED", latency_ms=0.0, message="skip")
    all_pass = VerificationSummary(results=[r1, r2], duration_ms=5.0)
    assert all_pass.passed is True
    assert all_pass.success is True


def test_s1_verification_summary_dict_interface_and_iteration() -> None:
    """VerificationSummary supports dict lookup, iteration, len, and alias equality."""
    r1 = VerificationResult(name="chk", status="PASS", latency_ms=1.5, message="ok")
    summary = VerificationSummary(results=[r1], duration_ms=1.5)

    assert summary["passed"] is True
    assert summary["total_count"] == 1
    assert summary.get("passed") is True
    assert summary.get("unknown_key", "default_val") == "default_val"
    with pytest.raises(KeyError):
        _ = summary["non_existent_key"]

    items = list(summary)
    assert len(items) == 1
    assert items[0].name == "chk"
    assert len(summary) == 1

    # VerificationReport must be identical alias to VerificationSummary
    assert VerificationReport is VerificationSummary


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: AES-GCM 256 Crypto Auth Verification (verify_crypto)
# ══════════════════════════════════════════════════════════════════════════════

def test_s2_verify_crypto_all_checks_pass() -> None:
    """verify_crypto executes all 6 cryptographic diagnostic checks with PASS."""
    verifier = BrokerVerifier(secret_key="12345678901234567890123456789012")
    results = verifier.verify_crypto()

    assert len(results) >= 6
    expected_names = {
        "crypto_aes_gcm_versioned_roundtrip",
        "crypto_aes_gcm_raw_roundtrip",
        "crypto_key_length_enforcement",
        "crypto_corrupted_tag_rejection",
        "crypto_request_token_swapping",
        "crypto_benchmark_throughput",
    }
    actual_names = {r.name for r in results}
    assert expected_names.issubset(actual_names)

    for r in results:
        assert r.status == "PASS", f"Check {r.name} failed: {r.message}"
        assert r.domain == "crypto"
        assert r.latency_ms >= 0.0


def test_s2_crypto_key_length_enforcement_direct() -> None:
    """AES-GCM key validation strictly requires 32 bytes."""
    from sktui.api.auth import _aes

    for invalid_key in ["", "short", "1234567890123456789012345678901", "123456789012345678901234567890123"]:
        with pytest.raises(ValueError, match="Secret key must be exactly 32 characters"):
            _aes(invalid_key)

    valid_key = "12345678901234567890123456789012"
    cipher = _aes(valid_key)
    assert cipher is not None


def test_s2_crypto_corrupted_tag_rejection_direct() -> None:
    """AES-GCM tag tampering raises InvalidTag on decryption."""
    import base64
    key = "12345678901234567890123456789012"
    token = encrypt_str("Hello|World", key, versioned=False)
    raw = bytearray(base64.b64decode(token))
    raw[-1] ^= 0xFF  # Flip bit in GCM auth tag
    corrupted_token = base64.b64encode(raw).decode("utf-8")

    with pytest.raises(InvalidTag):
        decrypt_str(corrupted_token, key, versioned=False)


def test_s2_crypto_token_swap_logic() -> None:
    """swap_request_token correctly splits on | and swaps halves."""
    key = "12345678901234567890123456789012"
    req_tok = encrypt_str("Req1001|Cust2002", key, versioned=True)
    swapped_tok = swap_request_token(req_tok, key, versioned=True)
    plain_swapped = decrypt_str(swapped_tok, key, versioned=True)
    assert plain_swapped == "Cust2002|Req1001"

    # String without '|' raises ValueError
    bad_tok = encrypt_str("NoDelimiterToken", key, versioned=True)
    with pytest.raises(ValueError, match="Request token did not decrypt to"):
        swap_request_token(bad_tok, key, versioned=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Paper Sandbox Simulation Verification (verify_paper_sandbox)
# ══════════════════════════════════════════════════════════════════════════════

def test_s3_verify_paper_sandbox_all_checks_pass() -> None:
    """verify_paper_sandbox executes all 7 paper sandbox tests with PASS."""
    verifier = BrokerVerifier(paper=True)
    results = verifier.verify_paper_sandbox()

    assert len(results) >= 7
    expected_names = {
        "paper_order_placement",
        "paper_order_cancellation",
        "paper_position_tracking",
        "paper_delivery_holdings",
        "paper_margin_cash_clamping",
        "paper_market_depth_synthesis",
        "paper_synthetic_ohlcv",
    }
    actual_names = {r.name for r in results}
    assert expected_names.issubset(actual_names)

    for r in results:
        assert r.status == "PASS", f"Check {r.name} failed: {r.message}"
        assert r.domain == "paper"
        assert r.latency_ms >= 0.0


def test_s3_paper_sandbox_margin_clamping_boundary() -> None:
    """Paper trading cash balance clamps at 0.0 lower bound and never goes negative."""
    client = Client(api_key="TEST", access_token="TEST", customer_id="123", paper=True)
    funds = client.funds("NC")
    initial_cash = funds[0].get("currentCashBalance") if isinstance(funds, list) else funds.get("currentCashBalance")
    assert initial_cash == 1_000_000.0

    # Deplete cash with order far exceeding balance
    client.submit({
        "requestType": "NEW",
        "exchange": "NC",
        "tradingSymbol": "BIGCO",
        "quantity": 10000,
        "price": "500.0",
        "orderType": "LMT",
        "transactionType": "B",
        "productType": "CNC",
    })
    post_funds = client.funds("NC")
    post_cash = post_funds[0].get("currentCashBalance") if isinstance(post_funds, list) else post_funds.get("currentCashBalance")
    post_limit = post_funds[0].get("tradingLimit") if isinstance(post_funds, list) else post_funds.get("tradingLimit")
    assert post_cash == 0.0
    assert post_limit == 0.0


def test_s3_paper_sandbox_depth_and_ohlcv_synthesis() -> None:
    """Paper depth DOM has 5 levels and OHLCV history has valid candlestick bounds."""
    from sktui.state.quote_store import QuoteStore
    from sktui.api.paper_trading import generate_paper_history

    quotes = QuoteStore()
    depth = quotes.get_depth("NC2885", fallback_ltp=2500.0)
    assert len(depth["bids"]) == 5
    assert len(depth["asks"]) == 5
    assert depth["spread"] >= 0.0
    assert -100.0 <= depth["imbalance_pct"] <= 100.0

    bars = generate_paper_history("NC", 2885, interval="1d", bars_count=30, base_price=2500.0)
    assert len(bars) == 30
    for bar in bars:
        assert bar["high"] >= bar["open"]
        assert bar["high"] >= bar["close"]
        assert bar["low"] <= bar["open"]
        assert bar["low"] <= bar["close"]
        assert bar["volume"] > 0


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Live & Mock Broker Endpoint Probing (verify_endpoints)
# ══════════════════════════════════════════════════════════════════════════════

def test_s4_verify_endpoints_paper_mode_passes() -> None:
    """verify_endpoints against paper client queries all 5 probe endpoints with PASS."""
    paper_client = Client(api_key="SB", access_token="SB", customer_id="12345", paper=True)
    verifier = BrokerVerifier(client=paper_client, paper=True)
    results = verifier.verify_endpoints(client=paper_client)

    assert len(results) == 5
    names = {r.name for r in results}
    assert names == {
        "endpoint_funds",
        "endpoint_holdings",
        "endpoint_positions",
        "endpoint_orders",
        "endpoint_quotes",
    }
    for r in results:
        assert r.status == "PASS"
        assert r.domain == "endpoints"


def test_s4_verify_endpoints_handles_network_error_gracefully() -> None:
    """verify_endpoints against broken client records FAIL without crashing."""
    broken_client = Client(api_key="BROKEN", access_token="BROKEN", customer_id="BROKEN", paper=False)
    verifier = BrokerVerifier(client=broken_client, paper=False)
    results = verifier.verify_endpoints(client=broken_client)

    assert len(results) == 5
    for r in results:
        assert r.status == "FAIL"
        assert "error" in r.details
        assert r.domain == "endpoints"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: Aggregated Verification Engine (run_all and run_all_checks)
# ══════════════════════════════════════════════════════════════════════════════

def test_s5_run_all_and_run_all_checks_sandbox() -> None:
    """run_all and run_all_checks aggregate all checks with 100% pass on paper sandbox."""
    verifier = BrokerVerifier(paper=True)

    results = verifier.run_all()
    assert len(results) >= 18
    assert all(r.status == "PASS" for r in results)

    summary = verifier.run_all_checks()
    assert isinstance(summary, VerificationSummary)
    assert summary.passed is True
    assert summary.success is True
    assert summary.total_count == len(results)
    assert summary.failed_count == 0
    assert summary.passed_count == len(results)
    assert summary.duration_ms >= 0.0


def test_s5_run_all_checks_broken_client_reports_failure() -> None:
    """run_all_checks against broken client with sandbox_only=False reports passed=False."""
    broken_client = Client(api_key="FAIL", access_token="FAIL", customer_id="FAIL", paper=False)
    verifier = BrokerVerifier(client=broken_client, paper=False)
    summary = verifier.run_all_checks(client=broken_client, sandbox_only=False)

    assert isinstance(summary, VerificationSummary)
    assert summary.passed is False
    assert summary.failed_count > 0


def test_s5_as_rows_utility() -> None:
    """as_rows safely extracts list of dicts from varying API response structures."""
    assert as_rows({"id": 1}) == [{"id": 1}]
    assert as_rows([{"id": 1}, {"id": 2}]) == [{"id": 1}, {"id": 2}]
    assert as_rows(None) == []
    assert as_rows("string_payload") == []


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: Headless CLI sktui verify Subcommand
# ══════════════════════════════════════════════════════════════════════════════

def test_s6_cli_verify_argument_parser() -> None:
    """build_parser parses all M6 verify flags correctly."""
    from sktui.app import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "verify",
        "--sandbox",
        "--auth",
        "--endpoint", "https://api.sharekhan.com",
        "--output", "/tmp/out.json",
        "--json",
        "--verbose",
    ])
    assert args.command == "verify"
    assert args.subcommand == "verify"
    assert args.sandbox is True
    assert args.auth is True
    assert args.endpoint == "https://api.sharekhan.com"
    assert args.output == "/tmp/out.json"
    assert args.json is True
    assert args.verbose is True

    # Test --live flag
    args_live = parser.parse_args(["verify", "--live"])
    assert args_live.live is True

    # Test --no-sandbox flag
    args_no_sb = parser.parse_args(["verify", "--no-sandbox"])
    assert args_no_sb.sandbox is False


def test_s6_cli_handle_verify_sandbox_default(capsys: pytest.CaptureFixture[str]) -> None:
    """handle_verify with default sandbox executes verifier and returns 0."""
    from sktui.app import handle_verify

    args = argparse.Namespace(
        sandbox=True,
        endpoint=None,
        verbose=False,
        auth=False,
        paper=False,
        live=False,
        output=None,
        json=False,
    )
    code = handle_verify(args)
    assert code == 0
    out = capsys.readouterr().out
    assert "verify" in out.lower() or "sandbox" in out.lower()
    assert "PASS" in out


def test_s6_cli_handle_verify_auth_subset(capsys: pytest.CaptureFixture[str]) -> None:
    """handle_verify with --auth runs only crypto checks and returns 0."""
    from sktui.app import handle_verify

    args = argparse.Namespace(
        sandbox=True,
        endpoint=None,
        verbose=False,
        auth=True,
        paper=False,
        live=False,
        output=None,
        json=False,
    )
    code = handle_verify(args)
    assert code == 0
    out = capsys.readouterr().out
    assert "crypto" in out.lower()


def test_s6_cli_handle_verify_paper_subset(capsys: pytest.CaptureFixture[str]) -> None:
    """handle_verify with --paper runs only paper trading checks and returns 0."""
    from sktui.app import handle_verify

    args = argparse.Namespace(
        sandbox=True,
        endpoint=None,
        verbose=False,
        auth=False,
        paper=True,
        live=False,
        output=None,
        json=False,
    )
    code = handle_verify(args)
    assert code == 0
    out = capsys.readouterr().out
    assert "paper" in out.lower()


def test_s6_cli_handle_verify_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    """handle_verify with --json emits valid parseable JSON to stdout."""
    from sktui.app import handle_verify

    args = argparse.Namespace(
        sandbox=True,
        endpoint=None,
        verbose=False,
        auth=False,
        paper=False,
        live=False,
        output=None,
        json=True,
    )
    code = handle_verify(args)
    assert code == 0
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["passed"] is True
    assert data["total_count"] >= 18
    assert "results" in data


def test_s6_cli_handle_verify_output_files(tmp_path: Path) -> None:
    """handle_verify writes JSON and text output files when --output is supplied."""
    from sktui.app import handle_verify

    json_file = str(tmp_path / "report.json")
    txt_file = str(tmp_path / "report.txt")

    # JSON output
    args_json = argparse.Namespace(
        sandbox=True,
        endpoint=None,
        verbose=False,
        auth=True,
        paper=False,
        live=False,
        output=json_file,
        json=True,
    )
    code = handle_verify(args_json)
    assert code == 0
    with open(json_file, "r", encoding="utf-8") as f:
        content = json.load(f)
    assert content["passed"] is True

    # Text output
    args_txt = argparse.Namespace(
        sandbox=True,
        endpoint=None,
        verbose=False,
        auth=False,
        paper=False,
        live=False,
        output=txt_file,
        json=False,
    )
    code = handle_verify(args_txt)
    assert code == 0
    with open(txt_file, "r", encoding="utf-8") as f:
        txt_content = f.read()
    assert "Status: PASS" in txt_content


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: TUI BrokerVerifyModal Lifecycle & Actions
# ══════════════════════════════════════════════════════════════════════════════

def test_s7_broker_verify_modal_initialization_variants() -> None:
    """BrokerVerifyModal accepts default, crypto, paper, and live configurations."""
    m_default = BrokerVerifyModal()
    assert m_default.paper is True
    assert m_default.mode is None

    m_crypto = BrokerVerifyModal(mode="crypto")
    assert m_crypto.mode == "crypto"
    assert m_crypto.paper is True

    m_paper = BrokerVerifyModal(mode="paper")
    assert m_paper.mode == "paper"
    assert m_paper.paper is True

    m_live = BrokerVerifyModal(mode="live")
    assert m_live.mode == "live"
    assert m_live.paper is False

    custom_client = Client(api_key="C", access_token="C", customer_id="0", paper=True)
    m_client = BrokerVerifyModal(client=custom_client)
    assert m_client.client is custom_client


def test_s7_broker_verify_modal_bindings() -> None:
    """BrokerVerifyModal registers escape/q, r, c, p, e keybindings."""
    binding_keys = {b.key for b in BrokerVerifyModal.BINDINGS}
    assert "escape" in binding_keys
    assert "q" in binding_keys
    assert "r" in binding_keys
    assert "c" in binding_keys
    assert "p" in binding_keys
    assert "e" in binding_keys


def test_s7_broker_verify_modal_tui_app_lifecycle() -> None:
    """BrokerVerifyModal mounts, populates widgets, handles hotkeys, and dismisses on Escape."""
    class TestApp(App):
        def compose(self):
            yield Label("Test Base Screen")

    async def run() -> None:
        app = TestApp()
        async with app.run_test(size=(160, 45)) as pilot:
            modal = BrokerVerifyModal()
            app.push_screen(modal)
            await pilot.pause(0.1)

            assert isinstance(app.screen, BrokerVerifyModal)
            table = app.screen.query_one("#t-verify-results", DataTable)
            assert len(table.columns) == 5
            assert table.row_count >= 18

            status_strip = app.screen.query_one("#verify-status-strip", Static)
            assert "ALL CHECKS PASSED" in str(status_strip.render())

            # Test hotkey c (crypto only)
            await pilot.press("c")
            await pilot.pause(0.05)
            assert table.row_count >= 6

            # Test hotkey p (paper only)
            await pilot.press("p")
            await pilot.pause(0.05)
            assert table.row_count >= 7

            # Test hotkey e (endpoints only)
            await pilot.press("e")
            await pilot.pause(0.05)
            assert table.row_count == 5

            # Test hotkey r (rerun all)
            await pilot.press("r")
            await pilot.pause(0.05)
            assert table.row_count >= 18

            # Test hotkey Escape to dismiss modal
            await pilot.press("escape")
            await pilot.pause(0.1)
            assert not isinstance(app.screen, BrokerVerifyModal)

    asyncio.run(run())


def test_s7_broker_verify_modal_action_methods_execute_safely() -> None:
    """BrokerVerifyModal action methods execute verifier checks and update state."""
    modal = BrokerVerifyModal()

    modal.action_rerun_all()
    assert modal.summary is not None
    assert modal.summary.passed is True
    assert modal.summary.total_count >= 18

    modal.action_run_crypto_only()
    assert modal.summary is not None
    assert modal.summary.passed is True
    assert modal.summary.total_count >= 6

    modal.action_run_paper_only()
    assert modal.summary is not None
    assert modal.summary.passed is True
    assert modal.summary.total_count >= 7

    modal.action_run_endpoints_only()
    assert modal.summary is not None
    assert modal.summary.passed is True
    assert modal.summary.total_count == 5


def test_s7_broker_verify_modal_display_detail() -> None:
    """_display_detail renders diagnostic details without raising exceptions."""
    modal = BrokerVerifyModal()
    res = VerificationResult(
        name="test_detail_chk",
        status="PASS",
        latency_ms=4.5,
        message="All good",
        details={"key1": "val1", "key2": 100},
        domain="crypto",
    )
    # Must not raise when called on unmounted or mounted modal
    modal._display_detail(res)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8: Slash Command Routing & MainScreen Integration
# ══════════════════════════════════════════════════════════════════════════════

def test_s8_slash_command_verify_registered() -> None:
    """Slash command /verify is registered in config.SLASH_COMMANDS and ALL_COMMANDS."""
    assert "/verify" in SLASH_COMMANDS
    desc, cmd = SLASH_COMMANDS["/verify"]
    assert "verify" in desc.lower() or "broker" in desc.lower()
    assert cmd == "verify"
    assert "/verify" in MainScreen.ALL_COMMANDS


def test_s8_main_screen_has_action_verify_broker() -> None:
    """MainScreen defines action_verify_broker callable."""
    assert hasattr(MainScreen, "action_verify_broker")
    assert callable(getattr(MainScreen, "action_verify_broker"))


def test_s8_action_verify_broker_pushes_modal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """action_verify_broker instantiates BrokerVerifyModal and pushes to app screen stack."""
    monkeypatch.setattr("sktui.config.CONF", tmp_path)
    monkeypatch.setattr("sktui.config.DATA", tmp_path)
    monkeypatch.setattr("sktui.config.WATCH_FILE", tmp_path / "w.json")
    monkeypatch.setattr("sktui.config.ALERTS_FILE", tmp_path / "a.json")

    mock_app = MagicMock()
    monkeypatch.setattr(MainScreen, "app", property(lambda self: mock_app))

    screen = MainScreen()
    screen.action_verify_broker()

    mock_app.push_screen.assert_called_once()
    pushed_screen = mock_app.push_screen.call_args[0][0]
    assert isinstance(pushed_screen, BrokerVerifyModal)


def test_s8_dispatch_slash_verify_routes_to_action(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """_dispatch_slash('/verify') invokes action_verify_broker cleanly."""
    monkeypatch.setattr("sktui.config.CONF", tmp_path)
    monkeypatch.setattr("sktui.config.DATA", tmp_path)
    monkeypatch.setattr("sktui.config.WATCH_FILE", tmp_path / "w.json")
    monkeypatch.setattr("sktui.config.ALERTS_FILE", tmp_path / "a.json")

    mock_app = MagicMock()
    monkeypatch.setattr(MainScreen, "app", property(lambda self: mock_app))

    screen = MainScreen()
    with patch.object(screen, "action_verify_broker") as mock_action:
        screen._dispatch_slash("/verify")
        mock_action.assert_called_once()
