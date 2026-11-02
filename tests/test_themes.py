"""Comprehensive tests for SKTUI dynamic theme engine, TCSS variables, Rich palettes, and ThemeModal."""
from __future__ import annotations

import asyncio
from rich.style import Style
from textual.command import CommandPalette
from textual.widgets import DataTable, Input, Static

from sktui import app as sk
from sktui.api import Client
from sktui.chart import aggregate_to_candles, render_candlestick_chart, render_chart, render_volume_bars
from sktui.screens.modals import HistoryScreen, OrderTicket, ThemeModal
from sktui.themes import (
    DEFAULT_THEME,
    SKTUI_THEME_MAP,
    current_palette,
    load_configured_theme,
    save_configured_theme,
)
from sktui.utils import read_json, write_private


class _DummyClient(Client):
    def __init__(self) -> None:
        super().__init__(
            "k", "tok", "272616", "LOGIN1",
            exchanges=["NC", "BC", "NF", "MX"], paper=True,
        )

    def orders(self):
        return [
            {
                "orderId": "101",
                "scripCode": 2475,
                "tradingSymbol": "ONGC",
                "exchange": "NC",
                "buySell": "B",
                "orderQty": 10,
                "execQty": 0,
                "orderPrice": "250.50",
                "orderStatus": "Pending",
                "priceType": "LIMIT",
            }
        ]

    def positions(self):
        return [
            {
                "tradingSymbol": "ONGC",
                "exchange": "NC",
                "scripCode": 2475,
                "productType": "INVESTMENT",
                "netQty": 10,
                "avgPrice": 245.0,
                "bpl": 120.0,
                "mtm": 55.0,
            }
        ]

    def holdings(self):
        return [{"tradingSymbol": "IOC", "exchange": "NC", "aval": "5", "holdPrice": "165.0"}]

    def funds(self, exchange):
        return [{"customerId": 1, "currentCashBalance": 500000.0}]

    def historical(self, e, c, i):
        return [
            {
                "open": 240 + idx,
                "high": 243 + idx,
                "low": 239 + idx,
                "close": 242 + idx,
                "qty": 1000 * (idx + 1),
                "tradeDate": "18/01/2026",
                "tradeTime": f"09:{15 + idx:02d}:00",
            }
            for idx in range(12)
        ]


def test_all_custom_and_builtin_palettes_valid_rich_styles():
    """Every registered custom and Textual built-in theme (including ansi-*) resolves valid Rich colors."""
    app = sk.SKApp(paper=True)
    for custom_name in (
        "sktui-obsidian",
        "sktui-bloomberg",
        "sktui-emerald",
        "sktui-midnight",
        "sktui-daylight",
    ):
        assert custom_name in app.available_themes

    assert len(app.available_themes) >= 20

    for theme_name in list(app.available_themes.keys()):
        app.theme = theme_name
        p = current_palette()
        assert p.name == theme_name
        assert p.dark == bool(app.current_theme.dark)

        # Ensure every color token parses cleanly in Rich without ColorParseError
        for hex_token in (
            p.bg, p.surface, p.panel, p.fg, p.fg_strong, p.muted, p.subtle,
            p.divider, p.primary, p.secondary, p.accent, p.bull, p.bear,
            p.warn, p.teal, p.on_primary, p.on_secondary, p.on_bull,
            p.on_bear, p.on_warn, p.primary_tint, *p.bull_grad, *p.bear_grad,
        ):
            assert hex_token.startswith("#") and len(hex_token) == 7, f"{theme_name}: {hex_token}"
            Style.parse(f"bold {hex_token} on {p.bg}")

        if not p.dark:
            # Light themes must never use white strong text on light surfaces
            assert p.fg_strong != "#ffffff"


