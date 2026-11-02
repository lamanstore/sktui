"""Real-world market data service for Indian equities, indices, and derivatives.

Fetches authentic real-world OHLCV historical candlestick data and live market
quotes from public market endpoints (Yahoo Finance and Google Finance) with fast
local disk caching and graceful fallback to pre-calibrated baseline models when offline.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from sktui.config import DATA, KNOWN_BASE_PRICES, SUB_MINUTE_INTERVALS

logger = logging.getLogger(__name__)

# Map internal interval strings to Yahoo Finance (interval, range) tuples
YF_INTERVAL_MAP: dict[str, tuple[str, str]] = {
    "1minute": ("1m", "1d"),
    "1min": ("1m", "1d"),
    "1m": ("1m", "1d"),
    "2minute": ("2m", "1d"),
    "2min": ("2m", "1d"),
    "2m": ("2m", "1d"),
    "3minute": ("5m", "1d"),  # YF doesn't have 3m; 5m is closest intraday
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

# Special mapping for major indices and derivative underlyings
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


# Currency pairs mapping (Yahoo ticker, Google ticker)
CURRENCY_MAP: dict[str, tuple[str, str]] = {
    "USDJPY": ("JPYINR=X", "USD-JPY"),
    "EURUSD": ("EURUSD=X", "EUR-USD"),
    "USDINR": ("USDINR=X", "USD-INR"),
    "GBPINR": ("GBPINR=X", "GBP-INR"),
    "EURINR": ("EURINR=X", "EUR-INR"),
    "JPYINR": ("JPYINR=X", "JPY-INR"),
}


def to_yahoo_ticker(symbol: str, exchange: str = "NC") -> str:
    """Convert an Indian trading symbol and exchange into a Yahoo Finance ticker."""
    clean_sym = symbol.strip().upper()
    if clean_sym in CURRENCY_MAP or str(exchange).upper() == "RN":
        return CURRENCY_MAP.get(clean_sym, ("USDINR=X", "USD-INR"))[0]
    if clean_sym.startswith("^"):
        return clean_sym
    if clean_sym in SPECIAL_TICKER_MAP:
        return SPECIAL_TICKER_MAP[clean_sym]

    # Clean up derivative symbols (e.g. NIFTY24OCTFUT, RELIANCEOCTFUT, NIFTY25000CE)
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


# Google Finance benchmark index mapping (finance.google.com)
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
    """Convert an Indian trading symbol and exchange into a Google Finance ticker (e.g. RELIANCE:NSE)."""
    clean_sym = symbol.strip().upper()
    if clean_sym in CURRENCY_MAP or str(exchange).upper() == "RN":
        return CURRENCY_MAP.get(clean_sym, ("USDINR=X", "USD-INR"))[1]
    if clean_sym in GF_INDEX_MAP:
        return GF_INDEX_MAP[clean_sym]
    if ":" in clean_sym or "-" in clean_sym:
        return clean_sym

    # Clean up derivative symbols (e.g. NIFTY24OCTFUT, RELIANCEOCTFUT)
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
) -> tuple[list[dict], dict | None]:
    """Fetch authentic historical candlestick data from public market endpoints.

    Returns:
        (rows, meta_dict)
        - rows: list of dicts with keys: tradeDate, tradeTime, timestamp, open, high, low, close, volume
        - meta_dict: latest quote stats from the provider (ltp, previousClose, dayHigh, dayLow, etc.)
    """
    clean_sym = symbol.strip().upper()
    ticker = to_yahoo_ticker(clean_sym, exchange)
    iv_key = str(interval).lower()
    yf_iv, yf_range = YF_INTERVAL_MAP.get(iv_key, ("5m", "5d"))

    cache_path = _get_cache_path(ticker, yf_iv)

    # 1. Check local cache (fresh within 60s for intraday, 1 hour for daily)
    cache_ttl = 60 if yf_iv in ("1m", "2m", "5m", "15m", "30m", "60m") else 3600
    if not force_refresh and cache_path.exists():
        try:
            mtime = cache_path.stat().st_mtime
            if (time.time() - mtime) < cache_ttl:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    if isinstance(cached_data, dict) and "rows" in cached_data and cached_data["rows"]:
                        return cached_data["rows"], cached_data.get("meta")
        except Exception:
            pass

    # 2. Query Yahoo Finance API
    safe_ticker_url = urllib.parse.quote(ticker, safe="^._-")
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{safe_ticker_url}?interval={yf_iv}&range={yf_range}",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{safe_ticker_url}?interval={yf_iv}&range={yf_range}",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://finance.yahoo.com",
        "Referer": f"https://finance.yahoo.com/quote/{urllib.parse.quote(ticker)}",
    }
    for url in urls:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw_json = json.loads(resp.read().decode("utf-8"))
                chart_res = raw_json.get("chart", {}).get("result")
                if chart_res and isinstance(chart_res, list) and len(chart_res) > 0:
                    data = chart_res[0]
                    meta = data.get("meta", {})
                    timestamps = data.get("timestamp", [])
                    indicators = data.get("indicators", {}).get("quote", [{}])[0]

                    opens = indicators.get("open", [])
                    highs = indicators.get("high", [])
                    lows = indicators.get("low", [])
                    closes = indicators.get("close", [])
                    volumes = indicators.get("volume", [])

                    rows = []
                    for idx, epoch in enumerate(timestamps):
                        c = closes[idx] if idx < len(closes) else None
                        if c is None:
                            continue
                        o = opens[idx] if idx < len(opens) and opens[idx] is not None else c
                        h = highs[idx] if idx < len(highs) and highs[idx] is not None else max(o, c)
                        l = lows[idx] if idx < len(lows) and lows[idx] is not None else min(o, c)
                        v = volumes[idx] if idx < len(volumes) and volumes[idx] is not None else 0.0

                        dt = datetime.fromtimestamp(epoch)
                        rows.append({
                            "tradeDate": dt.strftime("%Y-%m-%d"),
                            "tradeTime": dt.strftime("%H:%M:%S"),
                            "timestamp": float(epoch),
                            "open": round(float(o), 2),
                            "high": round(float(h), 2),
                            "low": round(float(l), 2),
                            "close": round(float(c), 2),
                            "volume": round(float(v), 2),
                        })

                    if rows:
                        quote_meta = {
                            "ltp": float(meta.get("regularMarketPrice") or rows[-1]["close"]),
                            "previousClose": float(meta.get("chartPreviousClose") or meta.get("previousClose") or rows[0]["open"]),
                            "high": float(meta.get("regularMarketDayHigh") or max(r["high"] for r in rows)),
                            "low": float(meta.get("regularMarketDayLow") or min(r["low"] for r in rows)),
                            "volume": float(meta.get("regularMarketVolume") or sum(r["volume"] for r in rows)),
                            "currency": str(meta.get("currency") or "INR"),
                        }
                        # Save to cache
                        try:
                            DATA.mkdir(parents=True, exist_ok=True)
                            with open(cache_path, "w", encoding="utf-8") as f:
                                json.dump({"rows": rows, "meta": quote_meta}, f)
                        except Exception:
                            pass
                        return rows, quote_meta
        except Exception as exc:
            logger.debug("Live market data fetch failed for %s (%s) from %s: %s", ticker, yf_iv, url, exc)

    # 3. Fallback: check if stale cache exists
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                if isinstance(cached_data, dict) and "rows" in cached_data and cached_data["rows"]:
                    return cached_data["rows"], cached_data.get("meta")
        except Exception:
            pass

    return [], None


def _parse_num(s: str | None) -> float | None:
    if not s:
        return None
    cleaned = re.sub(r"[^\d.\-+eE]", "", str(s))
    try:
        return float(cleaned)
    except Exception:
        return None


def _parse_vol(s: str | None) -> float:
    if not s:
        return 0.0
    su = str(s).strip().upper()
    mult = 1.0
    if su.endswith("M"):
        mult = 1_000_000.0
        su = su[:-1]
    elif su.endswith("B"):
        mult = 1_000_000_000.0
        su = su[:-1]
    elif su.endswith("K"):
        mult = 1_000.0
        su = su[:-1]
    elif su.endswith("CR") or su.endswith("CRORE"):
        mult = 10_000_000.0
        su = su.split("C")[0]
    elif su.endswith("L") or su.endswith("LAKH"):
        mult = 100_000.0
        su = su.split("L")[0]
    val = _parse_num(su)
    return float(val * mult) if val is not None else 0.0


def fetch_google_quote(
    symbol: str,
    exchange: str = "NC",
    timeout_sec: float = 3.0,
    force_refresh: bool = False,
) -> dict | None:
    """Fetch live market quote snapshot from Google Finance (finance.google.com)."""
    clean_sym = symbol.strip().upper()
    ticker = to_google_ticker(clean_sym, exchange)
    safe_ticker = ticker.replace(":", "_").replace("^", "")
    cache_path = DATA / f"cache_gquote_{safe_ticker}.json"

    # 1. Check local cache (fresh within 60s)
    if not force_refresh and cache_path.exists():
        try:
            mtime = cache_path.stat().st_mtime
            if (time.time() - mtime) < 60:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    if isinstance(cached_data, dict) and cached_data.get("ltp"):
                        return cached_data
        except Exception:
            pass

    # 2. Query Google Finance
    url = f"https://www.google.com/finance/quote/{urllib.parse.quote(ticker, safe=':-_^')}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            ltp = None
            prev_close = None
            high_p = None
            low_p = None
            vol = 0.0

            # Check JSON-LD metadata if present
            ld_matches = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
            for ld_text in ld_matches:
                try:
                    ld_data = json.loads(ld_text)
                    if isinstance(ld_data, dict):
                        if "price" in ld_data:
                            ltp = _parse_num(str(ld_data["price"]))
                except Exception:
                    pass

            # Primary price extraction (class fxKbKc / data-last-price)
            if ltp is None:
                p_match = re.search(r'data-last-price="([^"]+)"', html)
                if p_match:
                    ltp = _parse_num(p_match.group(1))
            if ltp is None:
                p_match = re.search(r'class="[^"]*YMlKec fxKbKc[^"]*">([^<]+)<', html)
                if p_match:
                    ltp = _parse_num(p_match.group(1))

            if ltp is not None and ltp > 0:
                # Previous close
                pc_match = re.search(r'Previous close[^<]*</div>\s*<div[^>]*class="[^"]*P6K39c[^"]*">([^<]+)<', html)
                if pc_match:
                    prev_close = _parse_num(pc_match.group(1))
                if prev_close is None:
                    pc_attr = re.search(r'data-previous-close="([^"]+)"', html)
                    if pc_attr:
                        prev_close = _parse_num(pc_attr.group(1))
                if prev_close is None:
                    prev_close = ltp

                # Day range (High / Low)
                rng_match = re.search(r'Day range[^<]*</div>\s*<div[^>]*class="[^"]*P6K39c[^"]*">([^<]+)<', html)
                if rng_match:
                    parts = rng_match.group(1).split("-")
                    if len(parts) >= 2:
                        low_p = _parse_num(parts[0])
                        high_p = _parse_num(parts[1])
                if high_p is None:
                    high_p = ltp
                if low_p is None:
                    low_p = ltp

                # Volume
                vol_match = re.search(r'Volume[^<]*</div>\s*<div[^>]*class="[^"]*P6K39c[^"]*">([^<]+)<', html)
                if vol_match:
                    vol = _parse_vol(vol_match.group(1))

                chg = round(ltp - prev_close, 2)
                pct = round((chg / prev_close * 100.0), 2) if prev_close else 0.0

                quote = {
                    "tradingSymbol": clean_sym,
                    "exchange": exchange,
                    "ltp": ltp,
                    "rsChange": chg,
                    "perChange": pct,
                    "open": prev_close,
                    "high": high_p,
                    "low": low_p,
                    "close": prev_close,
                    "qty": vol,
                    "source": "google",
                }
                # Save to cache
                try:
                    DATA.mkdir(parents=True, exist_ok=True)
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(quote, f)
                except Exception:
                    pass
                return quote
    except Exception as exc:
        logger.debug("Google Finance fetch failed for %s (%s): %s", ticker, url, exc)

    # 3. Fallback: check stale cache
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                if isinstance(cached_data, dict) and cached_data.get("ltp"):
                    return cached_data
        except Exception:
            pass

    return None


def fetch_real_quote(
    symbol: str,
    exchange: str = "NC",
    timeout_sec: float = 3.0,
) -> dict | None:
    """Fetch real-time snapshot quote for *symbol* with dual Yahoo + Google Finance failover."""
    # 1. Primary: Yahoo Finance
    rows, meta = fetch_real_history(symbol, exchange, interval="5minute", timeout_sec=timeout_sec)
    if meta and meta.get("ltp"):
        ltp = meta["ltp"]
        prev = meta.get("previousClose") or ltp
        chg = round(ltp - prev, 2)
        pct = round((chg / prev * 100.0), 2) if prev else 0.0
        return {
            "tradingSymbol": symbol.upper(),
            "exchange": exchange,
            "ltp": ltp,
            "rsChange": chg,
            "perChange": pct,
            "open": rows[0]["open"] if rows else ltp,
            "high": meta.get("high") or ltp,
            "low": meta.get("low") or ltp,
            "close": prev,
            "qty": meta.get("volume") or 0.0,
            "source": "yahoo",
        }

    # 2. Secondary failover: Google Finance (finance.google.com)
    g_quote = fetch_google_quote(symbol, exchange, timeout_sec=timeout_sec)
    if g_quote and g_quote.get("ltp"):
        return g_quote

    return None


def fetch_indices_quotes(timeout_sec: float = 3.0) -> dict[str, dict]:
    """Fetch real-world quotes for benchmark indices (NIFTY 50, BANK NIFTY, SENSEX)
    with dual Yahoo Finance + Google Finance redundancy."""
    indices = {
        "NIFTY50": ("^NSEI", "NIFTY_50:INDEXNSE"),
        "BANKNIFTY": ("^NSEBANK", "NIFTY_BANK:INDEXNSE"),
        "SENSEX": "^BSESN",
    }
    index_pairs = {
        "NIFTY50": ("^NSEI", "NIFTY_50:INDEXNSE"),
        "BANKNIFTY": ("^NSEBANK", "NIFTY_BANK:INDEXNSE"),
        "SENSEX": ("^BSESN", "SENSEX:INDEXBOM"),
    }
    out: dict[str, dict] = {}

    # 1. Attempt Yahoo Finance for all benchmark indices
    for name, (yf_ticker, _) in index_pairs.items():
        try:
            _, meta = fetch_real_history(yf_ticker, exchange="NC", interval="daily", timeout_sec=timeout_sec)
            if meta and meta.get("ltp"):
                ltp = float(meta["ltp"])
                prev = float(meta.get("previousClose") or ltp)
                chg = round(ltp - prev, 2)
                pct = round((chg / prev * 100.0), 2) if prev else 0.0
                out[name] = {
                    "tradingSymbol": name,
                    "ltp": ltp,
                    "rsChange": chg,
                    "perChange": pct,
                    "high": float(meta.get("high") or ltp),
                    "low": float(meta.get("low") or ltp),
                    "close": prev,
                    "source": "yahoo",
                }
        except Exception:
            pass

    # 2. For any index that Yahoo missed, failover to Google Finance (finance.google.com)
    for name, (_, gf_ticker) in index_pairs.items():
        if name not in out:
            try:
                g_q = fetch_google_quote(gf_ticker, exchange="NC", timeout_sec=timeout_sec)
                if g_q and g_q.get("ltp"):
                    out[name] = g_q
            except Exception:
                pass

    return out


