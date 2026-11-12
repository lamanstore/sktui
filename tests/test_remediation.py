"""Remediation and M1 Architecture Verification Test Suite:
1. Bug 1: MainScreen.on_unmount saves intraday tick tape and terminates live feed without duplicate definitions.
2. Bug 2: sktui.__main__ import guard prevents execution during introspection/import.
3. Bug 3: sktui.__version__ matches pyproject.toml 0.4.0.
4. Bug 4: DebugModal has exactly one action_refresh_debug definition and refreshes safely.
5. Bug 5: Coroutine / timer execution on unmounted MainScreen produces 0 RuntimeWarning under pytest -W error.
6. CLI Subparsers: build_parser() handles valid/invalid invocations for analyze, pairs, signals, backtest, bot, verify, and defaults.
7. Slash Commands: All 8 algorithmic trading slash commands exist in SLASH_COMMANDS, ALL_COMMANDS, and MainScreen dispatch routing.
"""
from __future__ import annotations

import argparse
import ast
import gc
import importlib
import importlib.metadata
import os
import subprocess
import sys
import tomllib
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sktui
from sktui import app as app_module
from sktui.config import SLASH_COMMANDS
from sktui.screens.main import MainScreen
from sktui.screens.modals import DebugModal


# ══════════════════════════════════════════════════════════════════════════════
#  BUG 1: MainScreen.on_unmount Tape Preservation & Feed Shutdown
# ══════════════════════════════════════════════════════════════════════════════

def test_main_screen_has_single_on_unmount_definition():
    """Verify via AST that MainScreen defines on_unmount exactly once."""
    main_py_path = Path(sktui.__file__).resolve().parent / "screens" / "main.py"
    with open(main_py_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(main_py_path))

    main_screen_cls = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "MainScreen"),
        None,
    )
    assert main_screen_cls is not None, "MainScreen class not found in main.py"

    unmount_defs = [
        n for n in main_screen_cls.body
        if isinstance(n, ast.FunctionDef) and n.name == "on_unmount"
    ]
    assert len(unmount_defs) == 1, f"Expected exactly 1 on_unmount definition, found {len(unmount_defs)}"


def test_main_screen_on_unmount_calls_tape_save_and_feed_stop(tmp_path: Path, monkeypatch):
    """Verify on_unmount saves intraday tick tape and shuts down the active feed."""
    monkeypatch.setattr("sktui.config.CONF", tmp_path)
    monkeypatch.setattr("sktui.config.DATA", tmp_path)
    monkeypatch.setattr("sktui.config.WATCH_FILE", tmp_path / "w.json")
    monkeypatch.setattr("sktui.config.ALERTS_FILE", tmp_path / "a.json")

    screen = MainScreen()
    screen.quotes = MagicMock()
    screen.feed = MagicMock()

    screen.on_unmount()

    screen.quotes.save_tape.assert_called_once()
    screen.feed.stop.assert_called_once()
    assert screen._coalescing_active is False
    assert screen._ack_pending is False


def test_main_screen_on_unmount_graceful_when_feed_is_none(tmp_path: Path, monkeypatch):
    """Verify on_unmount does not raise when feed is None."""
    monkeypatch.setattr("sktui.config.CONF", tmp_path)
    monkeypatch.setattr("sktui.config.DATA", tmp_path)
    monkeypatch.setattr("sktui.config.WATCH_FILE", tmp_path / "w.json")
    monkeypatch.setattr("sktui.config.ALERTS_FILE", tmp_path / "a.json")

    screen = MainScreen()
    screen.quotes = MagicMock()
    screen.feed = None

    screen.on_unmount()
    screen.quotes.save_tape.assert_called_once()
    assert screen._coalescing_active is False


