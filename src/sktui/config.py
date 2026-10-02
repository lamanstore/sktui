"""Configuration tokens, paths, constants, and command registries for SKTUI."""
from __future__ import annotations

import os
from pathlib import Path

# ── Design tokens ──────────────────────────────────────────────────────────────
C_CYAN   = "#00e5ff"
C_GREEN  = "#10b981"
C_RED    = "#ef4444"
C_AMBER  = "#f59e0b"
C_DIM    = "#475569"
C_PANEL  = "#0d1526"
C_BG     = "#060810"
C_BORDER = "#0f1929"
C_TEXT   = "#d4d4d8"
C_MUTED  = "#94a3b8"
C_SUBTLE = "#334155"

# Extended palette
C_BLUE   = "#3b82f6"
C_PURPLE = "#8b5cf6"
C_TEAL   = "#14b8a6"
C_LIME   = "#84cc16"
C_ORANGE = "#f97316"
C_PINK   = "#ec4899"
C_NAVY   = "#0a1f36"
C_DARK   = "#080c16"

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

# ── Interval display labels ───────────────────────────────────────────────────
INTERVAL_LABELS = {
    "1minute": "1m", "3minute": "3m", "5minute": "5m",
    "10minute": "10m", "15minute": "15m", "30minute": "30m",
    "60minute": "1h", "90minute": "90m", "daily": "1D",
    "weekly": "1W", "monthly": "1M", "quarterly": "3M",
    "halfyearly": "6M", "yearly": "1Y",
}

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
    "/add":        ("Add symbol to watchlist",                "add"),
    "/remove":     ("Remove symbol from watchlist",           "remove"),
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

HIST_COLS = [
    ("tradeDate", "Date"), ("tradeTime", "Time"),
    ("open", "  Open"), ("high", "  High"), ("low", "   Low"),
    ("close", " Close"), ("volume", "    Volume"),
]

