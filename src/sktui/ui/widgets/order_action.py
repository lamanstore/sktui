"""Order Action and Pre-Trade Risk Preview widget for the center pane of SKTUI."""
from __future__ import annotations

from typing import Any
from rich.text import Text
from textual.widgets import Static

from sktui.config import (
    C_AMBER, C_CYAN, C_GREEN, C_MUTED, C_PANEL, C_RED, C_SUBTLE, C_TEXT,
)
from sktui.utils import fmt, get, scrip_label, sign_style


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
        t = Text()
        if not self.item:
            t.append("  ACTION: ", style=C_MUTED)
            t.append("Select a symbol to stage orders and inspect risk.\n", style=C_SUBTLE)
            t.append("  Press [b] to Buy  ·  [s] to Sell  ·  [c] for Chart  ·  [K] to Flatten", style=C_MUTED)
            return t

        sym = scrip_label(self.item)
        exch = str(self.item.get("exchange", "NC"))
        ltp = self.quote.get("ltp") or 0.0

        # Position context
        pos_str = "FLAT (0)"
        pos_style = C_SUBTLE
        if self.position:
            net_q = int(self.position.get("netQty", 0))
            mtm = float(self.position.get("mtm", 0.0))
            if net_q != 0:
                side = "LONG" if net_q > 0 else "SHORT"
                pos_str = f"{side} {abs(net_q)} (MTM: ₹{mtm:+,.2f})"
                pos_style = f"bold {C_GREEN if mtm >= 0 else C_RED}"

        # Risk compliance badge
        risk_color = C_GREEN if self.risk_status == "NORMAL" else (C_AMBER if self.risk_status == "WARNING" else C_RED)

        t.append("  EXECUTE: ", style=C_MUTED)
        t.append(f"{sym} [{exch}]  ", style=f"bold {C_CYAN}")
        t.append(f"@ ₹{ltp:,.2f}  ·  ", style=C_TEXT if ltp > 0 else C_SUBTLE)
        t.append(f"Risk: {self.risk_status} ", style=f"bold {risk_color}")
        t.append(f"({self.daily_drawdown_pct:.1f}% loss cap)\n", style=C_SUBTLE)

        t.append("  Position: ", style=C_MUTED)
        t.append(f"{pos_str}  ·  ", style=pos_style)
        t.append("Lot: 1  ·  Tick: 0.05\n", style=C_SUBTLE)

        t.append("  Action Keys: ", style=C_MUTED)
        t.append(" [B] BUY TICKET ", style=f"bold black on {C_GREEN}")
        t.append(" ")
        t.append(" [S] SELL TICKET ", style=f"bold white on {C_RED}")
        t.append("   ")
        t.append("[C]", style=f"bold {C_CYAN}"); t.append("hart  ", style=C_SUBTLE)
        t.append("[I]", style=f"bold {C_CYAN}"); t.append("nfo  ", style=C_SUBTLE)
        t.append("[K]", style=f"bold {C_RED}"); t.append("ill/Flatten", style=C_SUBTLE)
        return t
