"""Quote store — raw tick cache, per-scrip tick history, and feed health monitoring.

The store owns:
  - raw_ticks          : {feed_key -> latest tick dict} (updated on every WS frame)
  - tick_history       : {feed_key -> list[float]} (last 120 LTP values)
  - tick_tape          : {feed_key -> deque[(wall_ts, ltp, vol_delta)]} for sub-minute candles
  - listeners          : callbacks fired on every LTP tick (real-time charts)
  - tick_timestamps    : {feed_key -> float} monotonic time of arrival
  - normalise_tick()   : maps all known WS field variants to canonical names
  - staleness_status() : FRESH (<2s), WARM (<10s), STALE (>=10s), NO_DATA
  - feed health metrics: tick rate, latency, and status
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable

#: Listener signature: (feed_key, raw_tick, ltp, vol_delta)
TickListener = Callable[[str, dict, float, float], None]


class QuoteStore:
    """In-memory store for live market data ticks with staleness and feed health tracking."""

    #: Maximum tick history kept per scrip.
    MAX_HISTORY = 120
    #: Maximum wall-clock tick tape entries kept per scrip (for sub-minute candles).
    MAX_TAPE = 2400

    def __init__(self) -> None:
        self.raw_ticks: dict[str, dict] = {}
        self.tick_history: dict[str, list[float]] = {}
        self.tick_timestamps: dict[str, float] = {}
        self._recent_tick_times: deque[float] = deque(maxlen=500)
        self.total_ticks: int = 0
        self.feed_state: str = "CONNECTED"  # CONNECTED | RECONNECTING | DISCONNECTED
        self.last_ping_ms: float = 12.0
        # Real-time tick tape: (wall_ts, ltp, vol_delta)
        self.tick_tape: dict[str, deque[tuple[float, float, float]]] = {}
        self.seeded_tape: dict[str, list[tuple[float, float, float]]] = {}
        self._last_cum_vol: dict[str, float] = {}
        self._listeners: list[TickListener] = []

    # ── Live listeners ────────────────────────────────────────────────────────
    def add_listener(self, fn: TickListener) -> None:
        """Register *fn* to be called synchronously on every LTP-bearing tick."""
        if fn not in self._listeners:
            self._listeners.append(fn)

    def remove_listener(self, fn: TickListener) -> None:
        try:
            self._listeners.remove(fn)
        except ValueError:
            pass

    def has_live_ticks(self, key: str) -> bool:
        """True if real ticks (not seeded data) have been recorded for *key*."""
        return bool(self.tick_tape.get(key))

    def seed_tape(self, key: str, entries: list[tuple[float, float, float]]) -> None:
        """Pre-populate a synthetic tape so sub-minute charts have initial structure."""
        if key not in self.seeded_tape:
            self.seeded_tape[key] = sorted(entries)[-self.MAX_TAPE:]

    def tape(self, key: str, include_seeded: bool = True) -> list[tuple[float, float, float]]:
        live = list(self.tick_tape.get(key, ()))
        if not include_seeded:
            return live
        seeded = self.seeded_tape.get(key, [])
        if live and seeded:
            first = live[0][0]
            seeded = [e for e in seeded if e[0] < first]
        return seeded + live

    def get_candles(
        self,
        key: str,
        interval_sec: int,
        max_bars: int = 240,
        include_seeded: bool = True,
    ) -> list:
        """Build OHLCV candles from the tick tape.

        ``interval_sec <= 0`` produces one bar per tick (TICK chart).
        """
        from datetime import datetime

        from sktui.chart import Candle

        tape = self.tape(key, include_seeded)
        if not tape:
            return []
        out: list[Candle] = []
        if interval_sec <= 0:
            prev = None
            for ts, px, vd in tape[-max_bars:]:
                o = prev if prev is not None else px
                out.append(Candle(
                    timestamp=datetime.fromtimestamp(ts).strftime("%H:%M:%S"),
                    open=o, high=max(o, px), low=min(o, px), close=px, volume=vd,
                ))
                prev = px
            return out
        cur_bucket = None
        for ts, px, vd in tape:
            b = int(ts // interval_sec)
            if b != cur_bucket:
                cur_bucket = b
                fmt = "%H:%M:%S" if interval_sec < 60 else "%H:%M"
                out.append(Candle(
                    timestamp=datetime.fromtimestamp(b * interval_sec).strftime(fmt),
                    open=px, high=px, low=px, close=px, volume=vd,
                ))
            else:
                c = out[-1]
                c.high = max(c.high, px)
                c.low = min(c.low, px)
                c.close = px
                c.volume += vd
        return out[-max_bars:]

    # ── Reading ───────────────────────────────────────────────────────────────
    def get(self, key: str) -> dict:
        """Return the latest tick dict for a feed key, or empty dict."""
        return self.raw_ticks.get(key, {})

    def keys(self):
        """Return active feed keys in the store."""
        return self.raw_ticks.keys()

    def items(self):
        """Return active key-value pairs in the store."""
        return self.raw_ticks.items()

    def ltp(self, key: str) -> float | None:
        q = self.raw_ticks.get(key)
        return float(q["ltp"]) if q and q.get("ltp") is not None else None

    def history(self, key: str) -> list[float]:
        return self.tick_history.get(key, [])

    # ── Staleness & Feed Health ───────────────────────────────────────────────
    def is_stale(self, key: str, threshold: float = 5.0) -> bool:
        """Return True if *key* has not received a tick within *threshold* seconds."""
        t = self.tick_timestamps.get(key)
        if t is None:
            return True
        return (time.monotonic() - t) >= threshold

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
        if age < 30.0:
            return (f"STALE ({int(age)}s)", "#ff5f5f")
        return (f"DEAD ({int(age)}s)", "#ef4444")

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
            return ("✗ DEAD", "#ff4757")
        if self.feed_state == "RECONNECTING":
            return ("■ RECONNECTING", "#f59e0b")
        if self.tick_timestamps:
            now = time.monotonic()
            latest_t = max(self.tick_timestamps.values())
            age = now - latest_t
            if age >= 30.0:
                return (f"✗ DEAD ({int(age)}s)", "#ff4757")
            if age >= 2.5:
                return (f"⚠ STALE ({age:.1f}s)", "#f59e0b")
            return (f"● LIVE ({age:.1f}s · {self.last_ping_ms:.0f}ms)", "#00ff87")
        return (f"● LIVE ({self.last_ping_ms:.0f}ms)", "#00ff87")

    # ── Writing ───────────────────────────────────────────────────────────────
    def update(self, key: str, tick: dict, wall_ts: float | None = None) -> float | None:
        """Merge *tick* into the store and return the new LTP (or None).

        LTP-bearing ticks are also appended to the wall-clock tick tape (used to
        build zero-lag sub-minute candles) and broadcast to registered listeners.
        """
        now = time.monotonic()
        self.tick_timestamps[key] = now
        self._recent_tick_times.append(now)
        self.total_ticks += 1
        self.feed_state = "CONNECTED"

        self.raw_ticks.setdefault(key, {}).update(tick)

        # Normalise all known field variants to canonical "ltp"
        raw = self.raw_ticks[key]
        ltp_val = (
            tick.get("ltp")
            or tick.get("lastTradedPrice")
            or tick.get("LastTradedPrice")
            or tick.get("LTP")
            or tick.get("tradePrice")
            or tick.get("price")
        )
        if ltp_val is not None:
            fltp = float(ltp_val)
            raw["ltp"] = fltp
            hist = self.tick_history.setdefault(key, [])
            hist.append(fltp)
            if len(hist) > self.MAX_HISTORY:
                hist.pop(0)

            # Map additional tick metadata into raw quote if provided
            for src, dst in [
                ("openPrice", "open"), ("OpenPrice", "open"), ("Open", "open"),
                ("highPrice", "high"), ("HighPrice", "high"), ("High", "high"),
                ("lowPrice", "low"), ("LowPrice", "low"), ("Low", "low"),
                ("closePrice", "close"), ("ClosePrice", "close"), ("Close", "close"),
                ("previousClose", "close"),
                ("change", "rsChange"), ("netChange", "rsChange"),
                ("percentChange", "perChange"), ("pChange", "perChange"),
                ("totalTradedVolume", "volume"), ("qty", "volume"), ("totalQty", "volume"),
                ("bidPrice", "bidPrice"), ("bp", "bidPrice"),
                ("askPrice", "offPrice"), ("offPrice", "offPrice"), ("ap", "offPrice"),
            ]:
                if src in tick and tick[src] is not None:
                    raw[dst] = tick[src]

            # Volume delta: explicit per-tick volume, else cumulative-volume diff
            vol_delta = 0.0
            tv = tick.get("tickVol") or tick.get("lastTradedQty") or tick.get("ltq")
            cum = tick.get("qty") or tick.get("volume") or tick.get("totalTradedVolume")
            try:
                if tv is not None:
                    vol_delta = max(0.0, float(tv))
                elif cum is not None:
                    fc = float(cum)
                    prev = self._last_cum_vol.get(key)
                    vol_delta = max(0.0, fc - prev) if prev is not None else 0.0
                    self._last_cum_vol[key] = fc
            except (TypeError, ValueError):
                vol_delta = 0.0

            ts = wall_ts if wall_ts is not None else time.time()
            tape = self.tick_tape.get(key)
            if tape is None:
                tape = self.tick_tape[key] = deque(maxlen=self.MAX_TAPE)
            tape.append((ts, fltp, vol_delta))

            for fn in list(self._listeners):
                try:
                    fn(key, raw, fltp, vol_delta)
                except Exception:
                    pass
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
