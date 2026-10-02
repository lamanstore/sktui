#!/usr/bin/env python3
"""SKTUI - Professional Terminal Trading CLI for Mirae Asset Sharekhan API."""
from __future__ import annotations

import argparse
import os

from textual.app import App

from sktui import api
from sktui.config import (
    C_AMBER, C_BG, C_BORDER, C_CYAN, C_DIM, C_GREEN, C_MUTED, C_PANEL, C_RED,
    C_SUBTLE, C_TEXT, CASH, CONF, CONFIG_FILE, DATA, EXCH_NAMES, INTERVALS,
    PRODUCTS, SESSION_FILE, SLASH_COMMANDS, VALIDITIES, WATCH_FILE,
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

    def __init__(self, paper: bool = False) -> None:
        super().__init__()
        self.paper       = paper
        self.client:     api.Client | None = None
        self.raw_ticks:  dict[str, dict]   = {}
        self.enable_feed = True

    def on_mount(self) -> None:
        self.push_screen(LoginScreen())


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SKTUI \u2014 professional terminal trading CLI for Mirae Asset Sharekhan")
    ap.add_argument("--paper", action="store_true",
                    help="dry-run: never send or cancel orders")
    args = ap.parse_args()
    SKApp(paper=args.paper or os.environ.get("SKTUI_PAPER") == "1").run()


if __name__ == "__main__":
    main()
