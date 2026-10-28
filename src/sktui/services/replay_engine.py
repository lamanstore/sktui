"""Historical Candle & Tick Replay Engine for SKTUI.

Simulates live market sessions by playing back historical candlestick bars
into the MarketService and QuoteStore tick-by-tick.
Ideal for testing alerts, trailing stop losses, risk rules, and UI responsiveness.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Sequence

from sktui.chart import Candle


class ReplayEngine:
    """Historical session replay engine for strategy and UI verification."""

    def __init__(
        self,
        on_tick: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.on_tick = on_tick
        self._sequence: list[dict[str, Any]] = []
        self._cursor: int = 0
        self._is_playing: bool = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.symbol: str = ""
        self.exchange: str = "NC"
        self.speed: float = 1.0  # 1.0 = real-time, 5.0 = 5x speed

    @property
    def total_ticks(self) -> int:
        return len(self._sequence)

    @property
    def current_tick_index(self) -> int:
        return self._cursor

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def load_candles(
        self,
        symbol: str,
        exchange: str,
        candles: Sequence[Candle],
        scrip_code: int = 2475,
    ) -> None:
        """Deconstruct candles into synthetic multi-step tick sequence."""
        self.symbol = symbol
        self.exchange = exchange
        self._sequence.clear()
        self._cursor = 0

        running_high = float("-inf")
        running_low = float("inf")
        running_vol = 0.0

        for c in candles:
            sub_vol = c.volume / 4.0 if c.volume > 0 else 100.0

            # Deconstruct bar into 4 realistic price micro-steps:
            # 1. Open
            # 2. Extreme 1 (Low if bullish, High if bearish)
            # 3. Extreme 2 (High if bullish, Low if bearish)
            # 4. Close
            if c.is_bullish:
                prices = [c.open, c.low, c.high, c.close]
            else:
                prices = [c.open, c.high, c.low, c.close]

            for p in prices:
                running_high = max(running_high, p)
                running_low = min(running_low, p)
                running_vol += sub_vol
                tick = {
                    "exchangeCode": exchange,
                    "scripCode": scrip_code,
                    "tradingSymbol": symbol,
                    "ltp": float(p),
                    "high": float(running_high),
                    "low": float(running_low),
                    "open": float(candles[0].open),
                    "close": float(candles[0].open),
                    "rsChange": float(p - candles[0].open),
                    "perChange": float((p - candles[0].open) / candles[0].open * 100.0) if candles[0].open else 0.0,
                    "qty": float(running_vol),
                    "volume": float(running_vol),
                    "bidPrice": float(p - 0.05),
                    "offPrice": float(p + 0.05),
                }
                self._sequence.append(tick)

    def step(self) -> dict[str, Any] | None:
        """Advance replay by single tick step."""
        if self._cursor >= len(self._sequence):
            self._is_playing = False
            return None
        tick = self._sequence[self._cursor]
        self._cursor += 1
        if self.on_tick:
            self.on_tick(tick)
        return tick

    def run_all(self) -> int:
        """Synchronously step through all remaining ticks in the sequence."""
        count = 0
        while self.step() is not None:
            count += 1
        return count

    def reset(self) -> None:
        """Reset replay playback to the start."""
        self.pause()
        self._cursor = 0

    def pause(self) -> None:
        """Pause continuous playback."""
        self._is_playing = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def play(self, tick_delay_s: float = 0.2) -> None:
        """Start background continuous tick playback."""
        if self._is_playing:
            return
        self._is_playing = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_playback,
            args=(tick_delay_s,),
            daemon=True,
        )
        self._thread.start()

    def _run_playback(self, delay: float) -> None:
        eff_delay = max(0.01, delay / max(0.1, self.speed))
        while not self._stop_event.is_set():
            tick = self.step()
            if tick is None:
                break
            time.sleep(eff_delay)
        self._is_playing = False
