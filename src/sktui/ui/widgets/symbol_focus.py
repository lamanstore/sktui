"""Symbol Focus Panel widget for SKTUI.

Prioritizes the currently selected symbol as the center of the trading workspace,
displaying comprehensive live quote, depth, spread, day range, volume, braille chart,
and position context without forcing horizontal table scroll.
"""
from __future__ import annotations

from typing import Any
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static

from sktui.chart import render_chart
from sktui.config import (
    C_AMBER, C_CYAN, C_DIM, C_GREEN, C_MUTED, C_PANEL, C_RED, C_SUBTLE, C_TEXT,
)
from sktui.ui.widgets.order_action import OrderActionWidget
from sktui.utils import (
    compact_number, format_change, safe_float, scrip_label, sign_style,
)


class SymbolFocusPanel(Static):
    """Selected symbol summary + chart area + stats."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.item: dict | None = None
        self.quote: dict = {}
        self.position: dict | None = None
        self.open_orders_count: int = 0
        self.stale_label: str = "WAITING"
        self.stale_color: str = C_SUBTLE
        self.prev_ltp: float | None = None
        self.tick_history: list[float] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="symbol-header")
        yield Static("", id="symbol-metrics")
        yield Static("", id="chart-panel")
        yield Static("", id="stats-strip")
        yield OrderActionWidget(id="action-order-box", classes="hidden-data")

    def update_context(
        self,
        item: dict | None,
        quote: dict | None = None,
        position: dict | None = None,
        open_orders: int = 0,
        stale_status: tuple[str, str] | None = None,
        tick_history: list[float] | None = None,
        width: int = 60,
    ) -> None:
        """Update focused symbol and all its visual child components."""
        if item is not None:
            self.item = item
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
        if not self.item:
            try:
                self.query_one("#symbol-header", Static).update(
                    Text("  No symbol selected — select from Watchlist [1]", style=C_MUTED)
                )
                self.query_one("#symbol-metrics", Static).update("")
                self.query_one("#chart-panel", Static).update(Text("  [ Chart Area ]", style=C_SUBTLE))
                self.query_one("#stats-strip", Static).update("")
            except Exception:
                pass
            return

        sym = scrip_label(self.item)
        exch = str(self.item.get("exchange", "NC"))
        q = self.quote or {}
        ltp = q.get("ltp")
        chg = safe_float(q.get("rsChange") or q.get("change") or 0.0)
        pct = safe_float(q.get("perChange") or q.get("percentChange") or 0.0)
        bid = safe_float(q.get("bidPrice") or q.get("bid"))
        ask = safe_float(q.get("offPrice") or q.get("ask"))
        bid_q = int(safe_float(q.get("bidQty") or q.get("bQty")))
        ask_q = int(safe_float(q.get("offQty") or q.get("aQty")))
        hi = safe_float(q.get("high") or q.get("highPrice"))
        lo = safe_float(q.get("low") or q.get("lowPrice"))
        op = safe_float(q.get("open") or q.get("openPrice"))
        cl = safe_float(q.get("close") or q.get("closePrice"))
        vol = safe_float(q.get("qty") or q.get("volume") or q.get("vol"))
        oi = safe_float(q.get("currentOI") or q.get("oi"))

        arrow = "▲ " if chg > 0 else ("▼ " if chg < 0 else "● ")

        # 1. Header
        hdr = Text()
        hdr.append(f"  {sym}  ", style=f"bold {C_CYAN}")
        hdr.append(f"[{exch}]  ", style=C_SUBTLE)
        if ltp is not None and ltp > 0:
            hdr.append(f"₹{ltp:,.2f}  ", style="bold white")
            hdr.append(f"{arrow}{format_change(chg, pct)}  ", style=sign_style(chg))
        else:
            hdr.append("--.-- (awaiting feed)  ", style=C_SUBTLE)
        hdr.append(f" {self.stale_label} ", style=f"bold {self.stale_color} on #0d1526")

        # 2. Metrics & Depth
        metrics = Text()
        metrics.append("  Depth: ", style=C_MUTED)
        if bid > 0 and ask > 0:
            metrics.append(f"BID ₹{bid:,.2f} × {bid_q:,}  ", style=f"bold {C_GREEN}")
            metrics.append("|  ", style=C_SUBTLE)
            metrics.append(f"ASK ₹{ask:,.2f} × {ask_q:,}  ", style=f"bold {C_RED}")
            sprd = ask - bid
            bps = (sprd / ltp * 10000) if ltp and ltp > 0 else 0.0
            metrics.append(f"Spread: ₹{sprd:.2f} ({bps:.1f} bps)  ", style=C_SUBTLE)
        else:
            metrics.append("Depth awaiting tick  ", style=C_SUBTLE)
        metrics.append(f"Vol: {compact_number(vol)}  ", style=C_MUTED)
        if oi > 0:
            metrics.append(f"OI: {compact_number(oi)}", style=C_MUTED)

        # 3. Chart Area
        chart_w = max(24, min(width - 4, 72))
        hist = self.tick_history if self.tick_history else ([ltp] * 10 if ltp else [100.0] * 10)
        chart_text = render_chart(hist, width=chart_w, height=6, show_stats=False, show_vol_strip=False)

        # 4. Stats Strip
        stats = Text()
        stats_parts = []
        if op > 0: stats_parts.append(f"Open: ₹{op:,.2f}")
        if hi > 0: stats_parts.append(f"High: ₹{hi:,.2f}")
        if lo > 0: stats_parts.append(f"Low: ₹{lo:,.2f}")
        if cl > 0: stats_parts.append(f"Close: ₹{cl:,.2f}")
        if hi > 0 and lo > 0: stats_parts.append(f"Range: ₹{hi - lo:,.2f}")
        stats_parts.append(f"Status: {self.stale_label}")
        stats.append("  " + "  ·  ".join(stats_parts), style=C_SUBTLE)

        try:
            self.query_one("#symbol-header", Static).update(hdr)
            self.query_one("#symbol-metrics", Static).update(metrics)
            self.query_one("#chart-panel", Static).update(chart_text)
            self.query_one("#stats-strip", Static).update(stats)
        except Exception:
            pass

    def render_content(self, width: int = 60) -> Text:
        """Render text representation for test assertions and modal fallbacks."""
        t = Text()
        if not self.item:
            t.append("  SELECTED INSTRUMENT\n  No symbol selected.\n", style=C_MUTED)
            return t
        sym = scrip_label(self.item)
        exch = str(self.item.get("exchange", "NC"))
        q = self.quote or {}
        ltp = q.get("ltp")
        chg = safe_float(q.get("rsChange") or 0.0)
        pct = safe_float(q.get("perChange") or 0.0)

        t.append(f"  {sym}  [{exch}]  {self.stale_label}\n", style=f"bold {C_CYAN}")
        if ltp is not None:
            t.append(f"  ₹{ltp:,.2f}  {format_change(chg, pct)}\n", style=sign_style(chg))
        else:
            t.append("  --.-- (awaiting tick data)\n", style=C_SUBTLE)
        return t
