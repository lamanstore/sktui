"""Pytest fixtures for SKTUI End-to-End (E2E) Test Suite.

Provides standard isolation fixtures, paper clients, synthetic OHLCV generators,
and CLI invocation helpers.
"""
from __future__ import annotations

import io
import os
import random
import sys
from typing import Any, Callable, Generator

import pytest

import sktui.config as cfg
from sktui.api.client import Client
from sktui.api.paper_trading import generate_paper_history


@pytest.fixture
def tmp_app_data(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Generator[dict[str, Any], None, None]:
    """Isolate configuration, session, and intraday data directories for each test."""
    data_dir = tmp_path / "sktui_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    watch_file = data_dir / "watch.json"
    config_file = data_dir / "config.json"
    session_file = data_dir / "session.json"

    monkeypatch.setattr(cfg, "DATA", data_dir)
    monkeypatch.setattr(cfg, "WATCH_FILE", watch_file)
    monkeypatch.setattr(cfg, "CONFIG_FILE", config_file)
    monkeypatch.setattr(cfg, "SESSION_FILE", session_file)
    monkeypatch.setenv("SKTUI_DATA_DIR", str(data_dir))

    yield {
        "data_dir": data_dir,
        "watch_file": watch_file,
        "config_file": config_file,
        "session_file": session_file,
    }


@pytest.fixture
def fake_client() -> Client:
    """Preconfigured offline paper trading client with initialized mock portfolios."""
    client = Client(
        api_key="TEST_API_KEY",
        access_token="TEST_ACCESS_TOKEN",
        customer_id="TEST_CUST_01",
        login_id="TEST_TRADER",
        vendor_key="TEST_VENDOR",
        exchanges=["NC", "BC", "NF"],
        full_name="PAPER SANDBOX TRADER",
        paper=True,
    )
    return client


@pytest.fixture
def synthetic_ohlcv() -> dict[str, Any]:
    """Deterministic synthetic OHLCV bar series (100 bars) with realistic drift and volatility."""
    bars = generate_paper_history("NC", 2475, "5minute", bars_count=100, base_price=2500.0)
    return {
        "bars": bars,
        "open": [float(b["open"]) for b in bars],
        "high": [float(b["high"]) for b in bars],
        "low": [float(b["low"]) for b in bars],
        "close": [float(b["close"]) for b in bars],
        "volume": [float(b["volume"]) for b in bars],
        "symbol": "RELIANCE",
    }


@pytest.fixture
def synthetic_pair_series() -> dict[str, Any]:
    """Generates two cointegrated price series: Y = 1.5 * X + stationary OU spread."""
    rng = random.Random(42)
    n = 120
    x = [100.0]
    for _ in range(n - 1):
        x.append(x[-1] + rng.gauss(0.05, 1.0))

    spread = [0.0]
    theta = 0.25  # Mean-reversion speed
    for _ in range(n - 1):
        spread.append(spread[-1] * (1.0 - theta) + rng.gauss(0.0, 0.4))

    y = [1.5 * xi + si + 15.0 for xi, si in zip(x, spread)]
    return {
        "stock_a": y,
        "stock_b": x,
        "hedge_ratio": 1.5,
        "symbol_a": "HDFCBANK",
        "symbol_b": "ICICIBANK",
    }


@pytest.fixture
def cli_runner(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[str]], tuple[int, str, str]]:
    """Invokes CLI parser and commands in-process, capturing return codes, stdout, and stderr."""
    def run_cli(args: list[str]) -> tuple[int, str, str]:
        import sktui.app as app_mod

        stdout = io.StringIO()
        stderr = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_argv = sys.argv
        exit_code = 0

        try:
            sys.stdout = stdout
            sys.stderr = stderr
            sys.argv = ["sktui"] + args
            if hasattr(app_mod, "main"):
                import inspect
                sig = inspect.signature(app_mod.main)
                if len(sig.parameters) > 0:
                    app_mod.main(args)
                else:
                    app_mod.main()
        except SystemExit as se:
            if isinstance(se.code, int):
                exit_code = se.code
            elif se.code is None:
                exit_code = 0
            else:
                exit_code = 1
        except Exception as exc:
            stderr.write(str(exc))
            exit_code = 1
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.argv = old_argv

        return exit_code, stdout.getvalue(), stderr.getvalue()

    return run_cli