def test_main_screen_on_unmount_feed_stop_exception_handling(tmp_path: Path, monkeypatch):
    """Verify on_unmount handles exceptions raised during feed.stop() gracefully."""
    monkeypatch.setattr("sktui.config.CONF", tmp_path)
    monkeypatch.setattr("sktui.config.DATA", tmp_path)
    monkeypatch.setattr("sktui.config.WATCH_FILE", tmp_path / "w.json")
    monkeypatch.setattr("sktui.config.ALERTS_FILE", tmp_path / "a.json")

    screen = MainScreen()
    screen.quotes = MagicMock()
    mock_feed = MagicMock()
    mock_feed.stop.side_effect = RuntimeError("Feed shutdown error")
    screen.feed = mock_feed

    # Should not raise exception
    screen.on_unmount()
    screen.quotes.save_tape.assert_called_once()
    mock_feed.stop.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
#  BUG 2: sktui.__main__ Import Guard
# ══════════════════════════════════════════════════════════════════════════════

def test_dunder_main_has_import_guard_ast():
    """Verify sktui/__main__.py wraps main() in if __name__ == '__main__':."""
    dunder_main_path = Path(sktui.__file__).resolve().parent / "__main__.py"
    with open(dunder_main_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(dunder_main_path))

    has_guard = False
    for node in tree.body:
        if isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Compare):
                left = getattr(test.left, "id", None)
                if left == "__name__":
                    for comparator in test.comparators:
                        if getattr(comparator, "value", None) == "__main__":
                            has_guard = True
                            break
    assert has_guard, "__main__.py must contain 'if __name__ == \"__main__\":'"


def test_dunder_main_safe_import_no_execution():
    """Importing sktui.__main__ must not invoke app.main()."""
    with patch("sktui.app.main") as mock_main:
        if "sktui.__main__" in sys.modules:
            importlib.reload(sys.modules["sktui.__main__"])
        else:
            importlib.import_module("sktui.__main__")
        mock_main.assert_not_called()


def test_dunder_main_wraps_sys_exit_ast():
    """Verify sktui/__main__.py wraps main() with sys.exit(main()) inside the guard."""
    dunder_main_path = Path(sktui.__file__).resolve().parent / "__main__.py"
    with open(dunder_main_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(dunder_main_path))

    calls_sys_exit = False
    for node in tree.body:
        if isinstance(node, ast.If):
            for stmt in node.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    call = stmt.value
                    func_name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
                    if func_name == "exit" or getattr(getattr(call.func, "value", None), "id", None) == "sys":
                        if call.args and isinstance(call.args[0], ast.Call):
                            arg_func = getattr(call.args[0].func, "id", None)
                            if arg_func == "main":
                                calls_sys_exit = True
    assert calls_sys_exit, "__main__.py must invoke sys.exit(main()) inside if __name__ == '__main__':"


def test_dunder_main_exit_code_propagation():
    """Executing python -m sktui with invalid args must exit with code 1."""
    res = subprocess.run(
        [sys.executable, "-m", "sktui", "analyze", ""],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1, f"Expected returncode 1, got {res.returncode}"
    assert "Symbol must not be empty" in res.stderr


# ══════════════════════════════════════════════════════════════════════════════
#  BUG 3: Version Synchronization
# ══════════════════════════════════════════════════════════════════════════════

def test_version_matches_pyproject_toml():
    """Verify sktui.__version__ is 0.4.0 and matches pyproject.toml."""
    pyproject_path = Path(sktui.__file__).resolve().parent.parent.parent / "pyproject.toml"
    assert pyproject_path.exists(), f"pyproject.toml not found at {pyproject_path}"

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    expected_version = data["project"]["version"]
    assert expected_version == "0.4.0"
    assert sktui.__version__ == "0.4.0"
    assert sktui.__version__ == expected_version


def test_importlib_metadata_version_matches():
    """Verify importlib.metadata.version('sktui') returns 0.4.0 and matches package version."""
    meta_ver = importlib.metadata.version("sktui")
    assert meta_ver == "0.4.0", f"Expected metadata version 0.4.0, got {meta_ver}"
    assert meta_ver == sktui.__version__


# ══════════════════════════════════════════════════════════════════════════════
#  BUG 4: DebugModal Duplicate Definition Cleanup
# ══════════════════════════════════════════════════════════════════════════════

def test_debug_modal_single_action_refresh_debug_definition():
    """Verify DebugModal has exactly one action_refresh_debug method defined."""
    modals_py_path = Path(sktui.__file__).resolve().parent / "screens" / "modals.py"
    with open(modals_py_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(modals_py_path))

    dbg_cls = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "DebugModal"),
        None,
    )
    assert dbg_cls is not None, "DebugModal class not found in modals.py"

    refresh_defs = [
        n for n in dbg_cls.body
        if isinstance(n, ast.FunctionDef) and n.name == "action_refresh_debug"
    ]
    assert len(refresh_defs) == 1, f"Expected 1 action_refresh_debug, found {len(refresh_defs)}"