# ── Fallback built-in scrips list for instant symbol search & paper mode ───────
BUILTIN_SCRIPS: dict[str, list[dict]] = {
    "NC": [
        {"scripCode": 15355, "tradingSymbol": "ASIANENE", "companyName": "Asian Energy Services Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 23481, "tradingSymbol": "ONGC", "companyName": "Oil and Natural Gas Corp Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 2885,  "tradingSymbol": "RELIANCE", "companyName": "Reliance Industries Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 11536, "tradingSymbol": "TCS", "companyName": "Tata Consultancy Services Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 1594,  "tradingSymbol": "INFY", "companyName": "Infosys Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 1333,  "tradingSymbol": "HDFCBANK", "companyName": "HDFC Bank Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 4963,  "tradingSymbol": "ICICIBANK", "companyName": "ICICI Bank Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 3045,  "tradingSymbol": "SBIN", "companyName": "State Bank of India", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 3456,  "tradingSymbol": "TATAMOTORS", "companyName": "Tata Motors Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 10940, "tradingSymbol": "BHARTIARTL", "companyName": "Bharti Airtel Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 1660,  "tradingSymbol": "ITC", "companyName": "ITC Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 1922,  "tradingSymbol": "KOTAKBANK", "companyName": "Kotak Mahindra Bank Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 11483, "tradingSymbol": "LT", "companyName": "Larsen & Toubro Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 1394,  "tradingSymbol": "HINDUNILVR", "companyName": "Hindustan Unilever Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 5900,  "tradingSymbol": "AXISBANK", "companyName": "Axis Bank Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 3787,  "tradingSymbol": "WIPRO", "companyName": "Wipro Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 10999, "tradingSymbol": "MARUTI", "companyName": "Maruti Suzuki India Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 3351,  "tradingSymbol": "SUNPHARMA", "companyName": "Sun Pharmaceutical Inds Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 3506,  "tradingSymbol": "TITAN", "companyName": "Titan Company Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 16675, "tradingSymbol": "BAJFINANCE", "companyName": "Bajaj Finance Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 21808, "tradingSymbol": "NIFTY50", "companyName": "Nifty 50 Index ETF", "lotSize": 1, "tickSize": 0.01, "instType": "EQ"},
    ],
    "BC": [
        {"scripCode": 500312, "tradingSymbol": "ONGC", "companyName": "Oil and Natural Gas Corp Ltd (BSE)", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 530355, "tradingSymbol": "ASIANENE", "companyName": "Asian Energy Services Ltd (BSE)", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 500325, "tradingSymbol": "RELIANCE", "companyName": "Reliance Industries Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 532540, "tradingSymbol": "TCS", "companyName": "Tata Consultancy Services Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 500182, "tradingSymbol": "HEROMOTOCO", "companyName": "Hero MotoCorp Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 500112, "tradingSymbol": "SBIN", "companyName": "State Bank of India", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 500209, "tradingSymbol": "INFY", "companyName": "Infosys Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 500180, "tradingSymbol": "HDFCBANK", "companyName": "HDFC Bank Ltd", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 500570, "tradingSymbol": "TATAMOTORS", "companyName": "Tata Motors Ltd (BSE)", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 532454, "tradingSymbol": "BHARTIARTL", "companyName": "Bharti Airtel Ltd (BSE)", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
        {"scripCode": 500875, "tradingSymbol": "ITC", "companyName": "ITC Ltd (BSE)", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
    ],
    "NF": [
        {"scripCode": 45001, "tradingSymbol": "NIFTY24OCTFUT", "companyName": "NIFTY 24 OCT FUT", "lotSize": 25, "tickSize": 0.05, "instType": "FUTIDX", "expiry": "24/10/2026"},
        {"scripCode": 45002, "tradingSymbol": "NIFTY25000CE", "companyName": "NIFTY 25000 CALL", "lotSize": 25, "tickSize": 0.05, "instType": "OPTIDX", "expiry": "24/10/2026", "strike": 25000, "optionType": "CE"},
        {"scripCode": 45003, "tradingSymbol": "NIFTY25000PE", "companyName": "NIFTY 25000 PUT", "lotSize": 25, "tickSize": 0.05, "instType": "OPTIDX", "expiry": "24/10/2026", "strike": 25000, "optionType": "PE"},
        {"scripCode": 45004, "tradingSymbol": "BANKNIFTYFUT", "companyName": "BANKNIFTY 24 OCT FUT", "lotSize": 15, "tickSize": 0.05, "instType": "FUTIDX", "expiry": "24/10/2026"},
        {"scripCode": 45005, "tradingSymbol": "RELIANCEOCTFUT", "companyName": "RELIANCE 24 OCT FUT", "lotSize": 250, "tickSize": 0.05, "instType": "FUTSTK", "expiry": "24/10/2026"},
        {"scripCode": 45006, "tradingSymbol": "INFYOCTFUT", "companyName": "INFOSYS 24 OCT FUT", "lotSize": 400, "tickSize": 0.05, "instType": "FUTSTK", "expiry": "24/10/2026"},
    ],
    "RN": [
        {"scripCode": 60001, "tradingSymbol": "USDINR24OCTFUT", "companyName": "USD/INR OCT FUT", "lotSize": 1000, "tickSize": 0.0025, "instType": "FUTCUR", "expiry": "28/10/2026"},
        {"scripCode": 60002, "tradingSymbol": "EURINR24OCTFUT", "companyName": "EUR/INR OCT FUT", "lotSize": 1000, "tickSize": 0.0025, "instType": "FUTCUR", "expiry": "28/10/2026"},
        {"scripCode": 60003, "tradingSymbol": "GBPINR24OCTFUT", "companyName": "GBP/INR OCT FUT", "lotSize": 1000, "tickSize": 0.0025, "instType": "FUTCUR", "expiry": "28/10/2026"},
        {"scripCode": 60004, "tradingSymbol": "JPYINR24OCTFUT", "companyName": "JPY/INR OCT FUT", "lotSize": 1000, "tickSize": 0.0025, "instType": "FUTCUR", "expiry": "28/10/2026"},
    ],
    "MX": [
        {"scripCode": 70001, "tradingSymbol": "GOLD24NOV", "companyName": "GOLD FUT 1KG", "lotSize": 1, "tickSize": 1.0, "instType": "FUTCOM", "expiry": "05/11/2026"},
        {"scripCode": 70002, "tradingSymbol": "SILVER24DEC", "companyName": "SILVER FUT 30KG", "lotSize": 1, "tickSize": 1.0, "instType": "FUTCOM", "expiry": "05/12/2026"},
        {"scripCode": 70003, "tradingSymbol": "CRUDEOIL24OCT", "companyName": "CRUDE OIL FUT 100BBL", "lotSize": 100, "tickSize": 1.0, "instType": "FUTCOM", "expiry": "19/10/2026"},
        {"scripCode": 70004, "tradingSymbol": "NATURALGASOCT", "companyName": "NATURAL GAS FUT", "lotSize": 1250, "tickSize": 0.10, "instType": "FUTCOM", "expiry": "26/10/2026"},
    ],
}

