"""Market Scanner and Movers widget for the left pane of SKTUI."""
from __future__ import annotations

from typing import Any
from rich.text import Text
from textual.widgets import Static

from sktui.themes import current_palette
from sktui.utils import fmt


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
        p = current_palette()
        t = Text()

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
            t.append("  Scanner: ", style=p.muted)
            t.append("Awaiting market ticks...\n", style=p.subtle)
            t.append("  Active Alerts: ", style=p.muted)
            t.append(f"{self.active_alerts_count} active\n", style=f"bold {p.primary}")
            t.append("  Press [/] for /scanner or /alerts", style=p.subtle)
            return t

        by_pct = sorted(items_with_data, key=lambda x: x[2], reverse=True)
        top_gainer = by_pct[0] if by_pct and by_pct[0][2] > 0 else None
        top_loser = by_pct[-1] if by_pct and by_pct[-1][2] < 0 else None
        by_vol = sorted(items_with_data, key=lambda x: x[3], reverse=True)
        vol_leader = by_vol[0] if by_vol and by_vol[0][3] > 0 else None

        if top_gainer:
            t.append("  Top Mover ▲: ", style=p.muted)
            t.append(f"{top_gainer[0]:<9} ", style=f"bold {p.bull}")
            t.append(f"₹{top_gainer[1]:<7.2f} ", style=p.fg)
            t.append(f"{top_gainer[2]:+6.2f}%\n", style=f"bold {p.bull}")
        else:
            t.append("  Top Mover ▲: --\n", style=p.subtle)

        if top_loser:
            t.append("  Top Loser ▼: ", style=p.muted)
            t.append(f"{top_loser[0]:<9} ", style=f"bold {p.bear}")
            t.append(f"₹{top_loser[1]:<7.2f} ", style=p.fg)
            t.append(f"{top_loser[2]:+6.2f}%\n", style=f"bold {p.bear}")
        else:
            t.append("  Top Loser ▼: --\n", style=p.subtle)

        if vol_leader:
            t.append("  Vol Leader : ", style=p.muted)
            t.append(f"{vol_leader[0]:<9} ", style=f"bold {p.primary}")
            t.append(f"Vol: {fmt(vol_leader[3])}\n", style=p.subtle)

        t.append("  Alerts: ", style=p.muted)
        t.append(f"{self.active_alerts_count} active  ·  ", style=f"bold {p.warn}")
        t.append("[/scanner, /alerts]", style=p.subtle)
        return t
