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
from sktui.utils import resolve_symbol, safe_float


class MarketService:
    """Processes market data ticks and routes feed events.

    Parameters
    ----------
    quotes:    QuoteStore instance to update on each tick.
    watchlist: WatchlistStore used to seed initial quotes.
    """

    def __init__(self, quotes: QuoteStore, watchlist: WatchlistStore, client: Any = None) -> None:
        self._quotes    = quotes
        self._watchlist = watchlist
        self._client    = client
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
            for container_key in ("data", "feed", "feeds", "ticks", "result", "records"):
                if container_key in msg:
                    content = msg[container_key]
                    if isinstance(content, list):
                        for row in content:
                            if isinstance(row, dict):
                                self._handle_single_data(row)
                        return
                    if isinstance(content, dict):
                        self._handle_single_data(content)
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
        raw_q = self._quotes.raw_ticks.get(key, {})
        if not raw_q.get("tradingSymbol"):
            sym = resolve_symbol(code, exchange=exch, watch=self._watchlist.items)
            if sym and not sym.isdigit():
                raw_q["tradingSymbol"] = sym

        if self.on_tick_update:
            self.on_tick_update(key, raw_q, prev_ltp, new_ltp)

    # ── Initial / simulated quotes ────────────────────────────────────────────
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
            p_cand = safe_float(item.get("ltp") or item.get("lastTradedPrice"), 0.0)
            if p_cand > 0:
                p = p_cand
                c = safe_float(item.get("rsChange"), 0.0)
                pct = safe_float(item.get("perChange"), 0.0)
                cl = safe_float(item.get("close"), (p - c if c else p))
                o = safe_float(item.get("open"), p)
                h = safe_float(item.get("high"), max(p, o))
                l = safe_float(item.get("low"), min(p, o))
                v = safe_float(item.get("qty") or item.get("volume"), 150000.0)
                b = safe_float(item.get("bidPrice"), round(p - 0.05, 2))
                a = safe_float(item.get("offPrice"), p)
                oi = int(safe_float(item.get("currentOI"), 0.0))

        # 2. Second priority: Query authentic Sharekhan REST quote snapshot
        if p is None and sym and allow_network:
            cli = getattr(self, "_client", None)
            if cli and hasattr(cli, "quote"):
                code = item.get("scripCode") or item.get("scrip_code") or item.get("code")
                if not code and sym:
                    from sktui.utils import resolve_code
                    code = resolve_code(sym, exch, self._watchlist.items if self._watchlist else None)
                if code:
                    try:
                        cq = cli.quote(exch, code)
                        if cq and cq.get("ltp"):
                            p = float(cq["ltp"])
                            cl = float(cq.get("close") or p)
                            c = float(cq.get("rsChange") or round(p - cl, 2))
                            pct = float(cq.get("perChange") or (round((c / cl * 100.0), 2) if cl else 0.0))
                            o = float(cq.get("open") or p)
                            h = float(cq.get("high") or p)
                            l = float(cq.get("low") or p)
                            v = float(cq.get("qty") or 100000)
                            b = float(cq.get("bidPrice") or round(p - 0.05, 2))
                            a = float(cq.get("offPrice") or p)
                            oi = int(cq.get("currentOI") or 10000)
                    except Exception:
                        pass

        # 3. Third priority: Baseline fallback
        cli = getattr(self, "_client", None)
        is_live_broker = cli is not None and not getattr(cli, "paper", False) and getattr(cli, "access_token", "")
        if p is not None:
            source = "real"
        elif is_live_broker:
            # In authenticated live broker mode, do not inject fake trades; await authentic feed
            source = "awaiting_feed"
            p = None
            c, pct, b, a, o, h, l, cl, v, oi = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0
        else:
            source = "baseline"
            from sktui.config import KNOWN_BASE_PRICES
            if sym in KNOWN_BASE_PRICES:
                p = KNOWN_BASE_PRICES[sym]
                c = round(p * 0.005, 2)
                pct = 0.50
                b, a, o, h, l, cl, v, oi = (
                    round(p - 0.05, 2), p, p - c, round(p + abs(c) + 1.0, 2),
                    round(max(1.0, p - abs(c) - 1.0), 2), p - c, 250000, 15000,
                )
            else:
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

        return self._quotes.get(key)

    @staticmethod
    def _synthetic_tape(
        price: float, n: int = 0, span_sec: float = 1200.0,
    ) -> list[tuple[float, float, float]]:
        """Deprecated: real terminal relies on authentic market feed ticks."""
        return []

    def simulate_tick(self, item: dict) -> None:
        """Fire a simulated micro price movement for *item*.

        Used in paper / offline mode so the watchlist and dashboard stay alive.
        Applies mean-reverting micro-fluctuations around the base market price.
        """
        key = WatchlistStore.feed_key(item)
        existing = self._quotes.get(key)
        if existing and existing.get("ltp"):
            q = existing
        else:
            q = self.initial_quote(item, allow_network=False)
        old_ltp = safe_float(q.get("ltp"), 100.0)
        if old_ltp <= 0:
            old_ltp = 100.0
        anchor  = safe_float(q.get("close") or q.get("open"), old_ltp)
        if anchor <= 0:
            anchor = old_ltp

        # Micro-movement with mean-reversion pull to prevent runaway random walks
        pull = (anchor - old_ltp) * 0.05
        noise = random.gauss(0, max(0.1, anchor * 0.0004))
        delta = round(pull + noise, 2)
        if abs(delta) < 0.05:
            delta = 0.05 if random.random() > 0.5 else -0.05

        new_ltp = max(0.5, round(old_ltp + delta, 2))
        close_px = safe_float(q.get("close"), anchor) or anchor
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
            "high":         max(safe_float(q.get("high"), new_ltp), new_ltp),
            "low":          min(safe_float(q.get("low"),  new_ltp) or new_ltp, new_ltp),
            "close":        close_px,
            "qty":          int(safe_float(q.get("qty"), 1000.0)) + random.randint(10, 500),
        }
        self._process_tick(tick)
