"""Symbol Focus Panel widget for SKTUI.

Prioritizes the currently selected symbol as the center of the trading workspace,
displaying comprehensive live quote, depth imbalance bar, spread, intraday range gauge,
volume, live braille chart, and position context without forcing horizontal table scroll.
"""
from __future__ import annotations

import math
import random
import time
from typing import Any

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from sktui.chart import render_candlestick_chart, render_chart, step_zoom
from sktui.config import INTERVAL_LABELS, INTERVAL_SECONDS, SECTOR_MAP
from sktui.themes import current_palette
from sktui.ui.widgets.chart_canvas import InteractiveChartCanvas
from sktui.ui.widgets.order_action import OrderActionWidget
from sktui.utils import (
    compact_number, format_change, get, safe_float, scrip_label, sign_style,
)

#: Timeframes available on the inline (tape-driven) workspace chart.
INLINE_TFS: list[str] = ["tick", "1second", "5second", "15second", "30second", "1minute"]


class SymbolFocusPanel(Static):
    """Selected symbol summary + microstructure metrics + live chart + stats.

    The inline chart is built from the real-time tick tape in ``QuoteStore`` so
    sub-minute candles form tick-by-tick.  When the panel (or its chart) has
    focus it accepts chart keys that do not shadow ``MainScreen`` shortcuts.
    """
    can_focus = True

    BINDINGS = [
        Binding("left_square_bracket", "chart_tf(-1)", "TF −", show=False),
        Binding("right_square_bracket", "chart_tf(1)", "TF +", show=False),
        Binding("k", "chart_mode", "Candle/Line", show=False),
        Binding("plus,equals_sign", "chart_zoom(-1)", "Zoom in", show=False),
        Binding("minus", "chart_zoom(1)", "Zoom out", show=False),
        Binding("0", "chart_fit", "Fit all", show=False),
        Binding("left", "chart_xh(-1)", "Inspect ←", show=False),
        Binding("right", "chart_xh(1)", "Inspect →", show=False),
        Binding("end,backspace", "chart_live", "Live edge", show=False),
        Binding("enter", "chart_open", "Full chart", show=False),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.item: dict | None = None
        self.quote: dict = {}
        self.position: dict | None = None
        self.open_orders_count: int = 0
        self.stale_label: str = "WAITING"
        self.stale_color: str = ""
        self.prev_ltp: float | None = None
        self.tick_history: list[float] = []
        # Live chart state
        self.quotes: Any = None
        self.chart_iv: str = "5second"
        self.chart_mode: str = "candle"
        self.zoom_bars: int | None = None
        self.fit_all: bool = False
        self.pan_offset: int = 0
        self.crosshair_idx: int | None = None
        self.crosshair_price: float | None = None

    def compose(self) -> ComposeResult:
        yield Static("  [2] INSTRUMENT FOCUS & LIVE MICROSTRUCTURE", classes="panel-header", markup=False)
        yield Static("", id="symbol-header")
        yield Static("", id="symbol-metrics")
        yield InteractiveChartCanvas("", id="chart-panel")
        yield Static("", id="stats-strip")
        yield OrderActionWidget(id="action-order-box", classes="hidden-data")

    def on_mount(self) -> None:
        # Drives the bar-close countdown and candle rollover between ticks.
        self.set_interval(0.5, self._on_chart_timer)

    def on_resize(self, event: events.Resize) -> None:
        self.call_after_refresh(self._render_chart)

    @property
    def feed_key(self) -> str:
        if not self.item or "scripCode" not in self.item:
            return ""
        return f"{self.item.get('exchange', 'NC')}{self.item.get('scripCode')}"

    def update_context(
        self,
        item: dict | None,
        quote: dict | None = None,
        position: dict | None = None,
        open_orders: int = 0,
        stale_status: tuple[str, str] | None = None,
        tick_history: list[float] | None = None,
        width: int = 60,
        quotes: Any = None,
    ) -> None:
        """Update focused symbol and all its visual child components."""
        if item is not None:
            if self.item is not None and item is not self.item and item != self.item:
                # New symbol: reset viewport/crosshair, keep TF & mode preference
                self.pan_offset = 0
                self.crosshair_idx = None
                self.crosshair_price = None
            self.item = item
        if quotes is not None:
            self.quotes = quotes
        if quote is not None:
            new_ltp = quote.get("ltp")
            if new_ltp is not None and self.quote.get("ltp"):
                self.prev_ltp = self.quote.get("ltp")
            self.quote.update(quote)
        self.position = position
        self.open_orders_count = open_orders
        if stale_status:
            self.stale_label, self.stale_color = stale_status
        if tick_history:
            self.tick_history = tick_history

        self._refresh_subwidgets(width)

    def _refresh_subwidgets(self, width: int = 60) -> None:
        p = current_palette()
        if not self.item:
            try:
                self.query_one("#symbol-header", Static).update(
                    Text("  No symbol selected — highlight an instrument in Watchlist [1]", style=p.muted)
                )
                self.query_one("#symbol-metrics", Static).update("")
                self.query_one("#chart-panel", Static).update(
                    Text("  [ Chart Canvas — Awaiting Selection ]", style=p.subtle)
                )
                self.query_one("#stats-strip", Static).update("")
            except Exception:
                pass
            return

        sym = scrip_label(self.item)
        raw_sym = str(self.item.get("tradingSymbol") or sym).upper()
        exch = str(self.item.get("exchange", "NC"))
        sector = SECTOR_MAP.get(raw_sym, "Equity" if exch in ("NC", "BC") else "Derivatives")
        q = self.quote or {}
        ltp = q.get("ltp")
        chg = safe_float(q.get("rsChange") or q.get("change") or 0.0)
        pct = safe_float(q.get("perChange") or q.get("percentChange") or 0.0)
        bid = safe_float(q.get("bidPrice") or q.get("bid"))
        ask = safe_float(q.get("offPrice") or q.get("ask"))
        bid_q = int(safe_float(q.get("bidQty") or q.get("bQty") or 100))
        ask_q = int(safe_float(q.get("offQty") or q.get("aQty") or 100))
        hi = safe_float(q.get("high") or q.get("highPrice"))
        lo = safe_float(q.get("low") or q.get("lowPrice"))
        op = safe_float(q.get("open") or q.get("openPrice"))
        cl = safe_float(q.get("close") or q.get("closePrice"))
        vol = safe_float(q.get("qty") or q.get("volume") or q.get("vol"))
        oi = safe_float(q.get("currentOI") or q.get("oi"))

        arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "●")
        stale_clr = p.badge_color(self.stale_color) if self.stale_color else p.subtle

        # ── 1. Symbol Hero Header (2 lines) ──────────────────────────────────
        hdr = Text()
        hdr.append(f" {sym} ", style=f"bold {p.on_primary} on {p.primary}")
        hdr.append(f" {exch} ", style=f"bold {p.secondary} on {p.panel}")
        hdr.append(f" {sector} ", style=f"bold {p.muted} on {p.surface}")
        hdr.append("  ")
        if ltp is not None and ltp > 0:
            hdr.append(f"₹{ltp:,.2f}  ", style=f"bold {p.fg_strong}")
            hdr.append(f"{arrow} {format_change(chg, pct)}  ", style=sign_style(chg))
        else:
            hdr.append("₹--.-- (awaiting tick)  ", style=p.subtle)
        hdr.append(f" {self.stale_label} ", style=f"bold {stale_clr} on {p.panel}")

        # Line 2 of Header: Position & Order Context
        hdr.append("\n ")
        if self.position and int(get(self.position, "netQty", default=0)) != 0:
            net_q = int(get(self.position, "netQty", default=0))
            avg_p = safe_float(get(self.position, "avgPrice", default=0.0))
            mtm = safe_float(get(self.position, "mtm", default=0.0))
            pos_side = "LONG" if net_q > 0 else "SHORT"
            pos_clr = p.bull if net_q > 0 else p.bear
            pos_fg = p.on_bull if net_q > 0 else p.on_bear
            hdr.append(f" {pos_side} {abs(net_q)} @ ₹{avg_p:,.2f} ", style=f"bold {pos_fg} on {pos_clr}")
            hdr.append(f"  MTM: ₹{mtm:+,.2f}", style=sign_style(mtm))
        else:
            hdr.append(" POS: FLAT (0) ", style=f"bold {p.subtle} on {p.panel}")
        if self.open_orders_count > 0:
            hdr.append(f"  │  ⏳ {self.open_orders_count} Open Order(s)", style=f"bold {p.warn}")
        lot = self.item.get("lotSize") or 1
        tick_sz = self.item.get("tickSize") or 0.05
        hdr.append(f"  │  Lot: {lot}  ·  Tick: {tick_sz}", style=p.subtle)

        # ── 2. Market Microstructure & Intraday Range (2 lines) ──────────────
        metrics = Text()
        if bid > 0 and ask > 0:
            tot_q = max(1, bid_q + ask_q)
            b_bars = max(1, min(7, int(round((bid_q / tot_q) * 8))))
            a_bars = max(1, 8 - b_bars)
            metrics.append(" BID ", style=f"bold {p.on_bull} on {p.bull}")
            metrics.append(f" ₹{bid:,.2f} ", style=f"bold {p.bull}")
            metrics.append("█" * b_bars, style=p.bull)
            metrics.append("░" * a_bars, style=p.bear)
            metrics.append(f" ₹{ask:,.2f} ", style=f"bold {p.bear}")
            metrics.append(" ASK ", style=f"bold {p.on_bear} on {p.bear}")
            sprd = max(0.0, ask - bid)
            bps = (sprd / ltp * 10000) if ltp and ltp > 0 else 0.0
            metrics.append(f"  │  Spread ₹{sprd:.2f} ({bps:.1f} bps)", style=p.muted)
        else:
            metrics.append(" BOOK ", style=f"bold {p.subtle} on {p.panel}")
            metrics.append(" Bid/Ask depth awaiting market tick  ", style=p.subtle)

        metrics.append(f"  │  Vol {compact_number(vol)}", style=f"bold {p.fg}")
        if oi > 0:
            metrics.append(f"  ·  OI {compact_number(oi)}", style=p.primary)

        # Line 2 of Metrics: Intraday High-Low Range Slider & VWAP
        metrics.append("\n ")
        if hi > lo and ltp and ltp > 0:
            frac = max(0.0, min(1.0, (ltp - lo) / (hi - lo)))
            bar_w = 14
            pos_idx = int(frac * (bar_w - 1))
            metrics.append(f"L ₹{lo:,.2f} ", style=p.bear)
            metrics.append("━" * pos_idx, style=p.primary)
            metrics.append("●", style=f"bold {p.bull}")
            metrics.append("─" * (bar_w - 1 - pos_idx), style=p.subtle)
            metrics.append(f" H ₹{hi:,.2f} ", style=p.bull)
            metrics.append(f"({frac * 100:.0f}%)", style=p.muted)
        else:
            metrics.append("Intraday Range: ──────●──────", style=p.subtle)

        if hi > 0 and lo > 0 and ltp and ltp > 0:
            vwap_est = (hi + lo + ltp) / 3.0
            v_diff = (ltp - vwap_est) / vwap_est * 100.0 if vwap_est else 0.0
            metrics.append(f"  │  VWAP ₹{vwap_est:,.2f} ({v_diff:+.2f}%)", style=sign_style(v_diff))

        # ── 4. Session OHLC & Action Bar (2 lines) ───────────────────────────
        stats = Text()
        stats_parts = []
        if op > 0:
            stats_parts.append(f"Open ₹{op:,.2f}")
        if hi > 0:
            stats_parts.append(f"High ₹{hi:,.2f}")
        if lo > 0:
            stats_parts.append(f"Low ₹{lo:,.2f}")
        if cl > 0:
            stats_parts.append(f"Prev ₹{cl:,.2f}")
        if hi > 0 and lo > 0:
            stats_parts.append(f"Span ₹{hi - lo:,.2f}")
        if not stats_parts:
            stats_parts.append(f"Feed Status: {self.stale_label}")
        stats.append(" " + "  ·  ".join(stats_parts) + "\n", style=p.muted)

        # Line 2: Ergonomic Action Bar
        stats.append(" ", style=p.subtle)
        stats.append(" [b] BUY ", style=f"bold {p.on_bull} on {p.bull}")
        stats.append(" ")
        stats.append(" [s] SELL ", style=f"bold {p.on_bear} on {p.bear}")
        stats.append("  ")
        stats.append("[c]", style=f"bold {p.primary}"); stats.append(" Full Chart  ", style=p.subtle)
        stats.append("[?]", style=f"bold {p.primary}"); stats.append(" Live Quote  ", style=p.subtle)
        stats.append("[i]", style=f"bold {p.primary}"); stats.append(" Audit Info  ", style=p.subtle)
        stats.append("[a]", style=f"bold {p.primary}"); stats.append(" +Watch", style=p.subtle)

        try:
            self.query_one("#symbol-header", Static).update(hdr)
            self.query_one("#symbol-metrics", Static).update(metrics)
            self.query_one("#stats-strip", Static).update(stats)
        except Exception:
            pass
        self._render_chart()

    # ── Live chart ────────────────────────────────────────────────────────────
    def _chart_canvas(self) -> InteractiveChartCanvas | None:
        try:
            return self.query_one("#chart-panel", InteractiveChartCanvas)
        except Exception:
            return None

    def _chart_has_focus(self) -> bool:
        try:
            return self.has_focus or self.query_one("#chart-panel").has_focus
        except Exception:
            return False

    def _on_chart_timer(self) -> None:
        if not self.item or not self.is_mounted:
            return
        try:
            if not self.screen.is_current:
                return
        except Exception:
            return
        self._render_chart()

    def live_candles(self, max_bars: int = 1200) -> list:
        """Candles for the active inline TF, built from the real-time tick tape."""
        key = self.feed_key
        if self.quotes is None or not key:
            return []
        sec = INTERVAL_SECONDS.get(self.chart_iv, 5)
        try:
            return self.quotes.get_candles(key, sec, max_bars=max_bars)
        except Exception:
            return []

    def build_chart_text(self, width: int, height: int) -> Text:
        """Render the inline chart for a *width* × *height* cell area."""
        p = current_palette()
        if not self.item:
            return Text("  [ Chart Canvas — Awaiting Selection ]", style=p.subtle)
        sym = scrip_label(self.item)
        q = self.quote or {}
        ltp = safe_float(q.get("ltp")) or None
        label = INTERVAL_LABELS.get(self.chart_iv, self.chart_iv)
        sec = INTERVAL_SECONDS.get(self.chart_iv, 5)
        countdown = (sec - (time.time() % sec)) if sec > 0 else None

        pos_price, pos_qty = None, 0
        if self.position:
            pos_qty = int(safe_float(get(self.position, "netQty", default=0)))
            pos_price = safe_float(get(self.position, "avgPrice", default=0.0)) or None

        if self._chart_has_focus():
            note = "[ ] TF · k mode · +/- zoom · 0 fit · ←→ inspect · ⏎ full"
        elif self.quotes is not None and self.feed_key and not self.quotes.has_live_ticks(self.feed_key):
            note = "◌ synthetic backfill · awaiting live ticks"
        else:
            note = "click/[2] to interact"

        candles = self.live_candles()
        if candles:
            common = dict(
                zoom_bars=self.zoom_bars, pan_offset=self.pan_offset, fit_all=self.fit_all,
                crosshair_idx=self.crosshair_idx, crosshair_price=self.crosshair_price,
                live_ltp=ltp, bar_countdown_sec=countdown, compact_header=True,
                total_height=height, status_note=note,
            )
            if self.chart_mode == "candle":
                return render_candlestick_chart(
                    candles, width=width, symbol=sym, interval=label,
                    show_ema=True, show_rsi=False, show_vwap=True, show_sr=False,
                    show_volume=True, pos_price=pos_price, pos_qty=pos_qty, **common,
                )
            return render_chart(
                [c.close for c in candles], [c.volume for c in candles],
                width=width, symbol=sym, interval=label, show_stats=False,
                timestamps=[c.timestamp for c in candles], **common,
            )

        # Fallback (no tick tape available): braille line of recent LTP history
        op = safe_float(q.get("open") or q.get("openPrice"))
        cl = safe_float(q.get("close") or q.get("closePrice"))
        hi = safe_float(q.get("high") or q.get("highPrice"))
        lo = safe_float(q.get("low") or q.get("lowPrice"))
        if self.tick_history and len(self.tick_history) >= 5:
            hist = self.tick_history
        elif ltp and ltp > 0:
            base = op if op > 0 else (cl if cl > 0 else ltp)
            low_val = lo if lo > 0 else min(base, ltp)
            high_val = hi if hi > 0 else max(base, ltp)
            # Smooth trajectory connecting Open -> Low/High extremes -> Current LTP
            n_pts = 24
            pts = []
            for i in range(n_pts):
                t = i / max(1, n_pts - 1)
                if t < 0.33:
                    sub_t = t / 0.33
                    val = base + (low_val - base) * sub_t
                elif t < 0.66:
                    sub_t = (t - 0.33) / 0.33
                    val = low_val + (high_val - low_val) * sub_t
                else:
                    sub_t = (t - 0.66) / 0.34
                    val = high_val + (ltp - high_val) * sub_t
                pts.append(round(val, 2))
            pts[-1] = ltp
            hist = pts
        else:
            hist = [100.0, 100.5, 101.2, 100.8, 101.5, 102.0, 101.7, 102.5, 103.0, 102.8]
        return render_chart(
            hist, width=width, total_height=height, symbol=sym, interval="LIVE TICK",
            show_stats=False, show_vol_strip=False, compact_header=True,
        )

    def _render_chart(self) -> None:
        canvas = self._chart_canvas()
        if canvas is None:
            return
        w, h = canvas.chart_size
        if w < 24 or h < 6:
            w, h = max(w, 60), max(h, 10)
        try:
            canvas.set_chart(self.build_chart_text(w, h))
        except Exception as e:  # never let a render glitch kill the workspace
            canvas.set_chart(Text(f"  — chart error: {e} —", style=current_palette().bear))

    def _chart_meta(self) -> dict:
        canvas = self._chart_canvas()
        return (canvas.meta or {}) if canvas else {}

    # ── Chart actions (active when panel / chart has focus) ──────────────────
    def action_chart_tf(self, delta: int) -> None:
        try:
            i = INLINE_TFS.index(self.chart_iv)
        except ValueError:
            i = 2
        self.chart_iv = INLINE_TFS[(i + delta) % len(INLINE_TFS)]
        self.pan_offset, self.crosshair_idx, self.crosshair_price = 0, None, None
        self._render_chart()

    def action_chart_mode(self) -> None:
        self.chart_mode = "line" if self.chart_mode == "candle" else "candle"
        self.crosshair_idx = None
        self._render_chart()

    def action_chart_zoom(self, direction: int) -> None:
        m = self._chart_meta()
        n_total = int(m.get("n_total") or len(self.live_candles()) or 1)
        cur = self.zoom_bars or int(m.get("end", n_total) - m.get("start", 0)) or 40
        if self.fit_all:
            self.fit_all, cur = False, n_total
        self.zoom_bars = step_zoom(cur, n_total, direction)
        self.crosshair_idx = None
        self._render_chart()

    def action_chart_fit(self) -> None:
        self.fit_all = not self.fit_all
        self.zoom_bars = None
        self.pan_offset, self.crosshair_idx = 0, None
        self._render_chart()

    def action_chart_xh(self, delta: int) -> None:
        m = self._chart_meta()
        n = int(m.get("n") or 0)
        if n <= 0:
            return
        if self.crosshair_idx is None:
            self.crosshair_idx = n - 1
        else:
            nxt = self.crosshair_idx + delta
            if nxt < 0 and not self.fit_all and m.get("start", 0) > 0:
                self.pan_offset += 1
                nxt = 0
            elif nxt >= n and self.pan_offset > 0:
                self.pan_offset -= 1
                nxt = n - 1
            self.crosshair_idx = max(0, min(n - 1, nxt))
        self.crosshair_price = None
        self._render_chart()

    def action_chart_live(self) -> None:
        self.pan_offset, self.crosshair_idx, self.crosshair_price = 0, None, None
        self._render_chart()

    def action_chart_open(self) -> None:
        opener = getattr(self.screen, "action_chart", None)
        if callable(opener):
            opener()

    def on_interactive_chart_canvas_clicked(self, msg: InteractiveChartCanvas.Clicked) -> None:
        msg.stop()
        if msg.idx is not None and msg.idx == self.crosshair_idx and msg.price is None:
            self.crosshair_idx = None
        else:
            self.crosshair_idx = msg.idx
            self.crosshair_price = msg.price
        self._render_chart()

    def on_interactive_chart_canvas_wheel(self, msg: InteractiveChartCanvas.Wheel) -> None:
        msg.stop()
        if msg.shift:
            m = self._chart_meta()
            max_pan = max(0, int(m.get("n_total", 0)) - int(m.get("end", 0) - m.get("start", 0)))
            self.pan_offset = max(0, min(max_pan, self.pan_offset - msg.direction * 5))
            self._render_chart()
        else:
            self.action_chart_zoom(msg.direction)

    def render_content(self, width: int = 60) -> Text:
        """Render text representation for test assertions and modal fallbacks."""
        p = current_palette()
        t = Text()
        if not self.item:
            t.append("  SELECTED INSTRUMENT\n  No symbol selected.\n", style=p.muted)
            return t
        sym = scrip_label(self.item)
        exch = str(self.item.get("exchange", "NC"))
        q = self.quote or {}
        ltp = q.get("ltp")
        chg = safe_float(q.get("rsChange") or 0.0)
        pct = safe_float(q.get("perChange") or 0.0)

        t.append(f"  {sym}  [{exch}]  {self.stale_label}\n", style=f"bold {p.primary}")
        if ltp is not None:
            t.append(f"  ₹{ltp:,.2f}  {format_change(chg, pct)}\n", style=sign_style(chg))
        else:
            t.append("  --.-- (awaiting tick data)\n", style=p.subtle)
        return t
