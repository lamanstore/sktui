"""Risk Dashboard Screen for SKTUI.

Displays active risk parameters, policy limits, real-time exposure,
drawdown status, and provides administrative controls (e.g. override lockout).
"""
from __future__ import annotations

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Rule, Static

from sktui.services.risk_engine import RiskEngine
from sktui.themes import current_palette


class RiskDashboardScreen(ModalScreen):
    """Interactive risk dashboard with live policies, exposure, and governance controls."""
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Close"),
        Binding("r", "reset_lockout", "Reset Lockout", show=False),
    ]

    def compose(self) -> ComposeResult:
        p = current_palette()
        c = self.app.client
        risk_eng = getattr(getattr(self.app.screen, "order_service", None), "risk_engine", None) or RiskEngine()
        lim = risk_eng.limits
        with Vertical(classes="modal wide"):
            yield Label("🛡  Professional Risk Controls & Governance", classes="title")
            t = Text()

            t.append("\n  ── Risk Status ────────────────────────────────────────\n\n", style=p.subtle)
            t.append("  Risk State:            ", style=p.muted)
            t.append("LOCKOUT ACTIVE\n" if risk_eng._lockout_active else "NORMAL (ACTIVE)\n",
                     style=f"bold {p.bear}" if risk_eng._lockout_active else f"bold {p.bull}")
            t.append("  Order Enforcement:     ", style=p.muted)
            t.append(f"{'ENABLED' if lim.enforce_limits else 'MONITORING ONLY'}\n",
                     style=f"bold {p.bull}" if lim.enforce_limits else f"bold {p.warn}")
            t.append("  Environment:           ", style=p.muted)
            t.append(f"{'PAPER SIMULATION' if getattr(c, 'paper', False) else 'LIVE EXCHANGE'}\n",
                     style=f"bold {p.warn}" if getattr(c, "paper", False) else f"bold {p.bear}")

            t.append("\n  ── Policy Limits & Thresholds ────────────────────────\n\n", style=p.subtle)
            t.append("  Max Order Quantity:    ", style=p.muted)
            t.append(f"{lim.max_order_qty:,} units\n", style=f"bold {p.primary}")
            t.append("  Max Order Value:       ", style=p.muted)
            t.append(f"₹{lim.max_order_value:,.2f}\n", style=f"bold {p.primary}")
            t.append("  Max Position Value:    ", style=p.muted)
            t.append(f"₹{lim.max_position_value:,.2f} per symbol\n", style=f"bold {p.primary}")
            t.append("  Max Daily Drawdown:    ", style=p.muted)
            t.append(f"-₹{lim.max_daily_loss:,.2f}\n", style=f"bold {p.bear}")
            t.append("  Rate Limiter:          ", style=p.muted)
            t.append(f"{lim.max_orders_per_minute} orders / min (Burst Protection)\n", style=f"bold {p.warn}")

            t.append("\n  ── Safety Invariants ──────────────────────────────────\n\n", style=p.subtle)
            invariants = [
                "Pre-trade size & exposure checks run on every order",
                "Dynamic 0-100 risk score computed for order ticket confirmation",
                "Stop-loss guardrail verified for derivatives",
                "Immutable audit trail logged to ~/.local/share/sktui/audit/audit.jsonl",
                "Hard lockout triggered automatically upon max daily loss breach",
            ]
            for inv in invariants:
                t.append("  ✓  ", style=f"bold {p.bull}")
                t.append(f"{inv}\n", style=p.muted)

            yield Static(t, id="risk-info-text")
            yield Rule()
            with Horizontal(classes="row buttons"):
                if risk_eng._lockout_active:
                    yield Button("🔓 Reset Lockout (Override)", id="btn-reset-lockout", variant="warning")
                yield Button("✗  Close", id="close-btn", variant="primary")

    @on(Button.Pressed, "#btn-reset-lockout")
    def action_reset_lockout(self) -> None:
        risk_eng = getattr(getattr(self.app.screen, "order_service", None), "risk_engine", None)
        if risk_eng:
            risk_eng.reset_lockout()
            self.app.notify("✓ Risk lockout cleared by operator override", severity="information")
            self.dismiss(None)

    @on(Button.Pressed, "#close-btn")
    def _close(self) -> None:
        self.dismiss(None)


# Alias for backwards compatibility
RiskScreen = RiskDashboardScreen
