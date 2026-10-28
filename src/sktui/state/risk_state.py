"""Risk state models and risk governance data structures for SKTUI.

Provides typed risk policies, pre-trade check outcomes, and real-time
risk scoring heuristics.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class RiskLimits:
    """Configurable risk policy parameters."""
    max_order_qty: int = 10_000
    max_order_value: float = 1_000_000.0          # Max value per single order in INR
    max_position_qty: int = 50_000
    max_position_value: float = 2_500_000.0       # Max total value per symbol in INR
    max_portfolio_exposure: float = 10_000_000.0  # Max total gross exposure
    max_daily_loss: float = 50_000.0              # Max daily loss before hard lockout
    max_orders_per_minute: int = 30               # Rate limit / burst protection
    enforce_limits: bool = True                   # Master kill switch for enforcement
    require_sl_for_derivatives: bool = True        # Guardrail for F&O
    require_sl_for_margin: bool = False           # Warning for leveraged equity


@dataclass
class RiskCheckResult:
    """Outcome of pre-trade risk evaluation."""
    allowed: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_margin: float = 0.0
    daily_pnl: float = 0.0
    risk_score: int = 10                          # 0-100 risk score
    risk_rating: str = "LOW"                      # LOW, MODERATE, ELEVATED, HIGH RISK

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    def summary(self) -> str:
        score_tag = f"[{self.risk_rating} · Score: {self.risk_score}/100]"
        if not self.allowed:
            return f"⛔ RISK REJECTION {score_tag}:\n• " + "\n• ".join(self.violations)
        if self.warnings:
            return f"⚠ RISK WARNINGS {score_tag}:\n• " + "\n• ".join(self.warnings)
        return f"✓ Risk check passed {score_tag}"


@dataclass
class RiskState:
    """Real-time risk state tracking for current session."""
    limits: RiskLimits = field(default_factory=RiskLimits)
    realized_daily_pnl: float = 0.0
    unrealized_daily_pnl: float = 0.0
    gross_exposure: float = 0.0
    lockout_active: bool = False
    lockout_reason: str = ""
    order_timestamps: deque[float] = field(default_factory=deque)

    def calculate_risk_score(
        self,
        order_value: float,
        projected_sym_value: float,
        is_derivative: bool,
        has_sl: bool,
    ) -> tuple[int, str]:
        """Compute an objective 0-100 risk score for an intended order."""
        score = 10.0

        # Order size component (up to 30 pts)
        if self.limits.max_order_value > 0:
            order_ratio = min(order_value / self.limits.max_order_value, 1.0)
            score += order_ratio * 30.0

        # Position concentration component (up to 30 pts)
        if self.limits.max_position_value > 0:
            pos_ratio = min(projected_sym_value / self.limits.max_position_value, 1.0)
            score += pos_ratio * 30.0

        # Derivative / SL risk component (up to 20 pts)
        if is_derivative:
            score += 10.0
            if not has_sl:
                score += 15.0

        # Drawdown component (up to 15 pts)
        if self.limits.max_daily_loss > 0 and self.realized_daily_pnl < 0:
            dd_ratio = min(abs(self.realized_daily_pnl) / self.limits.max_daily_loss, 1.0)
            score += dd_ratio * 15.0

        final_score = int(min(max(score, 5.0), 100.0))
        if final_score < 30:
            rating = "LOW"
        elif final_score < 60:
            rating = "MODERATE"
        elif final_score < 80:
            rating = "ELEVATED"
        else:
            rating = "HIGH RISK"

        return final_score, rating
