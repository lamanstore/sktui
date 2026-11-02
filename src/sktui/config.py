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

# Semantic color tokens (Phase G)
BULL    = C_GREEN
BEAR    = C_RED
RISK    = C_AMBER
STALE   = C_DIM
SAFE    = "#14b8a6"
NEUTRAL = "#ffffff"

# Extended palette
C_BLUE   = "#3b82f6"
C_PURPLE = "#8b5cf6"
C_TEAL   = "#14b8a6"
C_LIME   = "#84cc16"
C_ORANGE = "#f97316"
C_PINK   = "#ec4899"
C_NAVY   = "#0a1f36"
C_DARK   = "#080c16"

# ── Static Sector Mapping for Indian Equities (Phase E) ───────────────────────
SECTOR_MAP: dict[str, str] = {
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "SBIN": "Banking",
    "KOTAKBANK": "Banking",
    "AXISBANK": "Banking",
    "BANKNIFTYFUT": "Banking",
    "TCS": "IT",
    "INFY": "IT",
    "WIPRO": "IT",
    "HCLTECH": "IT",
    "TECHM": "IT",
    "INFYOCTFUT": "IT",
    "RELIANCE": "Energy",
    "ONGC": "Energy",
    "ASIANENE": "Energy",
    "NTPC": "Energy",
    "POWERGRID": "Energy",
    "BPCL": "Energy",
    "IOC": "Energy",
    "RELIANCEOCTFUT": "Energy",
    "TATAMOTORS": "Auto",
    "M&M": "Auto",
    "MARUTI": "Auto",
    "BAJAJ-AUTO": "Auto",
    "HEROMOTOCO": "Auto",
    "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals",
    "HINDALCO": "Metals",
    "COALINDIA": "Metals",
    "ITC": "FMCG",
    "HINDUNILVR": "FMCG",
    "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG",
    "SUNPHARMA": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "DIVISLAB": "Pharma",
    "LT": "Infrastructure",
    "BHARTIARTL": "Telecom",
    "TITAN": "Consumer",
    "BAJFINANCE": "Finance",
    "NIFTY50": "Index",
    "NIFTY24OCTFUT": "Index",
    "NIFTY25000CE": "Index",
    "NIFTY25000PE": "Index",
    "PNB": "Banking",
}

# ── Baseline market prices for Indian equities & indices ──────────────────────
KNOWN_BASE_PRICES: dict[str, float] = {
    "PNB": 123.50,
    "SBIN": 825.00,
    "HDFCBANK": 1650.00,
    "ICICIBANK": 1240.00,
    "KOTAKBANK": 1780.00,
    "AXISBANK": 1180.00,
    "BANKBARODA": 245.00,
    "CANBK": 105.00,
    "UNIONBANK": 115.00,
    "IDFCFIRSTB": 72.00,
    "RELIANCE": 1320.00,
    "ONGC": 255.00,
    "IOC": 142.00,
    "BPCL": 310.00,
    "HPCL": 370.00,
    "GAIL": 190.00,
    "NTPC": 385.00,
    "POWERGRID": 320.00,
    "COALINDIA": 415.00,
    "TCS": 4250.00,
    "INFY": 1890.00,
    "WIPRO": 540.00,
    "HCLTECH": 1760.00,
    "TECHM": 1620.00,
    "LTIM": 5900.00,
    "TATAMOTORS": 965.00,
    "MARUTI": 12400.00,
    "M&M": 2850.00,
    "BAJAJ-AUTO": 9800.00,
    "HEROMOTOCO": 5100.00,
    "EICHERMOT": 4650.00,
    "TATASTEEL": 152.00,
    "JSWSTEEL": 960.00,
    "HINDALCO": 680.00,
    "VEDL": 460.00,
    "ITC": 490.00,
    "HINDUNILVR": 2450.00,
    "NESTLEIND": 2250.00,
    "BRITANNIA": 5300.00,
    "DABUR": 520.00,
    "SUNPHARMA": 1750.00,
    "CIPLA": 1520.00,
    "DRREDDY": 6600.00,
    "DIVISLAB": 5800.00,
    "LT": 3550.00,
    "BHARTIARTL": 1540.00,
    "TITAN": 3400.00,
    "BAJFINANCE": 6900.00,
    "BAJAJFINSV": 1750.00,
    "ZOMATO": 260.00,
    "JIOFIN": 325.00,
    "IRFC": 155.00,
    "BEL": 290.00,
    "HAL": 4400.00,
    "BHEL": 240.00,
    "ASIANENE": 315.00,
    "SUZLON": 62.00,
    "ADANIENT": 2950.00,
    "ADANIPORTS": 1380.00,
    "TATAPOWER": 430.00,
    "NHPC": 92.00,
    "IREDA": 215.00,
    "RVNL": 480.00,
    "MAZDOCK": 4200.00,
    "COCHINSHIP": 1650.00,
    "IDEA": 9.50,
    "YESBANK": 22.00,
    "FEDERALBNK": 195.00,
    "INDUSINDBK": 1450.00,
    "MOTHERSON": 185.00,
    "POLYCAB": 6400.00,
    "HAVELLS": 1780.00,
    "PIDILITIND": 3100.00,
    "TRENT": 7200.00,
    "DMART": 4400.00,
    "SWIGGY": 480.00,
    "MRF": 132000.00,
    "NIFTY50": 24200.00,
    "NIFTY": 24200.00,
    "BANKNIFTY": 51800.00,
    "BANKNIFTYFUT": 51900.00,
    "SENSEX": 79400.00,
    "FINNIFTY": 23800.00,
    "NIFTY24OCTFUT": 24250.00,
    "HINDCOPPER": 285.00,
    "USDJPY": 154.20,
    "EURUSD": 1.08,
    "USDINR": 84.40,
    "GBPINR": 109.50,
    "EURINR": 91.50,
    "JPYINR": 0.55,
}

