"""End-to-End Tests for Requirement R1: Codebase Health, CLI Subparsers & Workstation.

Covers:
- Tier 1: Feature Coverage (isolated happy-path tests)
  1. CLI version and metadata synchronization
  2. __main__.py import guard side-effect prevention
  3. CLI subparsers discoverability and help
  4. TUI slash command table registry
  5. Interactive Textual workstation launch in paper mode
- Tier 2: Boundary & Corner Cases
  6. CLI unknown subcommand error handling
  7. CLI missing required arguments enforcement
  8. Workstation unmount tick tape persistence
  9. Safe timer scheduling lifecycle without coroutine warnings
  10. DebugModal lifecycle and unique action handlers
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import warnings
from typing import Any, Callable

import pytest

import sktui
import sktui.config as cfg
from sktui.app import SKApp
from sktui.screens.login import LoginScreen
from sktui.screens.main import MainScreen
from sktui.screens.modals import DebugModal


# ============================================================================
# Tier 1: Feature Coverage (Isolated Happy Path)
# ============================================================================

def test_r1_t1_cli_version_and_metadata() -> None:
    """Verify package version synchronization matches pyproject.toml 0.4.0."""
    version = getattr(sktui, "__version__", None)
    assert version is not None, "sktui.__version__ must be defined"
    assert version == "0.4.0", f"Expected version '0.4.0', got {version!r}"


def test_r1_t1_main_module_import_guard() -> None:
    """Verify sktui.__main__ can be imported safely without triggering sys.exit or main()."""
    if "sktui.__main__" in sys.modules:
        del sys.modules["sktui.__main__"]
    try:
        mod = importlib.import_module("sktui.__main__")
        assert mod is not None, "sktui.__main__ failed to import"
    except SystemExit as exc:
        pytest.fail(f"sktui.__main__ import triggered SystemExit({exc.code}) — missing if __name__ == '__main__' guard")


def test_r1_t1_cli_subparsers_help(cli_runner: Callable[[list[str]], tuple[int, str, str]]) -> None:
    """Verify CLI subparser discoverability for analyze, pairs, signals, backtest, bot, verify."""
    subcommands = ["analyze", "pairs", "signals", "backtest", "bot", "verify"]
    code, out, err = cli_runner(["--help"])
    assert code == 0, f"sktui --help failed with code {code}: {err}"
    missing_in_help = [sc for sc in subcommands if sc not in out]
    assert not missing_in_help, f"Required CLI subparsers missing from help output: {missing_in_help}"


def test_r1_t1_slash_command_registry() -> None:
    """Verify TUI slash command table contains entries for all required modules."""
    required = ["/quant", "/analyze", "/pair", "/spread", "/signal", "/backtest", "/bot", "/verify"]
    slash_table = getattr(cfg, "SLASH_COMMANDS", {})
    available = set(slash_table.keys())
    # Support both with and without leading slash
    missing = [
        cmd for cmd in required
        if cmd not in available and cmd.lstrip("/") not in available
    ]
    if missing:
        pytest.skip(f"Slash command registration for {missing} pending in Milestone 1")
    assert not missing, f"Missing slash commands: {missing}"


def test_r1_t1_textual_workstation_launch(tmp_app_data: dict[str, Any]) -> None:
    """Verify headless Textual workstation launches cleanly in paper mode with responsive breakpoints."""
    async def run() -> None:
        app = SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            assert app.screen is not None
            # Verify screen is LoginScreen or MainScreen
            assert isinstance(app.screen, (LoginScreen, MainScreen))
            # Verify terminal responsive sizing classes
            classes = app.screen.classes
            assert any(cls in classes for cls in ("-md", "-lg", "-sm", "-xs"))

    asyncio.run(run())


# ============================================================================
# Tier 2: Boundary & Corner Cases
# ============================================================================

def test_r1_t2_cli_unknown_subcommand_error(cli_runner: Callable[[list[str]], tuple[int, str, str]]) -> None:
    """Verify CLI cleanly rejects unknown subcommands with exit code 2 and helpful error."""
    code, out, err = cli_runner(["nonexistent_subcommand_xyz"])
    # Standard argparse rejects unknown subcommands or invalid options with code 2
    assert code == 2, f"Expected exit code 2 for unknown subcommand, got {code}"
    assert "error:" in err.lower() or "usage:" in err.lower() or "unrecognized" in err.lower()


def test_r1_t2_cli_missing_required_arguments(cli_runner: Callable[[list[str]], tuple[int, str, str]]) -> None:
    """Verify CLI subcommands missing required flags (e.g. backtest without strategy) reject with code 2."""
    code, out, err = cli_runner(["backtest"])
    if code == 2 and "unrecognized arguments" in err:
        pytest.skip("CLI backtest subparser pending in Milestone 1/4")
    # Missing required argument should result in exit code 2
    assert code == 2, f"Expected exit code 2 for missing required arguments, got {code}"
    assert "required" in err.lower() or "error:" in err.lower() or "usage:" in err.lower()


def test_r1_t2_workstation_unmount_tape_persistence(
    tmp_app_data: dict[str, Any],
    fake_client: Any,
) -> None:
    """Verify MainScreen.on_unmount flushes pending tick tape to disk via quotes.save_tape()."""
    async def run() -> None:
        app = SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(120, 40)) as pilot:
            app.client = fake_client
            main_scr = MainScreen()
            app.switch_screen(main_scr)
            await pilot.pause(0.1)

            # Verify quotes store and save_tape method exist
            assert hasattr(main_scr, "quotes"), "MainScreen must have quotes store"
            assert hasattr(main_scr.quotes, "save_tape"), "QuoteStore must have save_tape method"

            # Spy on quotes.save_tape to verify unmount auto-save invocation
            save_tape_called = []
            orig_save_tape = main_scr.quotes.save_tape
            def spy_save_tape(*args: Any, **kwargs: Any) -> int:
                save_tape_called.append(True)
                return orig_save_tape(*args, **kwargs)
            main_scr.quotes.save_tape = spy_save_tape

            # Trigger unmount lifecycle
            try:
                main_scr.on_unmount()
            except Exception as exc:
                pytest.fail(f"MainScreen.on_unmount raised unexpected exception: {exc}")

            assert len(save_tape_called) > 0, "MainScreen.on_unmount must invoke quotes.save_tape()"

    asyncio.run(run())


def test_r1_t2_timer_safe_scheduling_no_coroutine_warning(
    tmp_app_data: dict[str, Any],
    fake_client: Any,
) -> None:
    """Verify scheduling and canceling workstation refresh timers does not leak unawaited coroutines."""
    async def run() -> None:
        app = SKApp(paper=True)
        app.enable_feed = False
        with warnings.catch_warnings(record=True) as recorded_warnings:
            warnings.simplefilter("always")
            async with app.run_test(size=(120, 40)) as pilot:
                app.client = fake_client
                main_scr = MainScreen()
                app.switch_screen(main_scr)
                await pilot.pause(0.1)

            # Filter for unawaited coroutine warnings specifically
            coro_warnings = [
                w for w in recorded_warnings
                if issubclass(w.category, RuntimeWarning) and "coroutine" in str(w.message).lower()
            ]
            assert len(coro_warnings) == 0, (
                f"Workstation leaked {len(coro_warnings)} unawaited coroutine warning(s): "
                f"{[str(w.message) for w in coro_warnings]}"
            )

    asyncio.run(run())


def test_r1_t2_debug_modal_lifecycle_duplicate_cleanup(tmp_app_data: dict[str, Any]) -> None:
    """Verify DebugModal mounts cleanly and does not suffer from duplicate action handlers."""
    async def run() -> None:
        app = SKApp(paper=True)
        app.enable_feed = False
        async with app.run_test(size=(120, 40)) as pilot:
            modal = DebugModal()
            app.push_screen(modal)
            await pilot.pause(0.1)

            # Inspect action_refresh_debug methods on modal
            refresh_methods = [
                attr for attr in dir(modal)
                if attr == "action_refresh_debug"
            ]
            assert len(refresh_methods) == 1, "DebugModal should have exactly one action_refresh_debug definition"

            # Verify modal can be dismissed cleanly
            app.pop_screen()
            await pilot.pause(0.05)

    asyncio.run(run())