def test_theme_persistence_preserves_credentials_and_permissions(tmp_path, monkeypatch):
    monkeypatch.delenv("SKTUI_THEME", raising=False)
    cfg = tmp_path / "config.json"
    write_private(cfg, {"api_key": "AK_99", "secret": "SEC_99", "version": "1005"})

    assert load_configured_theme(cfg) == DEFAULT_THEME

    save_configured_theme("sktui-bloomberg", cfg)
    assert load_configured_theme(cfg) == "sktui-bloomberg"

    raw = read_json(cfg, {})
    assert raw["api_key"] == "AK_99"
    assert raw["secret"] == "SEC_99"
    assert raw["theme"] == "sktui-bloomberg"
    assert (cfg.stat().st_mode & 0o777) == 0o600

    # Environment variable override takes precedence
    monkeypatch.setenv("SKTUI_THEME", "sktui-daylight")
    assert load_configured_theme(cfg) == "sktui-daylight"


def test_login_screen_theme_switching_and_command_palette(tmp_path, monkeypatch):
    monkeypatch.setattr(sk, "SESSION_FILE", tmp_path / "no_session.json")
    monkeypatch.setattr("sktui.screens.login.SESSION_FILE", tmp_path / "no_session.json")
    monkeypatch.setattr("sktui.screens.login.CONFIG_FILE", tmp_path / "cfg.json")

    async def run() -> None:
        app = sk.SKApp(paper=True, initial_theme="sktui-obsidian")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            scr = app.screen
            assert type(scr).__name__ == "LoginScreen"
            scr._show_public_ip("198.51.100.42")
            scr.msg("Gateway ready")

            # Switch to light theme and ansi themes dynamically on LoginScreen
            app.theme = "sktui-daylight"
            await pilot.pause()
            assert current_palette().name == "sktui-daylight"
            assert not current_palette().dark
            assert "-light-mode" in app.classes

            app.theme = "ansi-dark"
            await pilot.pause()
            assert current_palette().name == "ansi-dark"

            app.theme = "ansi-light"
            await pilot.pause()
            assert current_palette().name == "ansi-light"

            # Ctrl+P opens Textual's built-in CommandPalette on LoginScreen
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert isinstance(app.screen, CommandPalette)
            await pilot.press("escape")
            await pilot.pause()
            assert type(app.screen).__name__ == "LoginScreen"

            # Ctrl+T opens ThemeModal on LoginScreen
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert isinstance(app.screen, ThemeModal)
            await pilot.press("escape")
            await pilot.pause()
            assert type(app.screen).__name__ == "LoginScreen"

    asyncio.run(run())


def test_main_screen_live_theme_switching_and_slash_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(sk, "DATA", tmp_path)
    monkeypatch.setattr(sk, "WATCH_FILE", tmp_path / "watch.json")

    async def run() -> None:
        app = sk.SKApp(paper=True, initial_theme="sktui-obsidian")
        app.enable_feed = False
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            app.client = _DummyClient()
            app.switch_screen(sk.MainScreen())
            await pilot.pause(0.4)
            scr = app.screen
            assert app.theme == "sktui-obsidian"

            # Parameterized /theme bloomberg (short alias)
            cmd_in = scr.query_one("#cmd-input", Input)
            cmd_in.focus()
            cmd_in.value = "/theme bloomberg"
            await pilot.press("enter")
            await pilot.pause()
            assert app.theme == "sktui-bloomberg"
            assert current_palette().primary == "#ff9900"

            preview_render = scr.query_one("#order-preview", Static).content
            assert "#ff9900" in str(preview_render.spans)

            # Switch to institutional light mode via /theme sktui-daylight
            cmd_in.focus()
            cmd_in.value = "/theme sktui-daylight"
            await pilot.press("enter")
            await pilot.pause()
            assert app.theme == "sktui-daylight"
            assert current_palette().dark is False
            assert "-light-mode" in app.classes
            preview_light = scr.query_one("#order-preview", Static).content
            assert "#ffffff" not in [
                s.style for s in preview_light.spans if "STAGE" not in preview_light.plain[s.start:s.end]
                and "SELL" not in preview_light.plain[s.start:s.end]
            ]

            # Built-in Textual theme via /theme nord
            cmd_in.focus()
            cmd_in.value = "/theme nord"
            await pilot.press("enter")
            await pilot.pause()
            assert app.theme == "nord"
            assert current_palette().name == "nord"

            # Unknown theme leaves current theme intact and shows status error
            cmd_in.focus()
            cmd_in.value = "/theme unknown-theme-xyz"
            await pilot.press("enter")
            await pilot.pause()
            assert app.theme == "nord"

    asyncio.run(run())