# ── Storage paths ──────────────────────────────────────────────────────────────
CONF         = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "sktui"
DATA         = Path(os.environ.get("XDG_DATA_HOME",   Path.home() / ".local/share")) / "sktui"
CONFIG_FILE  = CONF / "config.json"
SESSION_FILE = DATA / "session.json"
WATCH_FILE   = CONF / "watchlist.json"
ALERTS_FILE  = CONF / "alerts.json"

EXCH_NAMES = {"NC": "NSE Equity", "BC": "BSE Equity", "NF": "NSE F&O",
              "RN": "NSE Currency", "MX": "MCX",
              "NSE": "NSE Equity", "BSE": "BSE Equity"}
CASH       = ("NC", "BC")
PRODUCTS   = ["INVESTMENT", "BIGTRADE", "BIGTRADE+"]
VALIDITIES = ["GFD", "MyGTD", "IOC"]
INTERVALS = [
    "tick", "1second", "5second", "15second", "30second",
    "1minute", "3minute", "5minute", "10minute", "15minute", "30minute",
    "60minute", "90minute", "daily", "weekly", "monthly",
    "quarterly", "halfyearly", "yearly",
]

SUB_MINUTE_INTERVALS = ("tick", "1second", "5second", "15second", "30second")

INTERVAL_SECONDS: dict[str, int] = {
    "tick": 0,
    "1second": 1,
    "5second": 5,
    "15second": 15,
    "30second": 30,
    "1minute": 60,
    "3minute": 180,
    "5minute": 300,
    "10minute": 600,
    "15minute": 900,
    "30minute": 1800,
    "60minute": 3600,
    "90minute": 5400,
    "daily": 86400,
    "weekly": 604800,
    "monthly": 2592000,
    "quarterly": 7776000,
    "halfyearly": 15552000,
    "yearly": 31536000,
}

# ── Interval display labels ───────────────────────────────────────────────────
INTERVAL_LABELS = {
    "tick": "TICK", "1second": "1s", "5second": "5s",
    "15second": "15s", "30second": "30s",
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
    "/audit":      ("View immutable execution audit log",     "audit"),
    "/analytics":  ("Portfolio P/L & exposure analytics",     "analytics"),
    "/export":     ("Export analytics to CSV (/export csv)",  "export"),
    "/debug":      ("Open runtime diagnostics & WS panel",    "debug"),
    "/theme":      ("Switch UI color theme (live preview)",   "theme"),
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
        {"scripCode": 10666, "tradingSymbol": "PNB", "companyName": "Punjab National Bank", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
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
        {"scripCode": 532461, "tradingSymbol": "PNB", "companyName": "Punjab National Bank (BSE)", "lotSize": 1, "tickSize": 0.05, "instType": "EQ"},
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

# ── Workspace Layout & Action Registry ─────────────────────────────────────────
PANE_KEYS = {
    "dashboard": "1",
    "watch": "1",
    "watchlist": "1",
    "symbol": "2",
    "focus": "2",
    "chart": "2",
    "orders": "3",
    "trade": "3",
    "positions": "4",
    "holdings": "5",
    "funds": "6",
    "activity": "7",
    "scanner": "4",
    "alerts": "5",
    "logs": "6",
}

KEY_ACTIONS = {
    "b": "buy",
    "s": "sell",
    "m": "modify",
    "x": "cancel_order",
    "X": "cancel_all",
    "c": "chart",
    "i": "detail",
    "a": "add",
    "delete": "remove",
    "r": "refresh_all",
    "p": "products",
    "d": "toggle_log",
    "/": "command_mode",
    "f1": "help",
    "ctrl+l": "logout",
    "q": "quit",
}

DEFAULT_PANEL_WIDTHS = {
    "left_pane": 32,
    "center_pane": "1fr",
    "right_pane": 36,
    "bottom_height": 10,
    "command_width": 38,
}
PANEL_CONFIG = DEFAULT_PANEL_WIDTHS

ALERT_LEVELS = {"info", "warn", "critical"}

ALERT_THRESHOLDS = {
    "pct": 1.5,
    "vol": 2.0,
    "drawdown_pct": 2.0,
    "max_order_val": 200000.0,
}

SCAN_DEFAULTS = {
    "gainers_min_pct": 1.0,
    "losers_max_pct": -1.0,
    "volume_spike_mult": 1.5,
}

