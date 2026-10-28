"""Chart panel widget — renders braille or candlestick analytical charts with indicators.

Provides a Textual Static widget that fetches history from the client
and renders it using the upgraded chart renderer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.widgets import Static

from sktui import chart as _chart
from sktui.config import INTERVAL_LABELS
from sktui.utils import scrip_label

if TYPE_CHECKING:
    from sktui.api.client import Client


class ChartPanel(Static):
    """A Textual Static widget that renders analytical price & volume charts.

    Supports both Braille-dot line charts and full OHLC Candlestick charts
    with EMA, RSI, and directional volume panels.
    """

    DEFAULT_CSS = ""

    def __init__(
        self,
        item: dict,
        client: "Client",
        interval: str = "daily",
        mode: str = "candle",  # "candle" | "line"
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__("", id=id, classes=classes)
        self._item = item
        self._client = client
        self._interval = interval
        self.mode = mode
        self.show_ema: bool = True
        self.show_rsi: bool = True

    def on_mount(self) -> None:
        self._render()

    def set_interval_label(self, interval: str) -> None:
        self._interval = interval
        self._render()

    def toggle_mode(self) -> str:
        self.mode = "line" if self.mode == "candle" else "candle"
        self._render()
        return self.mode

    def toggle_ema(self) -> bool:
        self.show_ema = not self.show_ema
        self._render()
        return self.show_ema

    def toggle_rsi(self) -> bool:
        self.show_rsi = not self.show_rsi
        self._render()
        return self.show_rsi

    # ── Internal ──────────────────────────────────────────────────────────────
    def _render(self) -> None:
        item = self._item
        sym = scrip_label(item)
        try:
            rows = self._client.historical(
                item["exchange"], item["scripCode"], self._interval
            )
        except Exception as e:
            self.update(f"  — chart error: {e} —")
            return

        label_str = INTERVAL_LABELS.get(self._interval, self._interval)
        w = max(60, self.size.width - 12 if self.size.width > 20 else 78)

        if self.mode == "candle":
            candles: list[_chart.Candle] = []
            for r in rows:
                try:
                    c_open = float(r.get("open") or r.get("openPrice") or r.get("close") or 0.0)
                    c_high = float(r.get("high") or r.get("highPrice") or c_open)
                    c_low = float(r.get("low") or r.get("lowPrice") or c_open)
                    c_close = float(r.get("close") or r.get("closePrice") or c_open)
                    c_vol = float(r.get("volume") or r.get("qty") or 0.0)
                    ts = str(r.get("date") or r.get("timestamp") or "")
                    if c_close > 0:
                        candles.append(
                            _chart.Candle(
                                timestamp=ts,
                                open=c_open,
                                high=max(c_high, c_open, c_close),
                                low=min(c_low, c_open, c_close),
                                close=c_close,
                                volume=c_vol,
                            )
                        )
                except Exception:
                    continue

            if candles:
                rendered = _chart.render_candlestick_chart(
                    candles=candles,
                    width=w,
                    height=14,
                    symbol=sym,
                    interval=label_str,
                    show_ema=self.show_ema,
                    show_rsi=self.show_rsi,
                )
                self.update(rendered)
                return

        # Fallback to Braille Line chart
        closes = [float(r.get("close") or 0) for r in rows if r.get("close")]
        volumes = [float(r.get("volume") or r.get("qty") or 0) for r in rows]

        rendered = _chart.render_chart(
            closes,
            volumes if any(v > 0 for v in volumes) else None,
            width=w,
            height=14,
            symbol=sym,
            interval=label_str,
        )
        self.update(rendered)
