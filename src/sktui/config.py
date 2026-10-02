"""Configuration tokens, paths, constants, and command registries for SKTUI."""
from __future__ import annotations

import os
from pathlib import Path

# ── Design tokens ──────────────────────────────────────────────────────────────
C_CYAN   = "#00f0ff"
C_GREEN  = "#10b981"
C_RED    = "#ef4444"
C_AMBER  = "#f59e0b"
C_DIM    = "#71717a"
C_PANEL  = "#18181b"
C_BG     = "#09090b"
C_BORDER = "#1a1a20"
C_TEXT   = "#e4e4e7"
C_MUTED  = "#a1a1aa"
C_SUBTLE = "#52525b"

# ── Storage paths ──────────────────────────────────────────────────────────────
CONF         = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "sktui"
DATA         = Path(os.environ.get("XDG_DATA_HOME",   Path.home() / ".local/share")) / "sktui"
CONFIG_FILE  = CONF / "config.json"
SESSION_FILE = DATA / "session.json"
WATCH_FILE   = CONF / "watchlist.json"

EXCH_NAMES = {"NC": "NSE Equity", "BC": "BSE Equity", "NF": "NSE F&O",
              "RN": "NSE Currency", "MX": "MCX"}
CASH       = ("NC", "BC")
PRODUCTS   = ["INVESTMENT", "BIGTRADE", "BIGTRADE+"]
VALIDITIES = ["GFD", "MyGTD", "IOC"]
INTERVALS  = ["1minute", "3minute", "5minute", "10minute", "15minute", "30minute",
              "60minute", "90minute", "daily", "weekly", "monthly",
              "quarterly", "halfyearly", "yearly"]

# ── Slash command registry ─────────────────────────────────────────────────────
SLASH_COMMANDS: dict[str, tuple[str, str]] = {
    "/dashboard":  ("Open portfolio + market overview",       "tab:watch"),
    "/watchlist":  ("Manage watchlist symbols",               "tab:watch"),
    "/orders":     ("View and manage orders",                 "tab:orders"),
    "/positions":  ("View open positions",                    "tab:positions"),
    "/holdings":   ("View holdings",                          "tab:holdings"),
    "/funds":      ("View funds & margin",                    "tab:funds"),
    "/activity":   ("View activity & audit log",              "tab:activity"),
    "/buy":        ("Prepare a BUY order (select symbol first)", "trade:B"),
    "/sell":       ("Prepare a SELL order (select symbol first)", "trade:S"),
    "/cancel":     ("Cancel selected open order",             "cancel_order"),
    "/modify":     ("Modify selected order",                  "modify"),
    "/chart":      ("Open price chart for selected symbol",   "chart"),
    "/quote":      ("Live quote for selected symbol",         "quote"),
    "/products":   ("Browse markets & product links",         "products"),
    "/whatif":     ("Simulate order impact (read-only)",      "whatif"),
    "/risk":       ("Risk dashboard & safety controls",       "risk"),
    "/status":     ("System & broker health status",          "status"),
    "/help":       ("Full command reference & key bindings",  "help"),
    "/feed":       ("Toggle live WebSocket feed log",         "toggle_log"),
    "/refresh":    ("Refresh all account data",               "refresh_all"),
    "/kill":       ("EMERGENCY: block new automated orders",  "kill"),
    "/logout":     ("Log out and clear session",              "logout"),
}

TICK_MAP = {"ltp": "ltp", "chg": "rsChange", "pct": "perChange",
            "bid": "bidPrice", "ask": "offPrice", "vol": "qty"}

HIST_COLS = [("tradeDate", "Date"), ("tradeTime", "Time"),
             ("open", "Open"), ("high", "High"), ("low", "Low"),
             ("close", "Close"), ("volume", "Volume")]