def test_debug_modal_action_refresh_debug_invokes_refresh():
    """Verify action_refresh_debug calls refresh_debug."""
    modal = DebugModal()
    modal.refresh_debug = MagicMock()
    modal.action_refresh_debug()
    modal.refresh_debug.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
#  BUG 5: Zero Coroutine / Timer RuntimeWarning
# ══════════════════════════════════════════════════════════════════════════════

def test_on_ack_unmounted_produces_zero_runtime_warning(tmp_path: Path, monkeypatch):
    """Calling on_ack on an unmounted MainScreen must never leak unawaited timer coroutines."""
    monkeypatch.setattr("sktui.config.CONF", tmp_path)
    monkeypatch.setattr("sktui.config.DATA", tmp_path)
    monkeypatch.setattr("sktui.config.WATCH_FILE", tmp_path / "w.json")
    monkeypatch.setattr("sktui.config.ALERTS_FILE", tmp_path / "a.json")

    screen = MainScreen()
    ack = {
        "AckState": "TRADED",
        "BuySellString": "B",
        "TradeQty": 10,
        "TradePrice": 100.0,
        "TradingSymbol": "TCS",
        "Exchange": "NC",
        "SharekhanOrderID": "999888",
    }

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        screen.on_ack(ack)
        gc.collect()
        runtime_warns = [w for w in recorded if issubclass(w.category, RuntimeWarning)]
        assert len(runtime_warns) == 0, f"Leaked RuntimeWarning: {[str(w.message) for w in runtime_warns]}"


def test_on_ack_mounted_schedules_timer(tmp_path: Path, monkeypatch):
    """When MainScreen is mounted and event loop is available, on_ack schedules the refresh timer."""
    monkeypatch.setattr("sktui.config.CONF", tmp_path)
    monkeypatch.setattr("sktui.config.DATA", tmp_path)
    monkeypatch.setattr("sktui.config.WATCH_FILE", tmp_path / "w.json")
    monkeypatch.setattr("sktui.config.ALERTS_FILE", tmp_path / "a.json")

    mock_app = MagicMock()
    monkeypatch.setattr(MainScreen, "app", property(lambda self: mock_app))

    screen = MainScreen()
    screen._is_mounted = True
    screen.set_timer = MagicMock()

    ack = {
        "AckState": "TRADED",
        "BuySellString": "B",
        "TradeQty": 5,
        "TradingSymbol": "INFY",
        "SharekhanOrderID": "111222",
    }

    # Mock asyncio.get_running_loop to return a running loop
    mock_loop = MagicMock()
    mock_loop.is_running.return_value = True
    with patch("asyncio.get_running_loop", return_value=mock_loop):
        screen.on_ack(ack)
    screen.set_timer.assert_called_once_with(0.8, screen._ack_refresh)


# ══════════════════════════════════════════════════════════════════════════════
#  CLI SUBPARSER FRAMEWORK
# ══════════════════════════════════════════════════════════════════════════════

def test_cli_default_no_subcommand():
    """Default invocation with no arguments parses with subcommand=None and command=None."""
    parser = app_module.build_parser()
    args = parser.parse_args([])
    assert args.subcommand is None
    assert args.command is None
    assert args.paper is False
    assert args.debug is False


