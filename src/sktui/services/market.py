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
    def handle_ws(self, msg: dict) -> None:
        """Route a raw WebSocket message to the appropriate handler."""
        data = msg.get("data") if isinstance(msg, dict) else None
        if isinstance(data, dict):
            if "AckState" in data or "SharekhanOrderID" in data:
                if self.on_ack_update:
                    self.on_ack_update(data)
                return
            if "scripCode" in data and ("ltp" in data or "lastTradedPrice" in data):
                self._process_tick(data)

    # ── Tick processing ───────────────────────────────────────────────────────
    def _process_tick(self, d: dict) -> None:
        code = d.get("scripCode")
        exch = d.get("exchangeCode") or d.get("exchange") or "NC"
        key  = f"{exch}{code}"

        prev_ltp = self._quotes.get(key).get("ltp")
        new_ltp  = self._quotes.update(key, d)

        if self.on_tick_update:
            self.on_tick_update(key, self._quotes.raw_ticks[key], prev_ltp, new_ltp)

    # ── Initial / simulated quotes ────────────────────────────────────────────
    _BASE_PRICES: dict[str, tuple] = {
        "ONGC":      (248.50, 2.10,   0.85, 248.45, 248.50, 246.00, 249.20, 245.80, 246.40, 4820100, 12450),
        "RELIANCE":  (2980.00, -12.50, -0.42, 2979.80, 2980.00, 2990.00, 3005.00, 2972.00, 2992.50, 2150000, 85000),
        "TCS":       (4250.00, 35.00,  0.83, 4249.50, 4250.00, 4220.00, 4265.00, 4215.00, 4215.00, 1200000, 45000),
        "INFY":      (1890.00, 15.20,  0.81, 1889.50, 1890.00, 1875.00, 1898.00, 1870.00, 1874.80, 3500000, 62000),
        "HDFCBANK":  (1650.00, 8.40,   0.51, 1649.80, 1650.00, 1642.00, 1658.00, 1640.00, 1641.60, 5800000, 110000),
        "SBIN":      (825.00, -4.20,  -0.51, 824.80,  825.00,  829.00,  832.00,  822.00,  829.20,  7200000, 94000),
        "TATAMOTORS":(965.00, 11.30,   1.18, 964.80,  965.00,  955.00,  970.00,  952.00,  953.70,  6100000, 82000),
        "BHARTIARTL":(1540.00, 6.80,   0.44, 1539.50, 1540.00, 1535.00, 1545.00, 1530.00, 1533.20, 2800000, 39000),
    }

    def initial_quote(self, item: dict) -> dict:
        """Return an initial quote for *item*, seeding the store if needed."""
        key = WatchlistStore.feed_key(item)
        existing = self._quotes.get(key)
        if existing and existing.get("ltp"):
            return existing

        sym  = str(item.get("tradingSymbol", "")).upper()
        bp   = self._BASE_PRICES.get(sym)
        if bp:
            p, c, pct, b, a, o, h, l, cl, v, oi = bp
        else:
            code = int(item.get("scripCode") or 1000)
            p   = float(code % 1500) + 120.0
            c   = float((code % 18) - 9)
            pct = round((c / p) * 100, 2) if p else 0.0
            b, a, o, h, l, cl, v, oi = (
                p - 0.05, p, p - c, p + abs(c) + 2.0,
                max(1.0, p - abs(c) - 2.0), p - c, 185000, 8500,
            )

        q = {
            "scripCode":    item.get("scripCode"),
            "exchangeCode": item.get("exchange", "NC"),
            "ltp": p, "rsChange": c, "perChange": pct,
            "bidPrice": b, "offPrice": a, "open": o,
            "high": h, "low": l, "close": cl, "qty": v, "currentOI": oi,
        }
        self._quotes.seed(key, q)
        self._quotes.seed_history(
            key,
            [p * (1 + (random.random() - 0.5) * 0.01) for _ in range(15)],
        )
        return self._quotes.get(key)

    def simulate_tick(self, item: dict) -> None:
        """Fire a simulated micro price movement for *item*.

        Used in paper / offline mode so the watchlist and dashboard stay alive.
        """
        key = WatchlistStore.feed_key(item)
        q   = self.initial_quote(item)
        old_ltp = float(q.get("ltp") or 100.0)
        delta   = round(random.gauss(0, old_ltp * 0.0015), 2) or 0.05
        new_ltp = max(0.5, round(old_ltp + delta, 2))
        chg     = round(float(q.get("rsChange") or 0) + delta, 2)
        op      = float(q.get("open") or new_ltp)
        pct     = round((chg / op) * 100, 2) if op else 0.0

        tick = {
            "scripCode":    item.get("scripCode"),
            "exchangeCode": item.get("exchange", "NC"),
            "ltp":          new_ltp,
            "rsChange":     chg,
            "perChange":    pct,
            "bidPrice":     round(new_ltp - 0.05, 2),
            "offPrice":     new_ltp,
            "high":         max(float(q.get("high") or new_ltp), new_ltp),
            "low":          min(float(q.get("low")  or new_ltp), new_ltp),
            "qty":          int(q.get("qty") or 1000) + random.randint(10, 500),
        }
        self._process_tick(tick)
