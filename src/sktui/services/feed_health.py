"""Feed Health Monitor for SKTUI.

Provides per-symbol feed staleness classification, feed quality scoring,
reconnect-state management, and latency histogram computation.
Designed to complement QuoteStore without replacing it.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


# ── Feed State Constants ──────────────────────────────────────────────────────

FRESH_THRESHOLD   = 2.5     # seconds — within this = FRESH (green)
WARM_THRESHOLD    = 10.0    # seconds — within this = WARM (amber)
STALE_THRESHOLD   = 30.0    # seconds — beyond this = DEAD (red)

LATENCY_WINDOW    = 100     # keep rolling window of last N ping samples


@dataclass
class FeedHealthStatus:
    """Snapshot of per-symbol or global feed health."""
    symbol: str = ""
    state: str = "FRESH"              # FRESH | WARM | STALE | DEAD | NO_DATA
    age_s: float = 0.0                # seconds since last tick
    tick_rate: float = 0.0            # ticks per second (rolling 5s)
    latency_ms: float = 0.0           # most recent ping RTT in ms
    badge_text: str = "● LIVE"
    badge_color: str = "#00ff87"
    is_stale: bool = False


class FeedHealthMonitor:
    """Centralised feed health and staleness tracker.

    Works alongside QuoteStore — call update_tick() for each incoming tick
    and ping() whenever a WebSocket heartbeat round-trip is measured.
    """

    def __init__(self, stale_threshold: float = STALE_THRESHOLD) -> None:
        self._stale_threshold = stale_threshold
        self._tick_timestamps: dict[str, float] = {}
        self._recent_ticks: deque[float] = deque(maxlen=500)
        self._latency_samples: deque[float] = deque(maxlen=LATENCY_WINDOW)
        self._total_ticks: int = 0
        self.feed_state: str = "CONNECTED"          # CONNECTED | RECONNECTING | DISCONNECTED
        self._reconnect_attempts: int = 0
        self._last_reconnect_at: float = 0.0

    # ── Incoming Events ───────────────────────────────────────────────────────

    def update_tick(self, symbol_key: str) -> None:
        """Record arrival of a live tick for *symbol_key*."""
        now = time.monotonic()
        self._tick_timestamps[symbol_key] = now
        self._recent_ticks.append(now)
        self._total_ticks += 1
        if self.feed_state != "CONNECTED":
            self.feed_state = "CONNECTED"
            self._reconnect_attempts = 0

    def ping(self, latency_ms: float) -> None:
        """Record a WebSocket ping/pong round-trip latency sample."""
        self._latency_samples.append(latency_ms)

    def set_reconnecting(self) -> None:
        """Signal that the WebSocket connection has dropped and is reconnecting."""
        self.feed_state = "RECONNECTING"
        self._reconnect_attempts += 1
        self._last_reconnect_at = time.monotonic()

    def set_disconnected(self) -> None:
        """Signal that the connection has been given up / shutdown."""
        self.feed_state = "DISCONNECTED"

    # ── Staleness Queries ─────────────────────────────────────────────────────

    def is_stale(self, symbol_key: str, threshold: float = FRESH_THRESHOLD) -> bool:
        """Return True if *symbol_key* has not been updated within *threshold* seconds."""
        t = self._tick_timestamps.get(symbol_key)
        if t is None:
            return True
        return (time.monotonic() - t) >= threshold

    def symbol_status(self, symbol_key: str) -> FeedHealthStatus:
        """Return detailed health status for a single symbol."""
        t = self._tick_timestamps.get(symbol_key)
        if t is None:
            return FeedHealthStatus(
                symbol=symbol_key, state="NO_DATA",
                badge_text="○ NO DATA", badge_color="#888888", is_stale=True,
            )
        age = time.monotonic() - t
        if age < FRESH_THRESHOLD:
            state, badge, color = "FRESH", "● LIVE", "#00ff87"
        elif age < WARM_THRESHOLD:
            state, badge, color = "WARM", f"◎ WARM {age:.1f}s", "#ffaa00"
        elif age < self._stale_threshold:
            state, badge, color = "STALE", f"▲ STALE {age:.0f}s", "#f59e0b"
        else:
            state, badge, color = "DEAD", f"✕ DEAD {age:.0f}s", "#ff4757"
        return FeedHealthStatus(
            symbol=symbol_key,
            state=state,
            age_s=round(age, 2),
            tick_rate=self.ticks_per_second,
            latency_ms=self.avg_latency_ms,
            badge_text=badge,
            badge_color=color,
            is_stale=age >= FRESH_THRESHOLD,
        )

    # ── Global Feed Metrics ───────────────────────────────────────────────────

    @property
    def ticks_per_second(self) -> float:
        """Rolling 5-second tick rate."""
        now = time.monotonic()
        cutoff = now - 5.0
        # Trim old entries
        while self._recent_ticks and self._recent_ticks[0] < cutoff:
            self._recent_ticks.popleft()
        return len(self._recent_ticks) / 5.0

    @property
    def avg_latency_ms(self) -> float:
        """Average ping latency over the rolling sample window."""
        if not self._latency_samples:
            return 0.0
        return sum(self._latency_samples) / len(self._latency_samples)

    @property
    def p95_latency_ms(self) -> float:
        """95th-percentile ping latency (sorted approximate)."""
        if not self._latency_samples:
            return 0.0
        s = sorted(self._latency_samples)
        idx = int(len(s) * 0.95)
        return s[min(idx, len(s) - 1)]

    def feed_badge(self) -> tuple[str, str]:
        """Return (badge_text, badge_color) for the header connection indicator."""
        if self.feed_state == "DISCONNECTED":
            return ("✕ OFFLINE", "#ff4757")
        if self.feed_state == "RECONNECTING":
            elapsed = time.monotonic() - self._last_reconnect_at
            return (f"■ RECONNECTING {elapsed:.0f}s", "#f59e0b")
        if self._tick_timestamps:
            latest_t = max(self._tick_timestamps.values())
            age = time.monotonic() - latest_t
            if age >= FRESH_THRESHOLD:
                return (f"▲ STALE {age:.1f}s", "#f59e0b")
        lat = self.avg_latency_ms
        ping_str = f"{lat:.0f}ms" if lat > 0 else "--ms"
        return (f"● LIVE {ping_str}", "#00ff87")

    def summary(self) -> dict[str, Any]:
        """Structured health diagnostic dictionary."""
        return {
            "state": self.feed_state,
            "total_ticks": self._total_ticks,
            "tps": round(self.ticks_per_second, 1),
            "avg_ping_ms": round(self.avg_latency_ms, 1),
            "p95_ping_ms": round(self.p95_latency_ms, 1),
            "active_symbols": len(self._tick_timestamps),
            "reconnect_attempts": self._reconnect_attempts,
        }

    def stale_symbols(self, threshold: float = WARM_THRESHOLD) -> list[str]:
        """Return list of symbol keys with age >= *threshold* seconds."""
        now = time.monotonic()
        return [
            key for key, t in self._tick_timestamps.items()
            if (now - t) >= threshold
        ]


# Global singleton — wired by MainScreen into the tick dispatch path
feed_health = FeedHealthMonitor()
