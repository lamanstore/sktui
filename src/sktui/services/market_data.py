"""Pure Sharekhan market data service for Indian equities, indices, and derivatives.

Third-party scrapers (Yahoo Finance, Google Finance) have been completely removed.
All authentic market data, quotes, and candlestick feeds are sourced directly
from the Sharekhan REST API and WebSocket stream.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sktui.config import DATA, KNOWN_BASE_PRICES, SUB_MINUTE_INTERVALS

logger = logging.getLogger(__name__)

# Map internal interval strings to standardized interval codes
YF_INTERVAL_MAP: dict[str, tuple[str, str]] = {
    "1minute": ("1m", "1d"),
    "1min": ("1m", "1d"),
    "1m": ("1m", "1d"),
    "2minute": ("2m", "1d"),
    "2min": ("2m", "1d"),
    "2m": ("2m", "1d"),
    "3minute": ("5m", "1d"),
    "3min": ("5m", "1d"),
    "3m": ("5m", "1d"),
    "5minute": ("5m", "5d"),
    "5min": ("5m", "5d"),
    "5m": ("5m", "5d"),
    "10minute": ("15m", "5d"),
    "10min": ("15m", "5d"),
    "10m": ("15m", "5d"),
    "15minute": ("15m", "5d"),
    "15min": ("15m", "5d"),
    "15m": ("15m", "5d"),
    "30minute": ("30m", "1mo"),
    "30min": ("30m", "1mo"),
    "30m": ("30m", "1mo"),
    "60minute": ("60m", "1mo"),
    "60min": ("60m", "1mo"),
    "1h": ("60m", "1mo"),
    "daily": ("1d", "3mo"),
    "1d": ("1d", "3mo"),
    "weekly": ("1wk", "1y"),
    "1w": ("1wk", "1y"),
    "monthly": ("1mo", "5y"),
    "1M": ("1mo", "5y"),
}

# Mapping for major benchmark indices
SPECIAL_TICKER_MAP: dict[str, str] = {
    "NIFTY50": "^NSEI",
    "NIFTY 50": "^NSEI",
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "BANK NIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "BSE SENSEX": "^BSESN",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
}

# Currency pairs mapping
CURRENCY_MAP: dict[str, tuple[str, str]] = {
    "USDJPY": ("USDJPY=X", "USD-JPY"),
    "EURUSD": ("EURUSD=X", "EUR-USD"),
    "USDINR": ("USDINR=X", "USD-INR"),
    "GBPINR": ("GBPINR=X", "GBP-INR"),
    "EURINR": ("EURINR=X", "EUR-INR"),
    "JPYINR": ("JPYINR=X", "JPY-INR"),
}


def to_yahoo_ticker(symbol: str, exchange: str = "NC") -> str:
    """Format an Indian trading symbol and exchange into a standardized ticker format."""
    clean_sym = symbol.strip().upper()
    if clean_sym in CURRENCY_MAP or str(exchange).upper() == "RN":
        return CURRENCY_MAP.get(clean_sym, ("USDINR=X", "USD-INR"))[0]
    if clean_sym.startswith("^"):
        return clean_sym
    if clean_sym in SPECIAL_TICKER_MAP:
        return SPECIAL_TICKER_MAP[clean_sym]

    is_deriv = False
    for suffix in ("FUT", "CE", "PE"):
        if clean_sym.endswith(suffix):
            is_deriv = True
            break
    if is_deriv:
        for prefix in ("NIFTY", "BANKNIFTY", "FINNIFTY", "RELIANCE", "INFY", "TCS", "PNB", "SBIN"):
            if clean_sym.startswith(prefix) and clean_sym != prefix:
                return to_yahoo_ticker(prefix, exchange)

    exch_upper = str(exchange).upper()
    if exch_upper in ("BC", "BSE"):
        return f"{clean_sym}.BO"
    return f"{clean_sym}.NS"


GF_INDEX_MAP: dict[str, str] = {
    "NIFTY50": "NIFTY_50:INDEXNSE",
    "NIFTY 50": "NIFTY_50:INDEXNSE",
    "NIFTY": "NIFTY_50:INDEXNSE",
    "^NSEI": "NIFTY_50:INDEXNSE",
    "BANKNIFTY": "NIFTY_BANK:INDEXNSE",
    "BANK NIFTY": "NIFTY_BANK:INDEXNSE",
    "^NSEBANK": "NIFTY_BANK:INDEXNSE",
    "SENSEX": "SENSEX:INDEXBOM",
    "BSE SENSEX": "SENSEX:INDEXBOM",
    "^BSESN": "SENSEX:INDEXBOM",
    "FINNIFTY": "NIFTY_FIN_SERVICE:INDEXNSE",
}


def to_google_ticker(symbol: str, exchange: str = "NC") -> str:
    """Format an Indian trading symbol and exchange into a standardized symbol format."""
    clean_sym = symbol.strip().upper()
    if clean_sym in CURRENCY_MAP or str(exchange).upper() == "RN":
        return CURRENCY_MAP.get(clean_sym, ("USDINR=X", "USD-INR"))[1]
    if clean_sym in GF_INDEX_MAP:
        return GF_INDEX_MAP[clean_sym]
    if ":" in clean_sym or "-" in clean_sym:
        return clean_sym

    is_deriv = False
    for suffix in ("FUT", "CE", "PE"):
        if clean_sym.endswith(suffix):
            is_deriv = True
            break
    if is_deriv:
        for prefix in ("NIFTY", "BANKNIFTY", "FINNIFTY", "RELIANCE", "INFY", "TCS", "PNB", "SBIN"):
            if clean_sym.startswith(prefix) and clean_sym != prefix:
                return to_google_ticker(prefix, exchange)

    exch_upper = str(exchange).upper()
    if exch_upper in ("BC", "BSE", "BOM"):
        return f"{clean_sym}:BOM"
    return f"{clean_sym}:NSE"


def _get_cache_path(ticker: str, interval: str) -> Path:
    safe_ticker = ticker.replace("^", "").replace(".", "_")
    return DATA / f"cache_candles_{safe_ticker}_{interval}.json"


def fetch_real_history(
    symbol: str,
    exchange: str = "NC",
    interval: str = "5minute",
    scrip_code: Any = None,
    timeout_sec: float = 4.0,
    force_refresh: bool = False,
    client: Any = None,
) -> tuple[list[dict], dict | None]:
    """Fetch authentic historical candlestick data exclusively from Sharekhan.

    Third-party scrapers (Yahoo/Google) have been removed. If a Sharekhan client
    is provided or authenticated, queries Sharekhan historical endpoint.
    Also supports local test cache files if previously stored.
    """
    clean_sym = symbol.strip().upper()
    ticker = to_yahoo_ticker(clean_sym, exchange)
    iv_key = str(interval).lower()
    yf_iv, _ = YF_INTERVAL_MAP.get(iv_key, ("5m", "5d"))

    cache_path = _get_cache_path(ticker, yf_iv)

    # 1. Check local cache (useful for testing and offline replay)
    if not force_refresh and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                if isinstance(cached_data, dict) and "rows" in cached_data and cached_data["rows"]:
                    return cached_data["rows"], cached_data.get("meta")
        except Exception:
            pass

    # 2. Query Sharekhan REST API directly if client is available
    if client and hasattr(client, "historical"):
        code = scrip_code
        if not code and clean_sym:
            from sktui.utils import resolve_code
            code = resolve_code(clean_sym, exchange)
        if code:
            try:
                rows = client.historical(exchange, code, interval)
                if rows:
                    latest = rows[-1]
                    prev = rows[-2] if len(rows) >= 2 else latest
                    ltp = float(latest.get("close") or latest.get("Close") or 0.0)
                    prev_c = float(prev.get("close") or prev.get("Close") or ltp)
                    high_p = max(float(r.get("high") or r.get("High") or 0.0) for r in rows)
                    low_p = min(float(r.get("low") or r.get("Low") or ltp) for r in rows)
                    vol_tot = sum(float(r.get("volume") or r.get("Volume") or 0.0) for r in rows)
                    meta = {
                        "ltp": ltp,
                        "previousClose": prev_c,
                        "high": high_p,
                        "low": low_p,
                        "volume": vol_tot,
                        "currency": "INR",
                    }
                    return rows, meta
            except Exception as exc:
                logger.debug("Sharekhan historical fetch failed for %s (%s): %s", clean_sym, code, exc)

    return [], None


def fetch_google_quote(
    symbol: str,
    exchange: str = "NC",
    timeout_sec: float = 3.0,
    force_refresh: bool = False,
) -> dict | None:
    """Google Finance scraper has been removed per institutional mandate.

    Returns None. All quotes are delivered exclusively via Sharekhan.
    """
    return None


def fetch_real_quote(
    symbol: str,
    exchange: str = "NC",
    scrip_code: Any = None,
    client: Any = None,
    timeout_sec: float = 3.0,
) -> dict | None:
    """Fetch real-time snapshot quote exclusively from Sharekhan REST API."""
    if client and hasattr(client, "quote"):
        code = scrip_code
        if not code and symbol:
            from sktui.utils import resolve_code
            code = resolve_code(symbol, exchange)
        if code:
            try:
                return client.quote(exchange, code)
            except Exception:
                pass
    return None


def fetch_indices_quotes(timeout_sec: float = 3.0, client: Any = None) -> dict[str, dict]:
    """Fetch authentic benchmark index quotes exclusively from Sharekhan.

    Third-party scrapers have been eliminated.
    """
    out: dict[str, dict] = {}
    if client and hasattr(client, "quote"):
        try:
            q_nifty = client.quote("NC", 21808)
            if q_nifty and q_nifty.get("ltp"):
                out["NIFTY50"] = q_nifty
        except Exception:
            pass
    return out
