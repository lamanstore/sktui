"""Market service — live tick processing, quote normalisation, feed event routing.

This is the bridge between the raw WebSocket feed (api.Feed) and the
UI.  It owns:
  - routing WS messages to the right handler (tick vs ack)
  - updating QuoteStore on every tick
  - running the simulation tick for paper/offline mode
  - notifying the UI via a registered on_tick / on_ack callback

Usage::

    service = MarketService(quote_store, watchlist_store)
    service.on_tick_update = lambda key, tick: ...  # plug in UI callback
    service.on_ack_update  = lambda data: ...
    feed.start()
"""
from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Any, Callable

from sktui.state.quote_store import QuoteStore
from sktui.state.watchlist_store import WatchlistStore


class MarketService:
    """Processes market data ticks and routes feed events.

    Parameters
    ----------
    quotes:    QuoteStore instance to update on each tick.
    watchlist: WatchlistStore used to seed initial quotes.
    """

    def __init__(self, quotes: QuoteStore, watchlist: WatchlistStore) -> None:
        self._quotes    = quotes
        self._watchlist = watchlist
        # Callbacks wired in by the UI layer
        self.on_tick_update: Callable[[str, dict, float | None, float | None], None] | None = None
        self.on_ack_update:  Callable[[dict], None] | None = None

    # ── Feed entry-point ──────────────────────────────────────────────────────
    def handle_ws(self, msg: Any) -> None:
        """Route a raw WebSocket message to the appropriate handler."""
        if not msg:
            return
        if isinstance(msg, list):
            for row in msg:
                if isinstance(row, dict):
                    self._handle_single_data(row)
            return
        if isinstance(msg, dict):
            data = msg.get("data")
            if isinstance(data, list):
                for row in data:
                    if isinstance(row, dict):
                        self._handle_single_data(row)
                return
            if isinstance(data, dict):
                self._handle_single_data(data)
                return
            self._handle_single_data(msg)

    def _handle_single_data(self, data: dict) -> None:
        if "AckState" in data or "SharekhanOrderID" in data:
            if self.on_ack_update:
                self.on_ack_update(data)
            return
        code = data.get("scripCode") or data.get("code") or data.get("ScripCode")
        has_ltp = any(
            k in data for k in ("ltp", "lastTradedPrice", "LastTradedPrice", "LTP", "close", "Close", "c")
        )
        if code and has_ltp:
            self._process_tick(data)

    # ── Tick processing ───────────────────────────────────────────────────────
    def _process_tick(self, d: dict) -> None:
        code = d.get("scripCode") or d.get("code") or d.get("ScripCode")
        exch = d.get("exchangeCode") or d.get("exchange") or d.get("Exchange")
        if not exch:
            for w in self._watchlist.items:
                if str(w.get("scripCode")) == str(code):
                    exch = w.get("exchange", "NC")
                    break
        exch = exch or "NC"
        key  = f"{exch}{code}"

        prev_ltp = self._quotes.get(key).get("ltp")
        new_ltp  = self._quotes.update(key, d)

        if self.on_tick_update:
            self.on_tick_update(key, self._quotes.raw_ticks[key], prev_ltp, new_ltp)

    # ── Initial / simulated quotes ────────────────────────────────────────────
    _BASE_PRICES: dict[str, tuple] = {
        "ONGC":       (255.00, 1.80,   0.71, 254.95, 255.00, 253.20, 256.40, 252.80, 253.20, 5200000, 14200),
        "RELIANCE":   (1320.00, -8.50, -0.64, 1319.80, 1320.00, 1325.00, 1332.00, 1314.00, 1328.50, 4800000, 115000),
        "TCS":        (4050.00, 25.00,  0.62, 4049.50, 4050.00, 4025.00, 4065.00, 4015.00, 4025.00, 1500000, 42000),
        "INFY":       (1850.00, 12.20,  0.66, 1849.50, 1850.00, 1838.00, 1858.00, 1835.00, 1837.80, 3800000, 65000),
        "HDFCBANK":   (1740.00, 6.40,   0.37, 1739.80, 1740.00, 1733.60, 1748.00, 1730.00, 1733.60, 6100000, 125000),
        "SBIN":       (820.00, -3.20,  -0.39, 819.80,  820.00,  823.20,  826.50,  817.00,  823.20, 7500000, 98000),
        "TATAMOTORS": (920.00, 9.30,    1.02, 919.80,  920.00,  910.70,  925.00,  908.00,  910.70, 6500000, 86000),
        "BHARTIARTL": (1580.00, 7.80,   0.50, 1579.50, 1580.00, 1572.20, 1588.00, 1568.00, 1572.20, 3100000, 41000),
    }

    def initial_quote(self, item: dict, allow_network: bool = True) -> dict:
        """Return an initial quote for *item*, seeding the store if needed.

        Prioritizes authentic market quotes first, falling back to cached or
        calibrated models when offline. When allow_network is False, performs
        zero blocking network I/O and returns immediately.
        """
        key = WatchlistStore.feed_key(item)
        existing = self._quotes.get(key)
        if existing and existing.get("ltp"):
            return existing

        sym = str(item.get("tradingSymbol", "")).upper()
        exch = item.get("exchange", "NC")

        p = None
        c, pct, b, a, o, h, l, cl, v, oi = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0
        real_history_rows = None

        # 1. First priority: Real broker LTP snapshot if already present in item
        if item.get("ltp") or item.get("lastTradedPrice"):
            p = float(item.get("ltp") or item.get("lastTradedPrice"))
            c = float(item.get("rsChange") or 0.0)
            pct = float(item.get("perChange") or 0.0)
            cl = float(item.get("close") or (p - c if c else p))
            o = float(item.get("open") or p)
            h = float(item.get("high") or max(p, o))
            l = float(item.get("low") or min(p, o))
            v = float(item.get("qty") or item.get("volume") or 150000)
            b = float(item.get("bidPrice") or round(p - 0.05, 2))
            a = float(item.get("offPrice") or p)
            oi = int(item.get("currentOI") or 0)

        # 2. Second priority: Query authentic real-world market quote or local disk cache
        if p is None and sym:
            # Check local disk cache first (instant local file read without network)
            try:
                import json
                from sktui.services.market_data import _get_cache_path, to_yahoo_ticker
                ticker = to_yahoo_ticker(sym, exch)
                cache_path = _get_cache_path(ticker, "5m")
                if cache_path.exists():
                    with open(cache_path, "r", encoding="utf-8") as f:
                        cached_json = json.load(f)
                        cached_meta = cached_json.get("meta") if isinstance(cached_json, dict) else None
                        if cached_meta and cached_meta.get("ltp"):
                            p = float(cached_meta["ltp"])
                            cl = float(cached_meta.get("previousClose") or p)
                            c = round(p - cl, 2)
                            pct = round((c / cl * 100.0), 2) if cl else 0.0
                            h = float(cached_meta.get("high") or p)
                            l = float(cached_meta.get("low") or p)
                            real_history_rows = cached_json.get("rows")
                            o = float(real_history_rows[0]["open"] if real_history_rows else p)
                            v = float(cached_meta.get("volume") or 100000)
                            b = round(p - 0.05, 2)
                            a = p
                            oi = 10000
            except Exception:
                pass

            # Only query remote HTTP endpoints if network is explicitly permitted
            if p is None and allow_network:
                try:
                    from sktui.services.market_data import fetch_real_history, fetch_real_quote
                    real_rows, meta = fetch_real_history(sym, exch, interval="5minute", timeout_sec=2.0)
                    if meta and meta.get("ltp"):
                        p = float(meta["ltp"])
                        cl = float(meta.get("previousClose") or p)
                        c = round(p - cl, 2)
                        pct = round((c / cl * 100.0), 2) if cl else 0.0
                        h = float(meta.get("high") or p)
                        l = float(meta.get("low") or p)
                        o = float(real_rows[0]["open"] if real_rows else p)
                        v = float(meta.get("volume") or 100000)
                        b = round(p - 0.05, 2)
                        a = p
                        oi = 10000
                        real_history_rows = real_rows
                    else:
                        real_q = fetch_real_quote(sym, exch, timeout_sec=2.0)
                        if real_q and real_q.get("ltp"):
                            p = float(real_q["ltp"])
                            c = float(real_q.get("rsChange") or 0.0)
                            pct = float(real_q.get("perChange") or 0.0)
                            o = float(real_q.get("open") or p)
                            h = float(real_q.get("high") or p)
                            l = float(real_q.get("low") or p)
                            cl = float(real_q.get("close") or p)
                            v = float(real_q.get("qty") or 100000)
                            b = round(p - 0.05, 2)
                            a = p
                            oi = 10000
                except Exception:
                    pass

        # 3. Third priority: Offline baseline fallback
        source = "real" if (p is not None and not real_history_rows) else ("cache" if real_history_rows else "baseline")
        if p is None:
            source = "baseline"
            from sktui.config import KNOWN_BASE_PRICES
            bp = self._BASE_PRICES.get(sym)
            if bp:
                p, c, pct, b, a, o, h, l, cl, v, oi = bp
            elif sym in KNOWN_BASE_PRICES:
                p = KNOWN_BASE_PRICES[sym]
                c = round(p * 0.005, 2)
                pct = 0.50
                b, a, o, h, l, cl, v, oi = (
                    round(p - 0.05, 2), p, p - c, round(p + abs(c) + 1.0, 2),
                    round(max(1.0, p - abs(c) - 1.0), 2), p - c, 250000, 15000,
                )
            else:
                # Realistic offline baseline for unmapped symbols/currencies
                if str(exch).upper() == "RN" or any(k in sym for k in ("USD", "EUR", "JPY", "GBP")):
                    p = 84.40 if "USD" in sym else (1.08 if "EUR" in sym else (0.55 if "JPY" in sym else 1.0))
                else:
                    p = 100.00
                c = 0.0
                pct = 0.0
                b, a, o, h, l, cl, v, oi = (
                    round(p - 0.05, 2), p, p, p, p, p, 100000, 5000,
                )

        q = {
            "scripCode":    item.get("scripCode"),
            "exchangeCode": item.get("exchange", "NC"),
            "tradingSymbol": sym,
            "ltp": p, "rsChange": c, "perChange": pct,
            "bidPrice": b, "offPrice": a, "open": o,
            "high": h, "low": l, "close": cl, "qty": v, "currentOI": oi,
            "source": source,
        }
        self._quotes.seed(key, q)

        if real_history_rows:
            tape_entries = [
                (float(r.get("timestamp") or time.time()), float(r.get("close") or p), float(r.get("volume") or 0.0))
                for r in real_history_rows
            ]
            self._quotes.seed_tape(key, tape_entries)
            self._quotes.seed_history(key, [float(r.get("close") or p) for r in real_history_rows[-15:]])
        else:
            self._quotes.seed_history(
                key,
                [p * (1 + (random.random() - 0.5) * 0.005) for _ in range(15)],
            )
            self._quotes.seed_tape(key, self._synthetic_tape(p))

        return self._quotes.get(key)

    @staticmethod
    def _synthetic_tape(
        price: float, n: int = 900, span_sec: float = 1200.0,
    ) -> list[tuple[float, float, float]]:
        """Generate a backward random-walk tick tape ending at *price* now.

        Gives 1s/5s/15s/30s/TICK charts immediate structure before the first
        real tick arrives. Not counted as live ticks by ``QuoteStore``.
        """
        now = time.time()
        step = span_sec / max(1, n)
        vol_sigma = price * 0.0006
        out: list[tuple[float, float, float]] = []
        px = price
        for i in range(n):
            ts = now - i * step - random.random() * step * 0.4
            out.append((ts, round(px, 2), float(random.randint(5, 400))))
            px = max(0.5, px - random.gauss(0, vol_sigma))
        out.reverse()
        return out

    def simulate_tick(self, item: dict) -> None:
        """Fire a simulated micro price movement for *item*.

        Used in paper / offline mode so the watchlist and dashboard stay alive.
        Applies mean-reverting micro-fluctuations around the base market price.
        """
        key = WatchlistStore.feed_key(item)
        q   = self.initial_quote(item, allow_network=False)
        old_ltp = float(q.get("ltp") or 100.0)
        anchor  = float(q.get("close") or q.get("open") or old_ltp)

        # Micro-movement with mean-reversion pull to prevent runaway random walks
        pull = (anchor - old_ltp) * 0.05
        noise = random.gauss(0, max(0.1, anchor * 0.0004))
        delta = round(pull + noise, 2)
        if abs(delta) < 0.05:
            delta = 0.05 if random.random() > 0.5 else -0.05

        new_ltp = max(0.5, round(old_ltp + delta, 2))
        close_px = float(q.get("close") or anchor)
        chg     = round(new_ltp - close_px, 2)
        pct     = round((chg / close_px) * 100.0, 2) if close_px else 0.0

        tick = {
            "scripCode":    item.get("scripCode"),
            "exchangeCode": item.get("exchange", "NC"),
            "tradingSymbol": item.get("tradingSymbol") or q.get("tradingSymbol"),
            "ltp":          new_ltp,
            "rsChange":     chg,
            "perChange":    pct,
            "bidPrice":     round(new_ltp - 0.05, 2),
            "offPrice":     new_ltp,
            "high":         max(float(q.get("high") or new_ltp), new_ltp),
            "low":          min(float(q.get("low")  or new_ltp), new_ltp),
            "close":        close_px,
            "qty":          int(q.get("qty") or 1000) + random.randint(10, 500),
        }
        self._process_tick(tick)
