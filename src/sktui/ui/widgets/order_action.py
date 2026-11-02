"""Order Action and Pre-Trade Risk Preview widget for the center pane of SKTUI."""
from __future__ import annotations

from typing import Any
from rich.text import Text
from textual.widgets import Static

from sktui.themes import current_palette
from sktui.utils import scrip_label


class OrderActionWidget(Static):
    """Direct execution trigger and pre-trade risk impact widget."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.item: dict | None = None
        self.quote: dict = {}
        self.position: dict | None = None
        self.risk_status: str = "NORMAL"
        self.daily_drawdown_pct: float = 0.0

    def update_action_context(
        self,
        item: dict | None,
        quote: dict | None = None,
        position: dict | None = None,
        risk_status: str = "NORMAL",
        drawdown_pct: float = 0.0,
        width: int = 60,
    ) -> None:
        self.item = item
        if quote is not None:
            self.quote = quote
        self.position = position
        self.risk_status = risk_status
        self.daily_drawdown_pct = drawdown_pct
        self.update(self.render_content(width=width))

    def render_content(self, width: int = 60) -> Text:
        p = current_palette()
        t = Text()
        if not self.item:
            t.append("  ACTION: ", style=p.muted)
            t.append("Select a symbol to stage orders and inspect risk.\n", style=p.subtle)
            t.append("  Press [b] to Buy  ·  [s] to Sell  ·  [c] for Chart  ·  [K] to Flatten", style=p.muted)
            return t

        sym = scrip_label(self.item)
        exch = str(self.item.get("exchange", "NC"))
        ltp = self.quote.get("ltp") or 0.0

        pos_str = "FLAT (0)"
        pos_style = p.subtle
        if self.position:
            net_q = int(self.position.get("netQty", 0))
            mtm = float(self.position.get("mtm", 0.0))
            if net_q != 0:
                side = "LONG" if net_q > 0 else "SHORT"
                pos_str = f"{side} {abs(net_q)} (MTM: ₹{mtm:+,.2f})"
                pos_style = f"bold {p.bull if mtm >= 0 else p.bear}"

        risk_color = p.bull if self.risk_status == "NORMAL" else (p.warn if self.risk_status == "WARNING" else p.bear)

        t.append("  EXECUTE: ", style=p.muted)
        t.append(f"{sym} [{exch}]  ", style=f"bold {p.primary}")
        t.append(f"@ ₹{ltp:,.2f}  ·  ", style=p.fg if ltp > 0 else p.subtle)
        t.append(f"Risk: {self.risk_status} ", style=f"bold {risk_color}")
        t.append(f"({self.daily_drawdown_pct:.1f}% loss cap)\n", style=p.subtle)

        t.append("  Position: ", style=p.muted)
        t.append(f"{pos_str}  ·  ", style=pos_style)
        t.append("Lot: 1  ·  Tick: 0.05\n", style=p.subtle)

        t.append("  Action Keys: ", style=p.muted)
        t.append(" [B] BUY TICKET ", style=f"bold {p.on_bull} on {p.bull}")
        t.append(" ")
        t.append(" [S] SELL TICKET ", style=f"bold {p.on_bear} on {p.bear}")
        t.append("   ")
        t.append("[C]", style=f"bold {p.primary}"); t.append("hart  ", style=p.subtle)
        t.append("[I]", style=f"bold {p.primary}"); t.append("nfo  ", style=p.subtle)
        t.append("[K]", style=f"bold {p.bear}"); t.append("ill/Flatten", style=p.subtle)
        return t
