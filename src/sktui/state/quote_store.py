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

import json
import math
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sktui.config import DATA
from sktui.utils import read_json, safe_float, write_private

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
        # Level 2 Market Depth (5-level order book)
        self.depth_book: dict[str, dict[str, Any]] = {}
        try:
            self.load_tape()
        except Exception:
            pass

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

        if max_bars <= 0:
            return []
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
        if not q or q.get("ltp") is None:
            return None
        val = safe_float(q.get("ltp"), default=-1.0)
        return val if val >= 0.0 else None

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
            or tick.get("close")
            or tick.get("Close")
            or tick.get("c")
        )
        if ltp_val is not None:
            fltp = safe_float(ltp_val, default=-1.0)
            if fltp <= 0.0:
                return None
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

            if "bids" in tick or "bidPrice1" in tick or "bp1" in tick:
                self.update_depth(key, tick)

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

    # ── Tape Persistence ──────────────────────────────────────────────────────
    def save_tape(self, path: Path | None = None) -> int:
        """Persist current intraday tick tape to disk for session continuity."""
        target_path = path or (DATA / "intraday_tick_tape.json")
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        out: dict[str, list[list[float]]] = {}
        total_ticks = 0
        for key, tape in list(self.tick_tape.items()):
            valid = [list(entry) for entry in tape if entry[0] >= midnight]
            if valid:
                out[key] = valid[-self.MAX_TAPE:]
                total_ticks += len(valid)
        try:
            write_private(target_path, out)
            return total_ticks
        except Exception:
            return 0

    def load_tape(self, path: Path | None = None) -> int:
        """Restore intraday tick tape from disk to resume candles across restarts."""
        target_path = path or (DATA / "intraday_tick_tape.json")
        try:
            data = read_json(target_path, None)
            if not isinstance(data, dict):
                return 0
            midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            restored = 0
            for key, entries in data.items():
                if not isinstance(entries, list):
                    continue
                valid = [
                    tuple(e) for e in entries
                    if isinstance(e, (list, tuple)) and len(e) >= 3 and e[0] >= midnight
                ]
                if valid:
                    tape = self.tick_tape.get(key)
                    if tape is None:
                        tape = self.tick_tape[key] = deque(maxlen=self.MAX_TAPE)
                    for item in valid[-self.MAX_TAPE:]:
                        tape.append((float(item[0]), float(item[1]), float(item[2])))
                        restored += 1
                    if valid and key not in self.raw_ticks:
                        latest_entry = valid[-1]
                        self.raw_ticks[key] = {
                            "ltp": latest_entry[1],
                            "source": "persisted_tape",
                        }
                        self.tick_timestamps[key] = time.monotonic()
            return restored
        except Exception:
            return 0

    # ── Market Depth L2 Support ───────────────────────────────────────────────
    def update_depth(self, key: str, depth_info: dict) -> dict:
        """Store Level-2 Market Depth book containing 5 levels of bids and asks."""
        bids: list[tuple[float, int]] = []
        asks: list[tuple[float, int]] = []

        if "bids" in depth_info and isinstance(depth_info["bids"], list):
            for b in depth_info["bids"][:5]:
                if isinstance(b, (list, tuple)) and len(b) >= 2:
                    bids.append((float(b[0]), int(b[1])))
                elif isinstance(b, dict):
                    p = safe_float(b.get("price") or b.get("rate") or 0.0)
                    q = int(safe_float(b.get("quantity") or b.get("qty") or 0))
                    if p > 0 and q > 0:
                        bids.append((p, q))
        else:
            for i in range(1, 6):
                bp = safe_float(depth_info.get(f"bidPrice{i}") or depth_info.get(f"bp{i}") or 0.0)
                bq = int(safe_float(depth_info.get(f"bidQty{i}") or depth_info.get(f"bq{i}") or 0))
                if bp > 0 and bq > 0:
                    bids.append((bp, bq))

        if "asks" in depth_info and isinstance(depth_info["asks"], list):
            for a in depth_info["asks"][:5]:
                if isinstance(a, (list, tuple)) and len(a) >= 2:
                    asks.append((float(a[0]), int(a[1])))
                elif isinstance(a, dict):
                    p = safe_float(a.get("price") or a.get("rate") or 0.0)
                    q = int(safe_float(a.get("quantity") or a.get("qty") or 0))
                    if p > 0 and q > 0:
                        asks.append((p, q))
        else:
            for i in range(1, 6):
                ap = safe_float(depth_info.get(f"askPrice{i}") or depth_info.get(f"ap{i}") or 0.0)
                aq = int(safe_float(depth_info.get(f"askQty{i}") or depth_info.get(f"aq{i}") or 0))
                if ap > 0 and aq > 0:
                    asks.append((ap, aq))

        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        total_b_qty = sum(q for _, q in bids)
        total_a_qty = sum(q for _, q in asks)
        tot = total_b_qty + total_a_qty
        imbal = round(((total_b_qty - total_a_qty) / tot * 100.0), 1) if tot > 0 else 0.0

        spread = round(asks[0][0] - bids[0][0], 2) if bids and asks else 0.0

        book = {
            "bids": bids,
            "asks": asks,
            "total_bid_qty": total_b_qty,
            "total_ask_qty": total_a_qty,
            "spread": max(0.0, spread),
            "imbalance_pct": imbal,
            "updated_at": time.time(),
        }
        self.depth_book[key] = book
        return book

    def get_depth(self, key: str, fallback_ltp: float | None = None) -> dict[str, Any]:
        """Return 5-level market depth order book for *key*.

        If broker feeds real L2 depth, returns authentic order book.
        Otherwise synthesizes realistic, responsive depth around the current LTP
        so the DOM ladder remains visually interactive in paper sandbox and standard LTP streams.
        """
        if key in self.depth_book and self.depth_book[key].get("bids"):
            return self.depth_book[key]

        raw = self.raw_ticks.get(key, {})
        ltp = safe_float(raw.get("ltp"), default=0.0) or fallback_ltp or 0.0
        if ltp <= 0:
            # No live price yet: never fabricate a ladder around a made-up price.
            return {
                "bids": [], "asks": [], "total_bid_qty": 0, "total_ask_qty": 0,
                "spread": 0.0, "imbalance_pct": 0.0, "synthetic": True,
                "updated_at": time.time(),
            }

        tick_size = 0.05 if ltp < 10000 else 0.50
        bid1 = safe_float(raw.get("bidPrice"), default=0.0)
        ask1 = safe_float(raw.get("offPrice"), default=0.0)
        if bid1 <= 0 or ask1 <= 0 or bid1 >= ask1:
            bid1 = round(ltp - tick_size, 2)
            ask1 = round(ltp + tick_size, 2)

        vol = max(100.0, safe_float(raw.get("qty") or raw.get("volume"), default=5000.0))
        base_lot = max(1, int(vol * 0.002))

        bids = [
            (round(bid1 - (i * tick_size), 2), int(base_lot * (1.2 + (i * 0.4))))
            for i in range(5)
        ]
        asks = [
            (round(ask1 + (i * tick_size), 2), int(base_lot * (1.1 + (i * 0.35))))
            for i in range(5)
        ]

        total_b = sum(q for _, q in bids)
        total_a = sum(q for _, q in asks)
        tot = total_b + total_a
        imbal = round(((total_b - total_a) / tot * 100.0), 1) if tot > 0 else 0.0
        spread = round(asks[0][0] - bids[0][0], 2)

        synth_book = {
            "bids": bids,
            "asks": asks,
            "total_bid_qty": total_b,
            "total_ask_qty": total_a,
            "spread": max(0.0, spread),
            "imbalance_pct": imbal,
            "synthetic": True,
            "updated_at": time.time(),
        }
        self.depth_book[key] = synth_book
        return synth_book

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