def test_cli_default_with_global_flags():
    """Global flags work correctly when no subcommand is specified."""
    parser = app_module.build_parser()
    args = parser.parse_args(["--paper", "--profile", "test_profile", "--debug", "--log-level", "INFO", "--symbol", "SBIN"])
    assert args.subcommand is None
    assert args.command is None
    assert args.paper is True
    assert args.profile == "test_profile"
    assert args.debug is True
    assert args.log_level == "INFO"
    assert args.symbol == "SBIN"


def test_cli_analyze_valid():
    """sktui analyze <symbol> parses symbol and optional period/compare."""
    parser = app_module.build_parser()
    args = parser.parse_args(["analyze", "RELIANCE", "--period", "6m", "--indicators", "RSI,MACD", "--compare", "TCS"])
    assert args.subcommand == "analyze"
    assert args.command == "analyze"
    assert args.symbol == "RELIANCE"
    assert args.period == "6m"
    assert args.indicators == "RSI,MACD"
    assert args.compare == "TCS"


def test_cli_analyze_missing_symbol_fails():
    """sktui analyze without symbol raises SystemExit."""
    parser = app_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["analyze"])


def test_cli_pairs_valid():
    """sktui pairs parses optional sector, min-corr, symbols, and output."""
    parser = app_module.build_parser()
    args = parser.parse_args(["pairs", "--sector", "BANK", "--min-corr", "0.85", "--symbols", "HDFCBANK", "ICICIBANK", "--output", "pairs.json"])
    assert args.subcommand == "pairs"
    assert args.command == "pairs"
    assert args.sector == "BANK"
    assert args.min_corr == 0.85
    assert args.symbols == ["HDFCBANK", "ICICIBANK"]
    assert args.output == "pairs.json"


def test_cli_signals_valid():
    """sktui signals parses symbols, filter, and min-conf / min-confidence."""
    parser = app_module.build_parser()
    args = parser.parse_args(["signals", "--symbols", "TCS", "INFY", "--filter", "BUY", "--min-conf", "75.0"])
    assert args.subcommand == "signals"
    assert args.command == "signals"
    assert args.symbols == ["TCS", "INFY"]
    assert args.filter == "BUY"
    assert args.min_conf == 75.0
    assert args.min_confidence == 75.0


def test_cli_signals_min_confidence_alias():
    """sktui signals supports --min-confidence alias identically to --min-conf."""
    parser = app_module.build_parser()
    args = parser.parse_args(["signals", "--min-confidence", "80.0"])
    assert args.min_conf == 80.0
    assert args.min_confidence == 80.0


def test_cli_signals_invalid_filter_fails():
    """sktui signals with invalid filter choice raises SystemExit."""
    parser = app_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["signals", "--filter", "INVALID_DIRECTION"])


def test_cli_backtest_valid():
    """sktui backtest parses strategy, symbol, capital, period, and friction rates."""
    parser = app_module.build_parser()
    args = parser.parse_args(["backtest", "--strategy", "sma", "--symbol", "TCS", "--capital", "500000", "--period", "2y", "--commission", "0.0005", "--slippage", "0.0001"])
    assert args.subcommand == "backtest"
    assert args.command == "backtest"
    assert args.strategy == "sma"
    assert args.symbol == "TCS"
    assert args.capital == 500000.0
    assert args.period == "2y"
    assert args.commission == 0.0005
    assert args.slippage == 0.0001


def test_cli_backtest_missing_required_fails():
    """sktui backtest without strategy or symbol raises SystemExit."""
    parser = app_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["backtest", "--strategy", "sma"])
    with pytest.raises(SystemExit):
        parser.parse_args(["backtest", "--symbol", "TCS"])


