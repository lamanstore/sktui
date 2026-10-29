"""Market Scanner and Movers widget for the left pane of SKTUI."""
from __future__ import annotations

from typing import Any
from rich.text import Text
from textual.widgets import Static

from sktui.config import C_AMBER, C_CYAN, C_GREEN, C_MUTED, C_RED, C_SUBTLE, C_TEXT
from sktui.utils import fmt, sign_style


class MarketScannerWidget(Static):
    """Compact live scanner displaying top movers, volume leaders, and alert pulse."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.raw_ticks: dict = {}
        self.watch: list[dict] = []
        self.active_alerts_count: int = 0

    def update_scanner(
        self,
        raw_ticks: dict,
        watch: list[dict],
        alerts_count: int = 0,
        width: int = 40,
    ) -> None:
        self.raw_ticks = raw_ticks or {}
        self.watch = watch or []
        self.active_alerts_count = alerts_count
        self.update(self.render_content(width=width))

    def render_content(self, width: int = 40) -> Text:
        t = Text()

        # Gather tick statistics
        items_with_data = []
        for item in self.watch:
            sym = item.get("tradingSymbol") or item.get("tsym") or ""
            key = f"{item.get('exchange', 'NC')}{item.get('scripCode', '')}"
            q = self.raw_ticks.get(key) or self.raw_ticks.get(sym, {})
            pct = q.get("perChange") or q.get("percentChange") or 0.0
            vol = q.get("qty") or q.get("volume") or 0
            ltp = q.get("ltp") or 0.0
            if ltp > 0:
                items_with_data.append((sym, ltp, float(pct), vol))

        if not items_with_data:
            t.append("  Scanner: ", style=C_MUTED)
            t.append("Awaiting market ticks...\n", style=C_SUBTLE)
            t.append("  Active Alerts: ", style=C_MUTED)
            t.append(f"{self.active_alerts_count} active\n", style=f"bold {C_CYAN}")
            t.append("  Press [/] for /scanner or /alerts", style=C_SUBTLE)
            return t

        # Top Gainer & Loser
        by_pct = sorted(items_with_data, key=lambda x: x[2], reverse=True)
        top_gainer = by_pct[0] if by_pct and by_pct[0][2] > 0 else None
        top_loser = by_pct[-1] if by_pct and by_pct[-1][2] < 0 else None
        by_vol = sorted(items_with_data, key=lambda x: x[3], reverse=True)
        vol_leader = by_vol[0] if by_vol and by_vol[0][3] > 0 else None

        if top_gainer:
            t.append("  Top Mover ▲: ", style=C_MUTED)
            t.append(f"{top_gainer[0]:<9} ", style=f"bold {C_GREEN}")
            t.append(f"₹{top_gainer[1]:<7.2f} ", style=C_TEXT)
            t.append(f"{top_gainer[2]:+6.2f}%\n", style=f"bold {C_GREEN}")
        else:
            t.append("  Top Mover ▲: --\n", style=C_SUBTLE)

        if top_loser:
            t.append("  Top Loser ▼: ", style=C_MUTED)
            t.append(f"{top_loser[0]:<9} ", style=f"bold {C_RED}")
            t.append(f"₹{top_loser[1]:<7.2f} ", style=C_TEXT)
            t.append(f"{top_loser[2]:+6.2f}%\n", style=f"bold {C_RED}")
        else:
            t.append("  Top Loser ▼: --\n", style=C_SUBTLE)

        if vol_leader:
            t.append("  Vol Leader : ", style=C_MUTED)
            t.append(f"{vol_leader[0]:<9} ", style=f"bold {C_CYAN}")
            t.append(f"Vol: {fmt(vol_leader[3])}\n", style=C_SUBTLE)

        t.append("  Alerts: ", style=C_MUTED)
        t.append(f"{self.active_alerts_count} active  ·  ", style=f"bold {C_AMBER}")
        t.append("[/scanner, /alerts]", style=C_SUBTLE)
        return t
