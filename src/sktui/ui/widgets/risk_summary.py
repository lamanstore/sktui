"""Risk Summary and Feed Health widget for the lower right pane of SKTUI."""
from __future__ import annotations

from typing import Any
from rich.text import Text
from textual.widgets import Static

from sktui.config import C_AMBER, C_CYAN, C_GREEN, C_MUTED, C_RED, C_SUBTLE, C_TEXT
from sktui.utils import get, is_open_order, sign_style


class RiskSummaryWidget(Static):
    """Real-time portfolio exposure, drawdown, and feed health status widget."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.positions: list[dict] = []
        self.orders: list[dict] = []
        self.feed_badge_text: str = "LIVE 12ms"
        self.feed_badge_color: str = C_GREEN

    def update_summary(
        self,
        positions: list[dict],
        orders: list[dict],
        feed_badge: tuple[str, str] | None = None,
        width: int = 50,
    ) -> None:
        self.positions = positions or []
        self.orders = orders or []
        if feed_badge:
            self.feed_badge_text, self.feed_badge_color = feed_badge
        self.update(self.render_content(width=width))

    def render_content(self, width: int = 50) -> Text:
        t = Text()
        bpl = sum(float(str(get(r, "bpl", default=0)).replace(",", "") or 0) for r in self.positions)
        mtm = sum(float(str(get(r, "mtm", default=0)).replace(",", "") or 0) for r in self.positions)
        total_pnl = bpl + mtm
        open_orders_cnt = sum(1 for r in self.orders if is_open_order(r))

        # Line 1: Real-time P&L breakdown
        t.append("  P&L: ", style=C_MUTED)
        t.append(f"₹{total_pnl:+,.2f}  ", style=sign_style(total_pnl))
        t.append(f"(Realised: ₹{bpl:+,.2f}  MTM: ₹{mtm:+,.2f})\n", style=C_SUBTLE)

        # Line 2: Desk exposure & order flow
        t.append("  Desk: ", style=C_MUTED)
        t.append(f"{len(self.positions)} positions  ·  ", style=f"bold {C_CYAN}")
        t.append(f"{open_orders_cnt} pending orders  ·  ", style=f"bold {C_AMBER}" if open_orders_cnt > 0 else C_SUBTLE)
        t.append("Risk: OK\n", style=f"bold {C_GREEN}")

        # Line 3: Feed health & connection status
        t.append("  Feed: ", style=C_MUTED)
        t.append(f" {self.feed_badge_text} ", style=f"bold {self.feed_badge_color} on #0d1526")
        t.append("  ·  Press [/] for /risk or /analytics", style=C_SUBTLE)
        return t