def test_cli_bot_valid():
    """sktui bot parses strategy, symbol, paper flag, and config path."""
    parser = app_module.build_parser()
    args = parser.parse_args(["bot", "--strategy", "pmm", "--symbol", "RELIANCE", "--paper", "--config", "bot.yaml"])
    assert args.subcommand == "bot"
    assert args.command == "bot"
    assert args.strategy == "pmm"
    assert args.symbol == "RELIANCE"
    assert args.paper is True
    assert args.config == "bot.yaml"


def test_cli_bot_missing_required_fails():
    """sktui bot without symbol or strategy raises SystemExit."""
    parser = app_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bot", "--strategy", "pmm"])


def test_cli_verify_valid():
    """sktui verify parses sandbox flag, no-sandbox, endpoint, and verbose."""
    parser = app_module.build_parser()
    args = parser.parse_args(["verify", "--sandbox", "--verbose", "--endpoint", "https://api.sharekhan.com"])
    assert args.subcommand == "verify"
    assert args.command == "verify"
    assert args.sandbox is True
    assert args.verbose is True
    assert args.endpoint == "https://api.sharekhan.com"

    args_no_sb = parser.parse_args(["verify", "--no-sandbox"])
    assert args_no_sb.sandbox is False


def test_cli_main_handlers_execution(capsys):
    """Verify main(argv) executes each headless subcommand returning 0."""
    assert app_module.main(["analyze", "TCS"]) == 0
    assert app_module.main(["pairs", "--min-corr", "0.75"]) == 0
    assert app_module.main(["signals", "--symbols", "INFY"]) == 0
    assert app_module.main(["backtest", "--strategy", "sma", "--symbol", "RELIANCE"]) == 0
    assert app_module.main(["bot", "--strategy", "arbitrage", "--symbol", "ONGC"]) == 0
    assert app_module.main(["verify", "--sandbox"]) == 0


def test_cli_bot_honors_sktui_paper_env(capsys, monkeypatch):
    """Verify sktui bot honors SKTUI_PAPER=1 environment variable."""
    # 1. Without env and without --paper -> LIVE
    monkeypatch.delenv("SKTUI_PAPER", raising=False)
    assert app_module.main(["bot", "--strategy", "pmm", "--symbol", "RELIANCE"]) == 0
    captured = capsys.readouterr()
    assert "Mode            : LIVE" in captured.out

    # 2. With SKTUI_PAPER=1 without --paper -> PAPER (SANDBOX)
    monkeypatch.setenv("SKTUI_PAPER", "1")
    assert app_module.main(["bot", "--strategy", "pmm", "--symbol", "RELIANCE"]) == 0
    captured = capsys.readouterr()
    assert "Mode            : PAPER (SANDBOX)" in captured.out

    # 3. Explicit --paper flag always enables paper mode even without env
    monkeypatch.delenv("SKTUI_PAPER", raising=False)
    assert app_module.main(["bot", "--strategy", "pmm", "--symbol", "RELIANCE", "--paper"]) == 0
    captured = capsys.readouterr()
    assert "Mode            : PAPER (SANDBOX)" in captured.out

    # 4. SKTUI_PAPER=0 should not enable paper mode
    monkeypatch.setenv("SKTUI_PAPER", "0")
    assert app_module.main(["bot", "--strategy", "pmm", "--symbol", "RELIANCE"]) == 0
    captured = capsys.readouterr()
    assert "Mode            : LIVE" in captured.out


