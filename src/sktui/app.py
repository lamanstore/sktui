#!/usr/bin/env python3
"""SKTUI - Professional Terminal Trading CLI for Mirae Asset Sharekhan API."""
from __future__ import annotations

import argparse
import os

from textual.app import App

from sktui import api
from sktui.config import (
    C_AMBER, C_BG, C_BORDER, C_CYAN, C_DIM, C_GREEN, C_MUTED, C_PANEL, C_RED,
    C_SUBTLE, C_TEXT, C_DARK, C_NAVY, C_TEAL, CASH, CONF, CONFIG_FILE, DATA,
    EXCH_NAMES, INTERVALS, INTERVAL_LABELS, PRODUCTS, SESSION_FILE,
    SLASH_COMMANDS, VALIDITIES, WATCH_FILE,
)
from sktui.screens.login import LOGIN_LOGO, LoginScreen
from sktui.screens.main import MainScreen
from sktui.screens.modals import (
    Confirm, DetailScreen, HelpScreen, HistoryScreen, OrderTicket, ProductsScreen,
    QuoteScreen, RiskScreen, SymbolSearch, SystemStatusScreen, WhatIfScreen,
)
from sktui.styles import CSS
from sktui.utils import (
    build_order, cell, dec, expiry_key, fill_table, fmt, get, human, is_open_order,
    norm_expiry, normalize_scrip, order_summary, read_json, scrip_label, sign_style,
    strike_str, write_private,
)


class SKApp(App):
    TITLE     = "SKTUI  \u00b7  Sharekhan Terminal"
    SUB_TITLE = "Mirae Asset  \u00b7  Professional Trading CLI"
    CSS       = CSS

    # Responsive size classes applied to every Screen on resize (see styles.py).
    HORIZONTAL_BREAKPOINTS = [(0, "-xs"), (80, "-sm"), (110, "-md"), (150, "-lg"), (200, "-xl")]
    VERTICAL_BREAKPOINTS   = [(0, "-short"), (30, "-medium"), (45, "-tall")]

    def __init__(self, paper: bool = False) -> None:
        super().__init__()
        self.paper       = paper
        self.client:     api.Client | None = None
        self.raw_ticks:  dict[str, dict]   = {}
        self.enable_feed = True

    def on_mount(self) -> None:
        self.push_screen(LoginScreen())


def main() -> None:
    import sys
    import traceback
    from datetime import datetime
    from sktui.services.logger import setup_logger
    from sktui.config_manager import config_manager

    logger = setup_logger()
    logger.info("Starting SKTUI workstation session")

    ap = argparse.ArgumentParser(
        description="SKTUI — professional terminal trading CLI for Mirae Asset Sharekhan"
    )
    ap.add_argument("--paper", action="store_true",
                    help="dry-run: simulate orders, never execute live")
    ap.add_argument("--profile", default=os.environ.get("SKTUI_PROFILE", "default"),
                    help="configuration profile (e.g. default, live, paper)")
    ap.add_argument("--debug", action="store_true",
                    help="enable verbose debug logging and Textual devtools")
    args = ap.parse_args()

    # Run startup validation via ConfigManager
    profile, validation_warnings = config_manager.startup_validation_report(args.profile)
    for warn in validation_warnings:
        logger.warning("Config validation: %s", warn)

    # Resolve paper mode from profile, flag, or env
    is_paper = args.paper or profile.paper or args.profile == "paper" or os.environ.get("SKTUI_PAPER") == "1"
    os.environ["SKTUI_PROFILE"] = args.profile

    if args.debug:
        os.environ["TEXTUAL_DEBUG"] = "1"
        logger.setLevel("DEBUG")

    logger.info("Profile: %s  Paper: %s  Debug: %s", args.profile, is_paper, args.debug)
    if validation_warnings:
        logger.warning("Startup config issues: %d warning(s)", len(validation_warnings))

    app = SKApp(paper=is_paper)
    try:
        app.run()
    except Exception as e:
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_file = DATA / f"crash_{now_str}.log"
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            with open(crash_file, "w", encoding="utf-8") as f:
                f.write(f"SKTUI CRASH REPORT — {datetime.now().isoformat()}\n")
                f.write(f"Python: {sys.version}\n")
                f.write(f"Profile: {args.profile} (Paper: {is_paper}, Debug: {args.debug})\n\n")
                traceback.print_exc(file=f)
            logger.error("Uncaught exception in SKTUI runtime. Crash dump written to %s", crash_file, exc_info=True)
            print(f"\n[!] SKTUI encountered an unexpected error: {e}", file=sys.stderr)
            print(f"[!] Crash report written to: {crash_file}\n", file=sys.stderr)
        except Exception:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