def test_theme_modal_live_preview_apply_and_escape_revert(tmp_path, monkeypatch):
    monkeypatch.setattr(sk, "DATA", tmp_path)
    monkeypatch.setattr(sk, "WATCH_FILE", tmp_path / "watch.json")

    async def run() -> None:
        app = sk.SKApp(paper=True, initial_theme="sktui-obsidian")
        app.enable_feed = False
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            app.client = _DummyClient()
            app.switch_screen(sk.MainScreen())
            await pilot.pause(0.3)

            # Open ThemeModal with Ctrl+T
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert isinstance(app.screen, ThemeModal)
            tbl = app.screen.query_one("#theme-table", DataTable)
            assert tbl.row_count >= len(SKTUI_THEME_MAP)

            # Arrow down previews next theme live
            await pilot.press("down")
            await pilot.pause()
            assert app.theme == "sktui-bloomberg"
            assert current_palette().name == "sktui-bloomberg"

            # Escape reverts back to initial theme (sktui-obsidian)
            await pilot.press("escape")
            await pilot.pause()
            assert type(app.screen).__name__ == "MainScreen"
            assert app.theme == "sktui-obsidian"
            assert current_palette().name == "sktui-obsidian"

            # Open via /theme, filter to emerald, press Enter to confirm
            cmd_in = app.screen.query_one("#cmd-input", Input)
            cmd_in.focus()
            cmd_in.value = "/theme"
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ThemeModal)

            flt = app.screen.query_one("#theme-filter", Input)
            flt.focus()
            flt.value = "sktui-emerald"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert type(app.screen).__name__ == "MainScreen"
            assert app.theme == "sktui-emerald"
            assert current_palette().name == "sktui-emerald"

    asyncio.run(run())


def test_modals_and_charts_adapt_to_active_theme(tmp_path, monkeypatch):
    monkeypatch.setattr(sk, "DATA", tmp_path)
    monkeypatch.setattr(sk, "WATCH_FILE", tmp_path / "watch.json")

    async def run() -> None:
        app = sk.SKApp(paper=True, initial_theme="sktui-daylight")
        app.enable_feed = False
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            app.client = _DummyClient()
            app.switch_screen(sk.MainScreen())
            await pilot.pause(0.4)

            # Charts render with active light theme palette cleanly
            prices = [240.0 + (i % 5) * 1.5 for i in range(24)]
            line_c = render_chart(prices, width=48, height=6)
            candles = aggregate_to_candles(prices, bar_size=3)
            candle_c = render_candlestick_chart(candles, width=48, height=8)
            vol_c = render_volume_bars(
                ["09:15", "09:16", "09:17", "09:18", "09:19"],
                [1200, 1800, 950, 2400, 3100],
                width=40,
            )
            assert len(line_c.plain) > 0
            assert len(candle_c.plain) > 0
            assert len(vol_c.plain) > 0

            # Open OrderTicket and switch theme while modal is open
            await pilot.press("b")
            await pilot.pause()
            assert isinstance(app.screen, OrderTicket)
            app.theme = "sktui-bloomberg"
            await pilot.pause()
            ticket_banner = app.screen.query_one("#order-quote-banner", Static).content
            pal_b = current_palette()
            assert pal_b.warn in str(ticket_banner.spans) or pal_b.bull in str(ticket_banner.spans)
            await pilot.press("escape")
            await pilot.pause()

            # Open HistoryScreen and switch theme while chart modal is open
            await pilot.press("c")
            await pilot.pause(0.5)
            assert isinstance(app.screen, HistoryScreen)
            app.theme = "sktui-midnight"
            await pilot.pause()
            assert current_palette().name == "sktui-midnight"
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(run())
