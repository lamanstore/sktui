"""Quote store — raw tick cache, per-scrip tick history, and feed health monitoring.

The store owns:
  - raw_ticks          : {feed_key -> latest tick dict} (updated on every WS frame)
  - tick_history       : {feed_key -> list[float]} (last 60 LTP values)
  - tick_timestamps    : {feed_key -> float} monotonic time of arrival
  - normalise_tick()   : maps all known WS field variants to canonical names
  - staleness_status() : FRESH (<2s), WARM (<10s), STALE (>=10s), NO_DATA
  - feed health metrics: tick rate, latency, and status
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any


class QuoteStore:
    """In-memory store for live market data ticks with staleness and feed health tracking."""

    #: Maximum tick history kept per scrip.
    MAX_HISTORY = 60

    def __init__(self) -> None:
        self.raw_ticks: dict[str, dict] = {}
        self.tick_history: dict[str, list[float]] = {}
        self.tick_timestamps: dict[str, float] = {}
        self._recent_tick_times: deque[float] = deque(maxlen=500)
        self.total_ticks: int = 0
        self.feed_state: str = "CONNECTED"  # CONNECTED | RECONNECTING | DISCONNECTED
        self.last_ping_ms: float = 12.0

    # ── Reading ───────────────────────────────────────────────────────────────
    def get(self, key: str) -> dict:
        """Return the latest tick dict for a feed key, or empty dict."""
        return self.raw_ticks.get(key, {})

    def ltp(self, key: str) -> float | None:
        q = self.raw_ticks.get(key)
        return float(q["ltp"]) if q and q.get("ltp") is not None else None

    def history(self, key: str) -> list[float]:
        return self.tick_history.get(key, [])

    # ── Staleness & Feed Health ───────────────────────────────────────────────
    def staleness_status(self, key: str) -> tuple[str, str]:
        """Return (StatusLabel, ColorHex) for the given symbol feed key."""
        t = self.tick_timestamps.get(key)
        if t is None:
            return ("NO_DATA", "#888888")
        age = time.monotonic() - t
        if age < 2.5:
            return ("FRESH", "#00ff87")
        if age < 12.0:
            return ("WARM", "#ffaa00")
        return (f"STALE ({int(age)}s)", "#ff5f5f")

    @property
    def ticks_per_sec(self) -> float:
        """Calculate ticks received per second over the recent window."""
        now = time.monotonic()
        while self._recent_tick_times and self._recent_tick_times[0] < now - 5.0:
            self._recent_tick_times.popleft()
        return len(self._recent_tick_times) / 5.0

    def feed_health_summary(self) -> dict[str, Any]:
        """Return a structured feed health diagnostic dictionary."""
        return {
            "state": self.feed_state,
            "total_ticks": self.total_ticks,
            "tps": round(self.ticks_per_sec, 1),
            "ping_ms": round(self.last_ping_ms, 1),
            "active_symbols": len(self.raw_ticks),
        }

    def feed_badge(self) -> tuple[str, str]:
        """Return formatted connection badge text and style color for UI headers.

        Formats:
        - ● LIVE 18ms (green #00ff87)
        - ▲ STALE 3.2s (amber #f59e0b)
        - ■ RECONNECTING (amber #f59e0b)
        - ✕ OFFLINE (crimson #ff4757)
        """
        if self.feed_state == "DISCONNECTED":
            return ("✕ OFFLINE", "#ff4757")
        if self.feed_state == "RECONNECTING":
            return ("■ RECONNECTING", "#f59e0b")
        if self.tick_timestamps:
            now = time.monotonic()
            latest_t = max(self.tick_timestamps.values())
            age = now - latest_t
            if age >= 2.5:
                return (f"▲ STALE {age:.1f}s", "#f59e0b")
        return (f"● LIVE {self.last_ping_ms:.0f}ms", "#00ff87")

    # ── Writing ───────────────────────────────────────────────────────────────
    def update(self, key: str, tick: dict) -> float | None:
        """Merge *tick* into the store and return the new LTP (or None)."""
        now = time.monotonic()
        self.tick_timestamps[key] = now
        self._recent_tick_times.append(now)
        self.total_ticks += 1
        self.feed_state = "CONNECTED"

        self.raw_ticks.setdefault(key, {}).update(tick)

        # Normalise all known field variants to canonical "ltp"
        raw = self.raw_ticks[key]
        ltp_val = tick.get("ltp") or tick.get("lastTradedPrice") or tick.get("LTP")
        if ltp_val is not None:
            fltp = float(ltp_val)
            raw["ltp"] = fltp
            hist = self.tick_history.setdefault(key, [])
            hist.append(fltp)
            if len(hist) > self.MAX_HISTORY:
                hist.pop(0)
            return fltp
        return None

    def seed(self, key: str, quote: dict) -> None:
        """Seed an initial quote without overwriting real ticks."""
        if key not in self.raw_ticks:
            self.raw_ticks[key] = dict(quote)
            self.tick_timestamps[key] = time.monotonic()

    def seed_history(self, key: str, values: list[float]) -> None:
        """Pre-populate tick history (e.g. with simulated data)."""
        if key not in self.tick_history:
            self.tick_history[key] = list(values)

    # ── Helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def canonical(tick: dict) -> dict:
        """Map all known API field name variants to canonical names."""
        c = dict(tick)
        for dst, srcs in (
            ("ltp",       ("lastTradedPrice", "LTP")),
            ("rsChange",  ("change", "netPriceChange")),
            ("perChange", ("pChange", "percentChange")),
            ("bidPrice",  ("bid",)),
            ("offPrice",  ("ask",)),
            ("open",      ("openPrice",)),
            ("high",      ("highPrice",)),
            ("low",       ("lowPrice",)),
            ("close",     ("closePrice",)),
            ("qty",       ("volume", "vol")),
            ("currentOI", ("openInterest", "oi")),
        ):
            if dst not in c:
                for src in srcs:
                    if src in c:
                        c[dst] = c[src]
                        break
        return c