def test_cli_bot_subprocess_honors_sktui_paper_env():
    """Verify executing python -m sktui bot in subprocess honors SKTUI_PAPER=1."""
    env = {**os.environ, "SKTUI_PAPER": "1"}
    res = subprocess.run(
        [sys.executable, "-m", "sktui", "bot", "--strategy", "pmm", "--symbol", "RELIANCE"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode == 0
    assert "Mode            : PAPER (SANDBOX)" in res.stdout


def test_cli_main_validation_errors():
    """Verify main(argv) validates inputs and returns 1 on bad parameters."""
    assert app_module.main(["pairs", "--min-corr", "2.0"]) == 1
    assert app_module.main(["backtest", "--strategy", "sma", "--symbol", "INFY", "--capital", "-1000"]) == 1


def test_cli_main_default_launches_skapp():
    """Verify calling main([]) with no subcommands instantiates and runs SKApp."""
    with patch.object(app_module.SKApp, "run", return_value=None) as mock_run:
        exit_code = app_module.main([])
        assert exit_code == 0
        mock_run.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
#  TUI SLASH COMMAND REGISTRY & DISPATCH
# ══════════════════════════════════════════════════════════════════════════════

REQUIRED_SLASH_COMMANDS = [
    "/quant",
    "/analyze",
    "/pair",
    "/spread",
    "/signal",
    "/backtest",
    "/bot",
    "/verify",
]


def test_all_8_slash_commands_in_config():
    """All 8 required commands must exist in config.SLASH_COMMANDS with non-empty help and token."""
    for cmd in REQUIRED_SLASH_COMMANDS:
        assert cmd in SLASH_COMMANDS, f"{cmd} missing from config.SLASH_COMMANDS"
        desc, token = SLASH_COMMANDS[cmd]
        assert isinstance(desc, str) and len(desc.strip()) > 0, f"{cmd} missing description"
        assert isinstance(token, str) and len(token.strip()) > 0, f"{cmd} missing action token"


def test_all_8_slash_commands_in_main_screen_all_commands():
    """All 8 required commands must be in MainScreen.ALL_COMMANDS for suggestion chips."""
    for cmd in REQUIRED_SLASH_COMMANDS:
        assert cmd in MainScreen.ALL_COMMANDS, f"{cmd} missing from MainScreen.ALL_COMMANDS"


def test_main_screen_slash_command_actions_exist():
    """MainScreen must define action methods for all 8 slash commands."""
    expected_actions = [
        "action_quant",
        "action_analyze",
        "action_pair_screener",
        "action_spread_analysis",
        "action_signal_scanner",
        "action_backtest",
        "action_bot_manager",
        "action_verify_broker",
    ]
    for action_name in expected_actions:
        assert hasattr(MainScreen, action_name), f"MainScreen missing method {action_name}"
        assert callable(getattr(MainScreen, action_name))


def test_main_screen_dispatch_slash_routes_all_8_commands(tmp_path: Path, monkeypatch):
    """_dispatch_slash must route each of the 8 commands to its action handler without raising."""
    monkeypatch.setattr("sktui.config.CONF", tmp_path)
    monkeypatch.setattr("sktui.config.DATA", tmp_path)
    monkeypatch.setattr("sktui.config.WATCH_FILE", tmp_path / "w.json")
    monkeypatch.setattr("sktui.config.ALERTS_FILE", tmp_path / "a.json")

    mock_app = MagicMock()
    monkeypatch.setattr(MainScreen, "app", property(lambda self: mock_app))

    screen = MainScreen()

    for cmd in REQUIRED_SLASH_COMMANDS:
        # Must execute cleanly without unhandled exception or status error
        screen._dispatch_slash(cmd)


def test_main_screen_dispatch_slash_with_args(tmp_path: Path, monkeypatch):
    """_dispatch_slash supports command arguments when invoked from cmd input."""
    monkeypatch.setattr("sktui.config.CONF", tmp_path)
    monkeypatch.setattr("sktui.config.DATA", tmp_path)
    monkeypatch.setattr("sktui.config.WATCH_FILE", tmp_path / "w.json")
    monkeypatch.setattr("sktui.config.ALERTS_FILE", tmp_path / "a.json")

    mock_app = MagicMock()
    monkeypatch.setattr(MainScreen, "app", property(lambda self: mock_app))

    screen = MainScreen()

    screen._dispatch_slash("/analyze", arg="RELIANCE")
    screen._dispatch_slash("/backtest", arg="sma")
    screen._dispatch_slash("/spread", arg="RELIANCE-TCS")
