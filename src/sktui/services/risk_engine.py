"""Professional Risk Engine for SKTUI.

Provides pre-trade risk controls, position size limits, exposure monitoring,
stop-loss guardrails, daily drawdown checks, and order rate-limiting.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence


from sktui.state.risk_state import RiskCheckResult, RiskLimits, RiskState



class RiskEngine:
    """Central risk governor for order entry and portfolio safety."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()
        # Sliding window timestamps of recent order submissions
        self._order_timestamps: deque[float] = deque()
        self._daily_realized_pnl: float = 0.0
        self._lockout_active: bool = False
        self._lockout_reason: str = ""

    def update_daily_pnl(self, realized_pnl: float) -> None:
        """Update realized PnL and trigger drawdown lockout if breached."""
        self._daily_realized_pnl = realized_pnl
        if self.limits.enforce_limits and realized_pnl <= -abs(self.limits.max_daily_loss):
            self._lockout_active = True
            self._lockout_reason = (
                f"Daily drawdown limit breached: ₹{realized_pnl:,.2f} "
                f"(limit: -₹{self.limits.max_daily_loss:,.2f})"
            )

    def reset_lockout(self) -> None:
        """Manually unlock the risk engine (trader override)."""
        self._lockout_active = False
        self._lockout_reason = ""

    def record_order_submission(self) -> None:
        """Record an order submission timestamp for rate limiting."""
        now = time.monotonic()
        self._order_timestamps.append(now)

    def _check_rate_limit(self) -> bool:
        """Check if order rate exceeds max_orders_per_minute."""
        now = time.monotonic()
        # Drop timestamps older than 60 seconds
        while self._order_timestamps and self._order_timestamps[0] < now - 60.0:
            self._order_timestamps.popleft()
        return len(self._order_timestamps) < self.limits.max_orders_per_minute

    def validate_order(
        self,
        order_params: dict[str, Any],
        positions: Sequence[Any] | None = None,
        quote_price: float = 0.0,
        available_funds: float = 0.0,
    ) -> RiskCheckResult:
        """Validate order parameters against risk limits and return result."""
        violations: list[str] = []
        warnings: list[str] = []

        # 1. Hard Lockout Check
        if self._lockout_active:
            violations.append(f"RISK LOCKOUT ACTIVE: {self._lockout_reason}")
            return RiskCheckResult(allowed=False, violations=violations, daily_pnl=self._daily_realized_pnl)

        # 2. Rate Limit Check
        if not self._check_rate_limit():
            violations.append(
                f"Rate limit exceeded: >{self.limits.max_orders_per_minute} orders/min. "
                "Cooling down to prevent runaway execution."
            )

        # Parse order details
        symbol = str(order_params.get("tradingSymbol", "UNKNOWN"))
        exchange = str(order_params.get("exchange", "NC")).upper()
        side = str(order_params.get("transactionType", "B")).upper()
        try:
            qty = int(order_params.get("quantity") or 0)
        except (ValueError, TypeError):
            qty = 0
        try:
            price = float(order_params.get("price") or 0.0)
        except (ValueError, TypeError):
            price = 0.0
        try:
            trigger_price = float(order_params.get("triggerPrice") or 0.0)
        except (ValueError, TypeError):
            trigger_price = 0.0

        ref_price = price if price > 0 else (quote_price if quote_price > 0 else 1.0)
        order_value = qty * ref_price
        is_derivative = exchange not in ("NC", "BC")
        product = str(order_params.get("productType", "INVESTMENT")).upper()

        # 3. Quantity & Order Value Caps
        if qty <= 0:
            violations.append("Order quantity must be positive")
        elif qty > self.limits.max_order_qty:
            violations.append(
                f"Order quantity {qty:,} exceeds max allowed ({self.limits.max_order_qty:,})"
            )

        if order_value > self.limits.max_order_value:
            violations.append(
                f"Order value ₹{order_value:,.2f} exceeds per-order ceiling of ₹{self.limits.max_order_value:,.2f}"
            )

        # Daily Drawdown Guardrail
        if not self._lockout_active and self._daily_realized_pnl < -abs(self.limits.max_daily_loss):
            warnings.append(
                f"Trader Override Active: realized daily loss ₹{abs(self._daily_realized_pnl):,.2f} "
                f"exceeds budget ₹{self.limits.max_daily_loss:,.2f}"
            )

        # 4. Stop-Loss Guardrails & Fat-Finger Protection
        if is_derivative and self.limits.require_sl_for_derivatives:
            if trigger_price <= 0 and order_params.get("orderType") not in ("SL", "SL-M"):
                warnings.append(
                    f"Derivative order for {symbol} has no Stop-Loss protection set"
                )

        if price == 0 and ref_price > 0:
            warnings.append(f"MARKET order will execute at best available book price (~₹{ref_price:,.2f})")
        elif price > 0 and quote_price > 0:
            # Fat-finger deviation check (>10% from current LTP)
            if side == "B" and price > quote_price * 1.10:
                dev = ((price - quote_price) / quote_price) * 100.0
                warnings.append(f"FAT-FINGER ALERT: Buy limit ₹{price:,.2f} is {dev:.1f}% above market LTP ₹{quote_price:,.2f}")
            elif side == "S" and price < quote_price * 0.90:
                dev = ((quote_price - price) / quote_price) * 100.0
                warnings.append(f"FAT-FINGER ALERT: Sell limit ₹{price:,.2f} is {dev:.1f}% below market LTP ₹{quote_price:,.2f}")

        # 5. Position Sizing & Exposure Check
        current_sym_qty = 0
        current_sym_val = 0.0
        total_exposure = 0.0

        if positions:
            for p in positions:
                # Support both dict and Position dataclass
                p_sym = getattr(p, "trading_symbol", None) or (p.get("tradingSymbol") if isinstance(p, dict) else "")
                p_net = getattr(p, "net_qty", None) or (p.get("netQty") if isinstance(p, dict) else 0)
                p_rate = getattr(p, "avg_price", None) or (p.get("avgPrice") if isinstance(p, dict) else 0.0)
                try:
                    p_net_int = int(p_net or 0)
                    p_rate_flt = float(p_rate or 0.0)
                except (ValueError, TypeError):
                    p_net_int, p_rate_flt = 0, 0.0

                pos_val = abs(p_net_int * p_rate_flt)
                total_exposure += pos_val
                if p_sym == symbol:
                    current_sym_qty = p_net_int
                    current_sym_val = pos_val

        # Projected exposure if filled
        new_sym_qty = (current_sym_qty + qty) if side == "B" else (current_sym_qty - qty)
        projected_sym_val = abs(new_sym_qty * ref_price)
        if abs(new_sym_qty) > self.limits.max_position_qty:
            violations.append(
                f"Projected position {abs(new_sym_qty):,} for {symbol} exceeds max position limit ({self.limits.max_position_qty:,})"
            )
        if projected_sym_val > self.limits.max_position_value:
            violations.append(
                f"Projected exposure ₹{projected_sym_val:,.2f} for {symbol} exceeds max symbol limit of ₹{self.limits.max_position_value:,.2f}"
            )

        projected_total = total_exposure + order_value
        if projected_total > self.limits.max_portfolio_exposure:
            warnings.append(
                f"Total gross exposure will reach ₹{projected_total:,.2f} (cap: ₹{self.limits.max_portfolio_exposure:,.2f})"
            )

        # 6. Margin Check (Simple Equity / Margin heuristic)
        margin_pct = 0.20 if product in ("BIGTRADE", "MIS", "INTRADAY") else 1.00
        estimated_margin = order_value * margin_pct
        if available_funds > 0 and estimated_margin > available_funds:
            warnings.append(
                f"Estimated margin ₹{estimated_margin:,.2f} exceeds available funds ₹{available_funds:,.2f}"
            )

        # 7. Compute Risk Score
        risk_state_helper = RiskState(
            limits=self.limits,
            realized_daily_pnl=self._daily_realized_pnl,
            gross_exposure=total_exposure,
            lockout_active=self._lockout_active,
        )
        has_sl = (trigger_price > 0) or (order_params.get("orderType") in ("SL", "SL-M"))
        score, rating = risk_state_helper.calculate_risk_score(
            order_value=order_value,
            projected_sym_value=projected_sym_val,
            is_derivative=is_derivative,
            has_sl=has_sl,
        )

        allowed = len(violations) == 0 if self.limits.enforce_limits else True
        return RiskCheckResult(
            allowed=allowed,
            violations=violations,
            warnings=warnings,
            estimated_margin=estimated_margin,
            daily_pnl=self._daily_realized_pnl,
            risk_score=score,
            risk_rating=rating,
        )

    def check_pre_ticket(self, symbol: str, positions: Sequence[Any] | None = None) -> tuple[bool, str]:
        """Fast pre-ticket check before even opening order dialog."""
        if self._lockout_active:
            return False, f"Trading locked out: {self._lockout_reason}"
        if not self._check_rate_limit():
            return False, f"Order submission throttled (>{self.limits.max_orders_per_minute}/min)"
        if positions and self.limits.enforce_limits:
            for p in positions:
                p_sym = getattr(p, "trading_symbol", None) or (p.get("tradingSymbol") if isinstance(p, dict) else "")
                p_net = getattr(p, "net_qty", None) or (p.get("netQty") if isinstance(p, dict) else 0)
                try:
                    p_qty = abs(int(p_net or 0))
                except (ValueError, TypeError):
                    p_qty = 0
                if p_sym == symbol and p_qty >= self.limits.max_position_qty:
                    return False, f"Existing position in {symbol} ({p_qty:,}) has reached max position cap ({self.limits.max_position_qty:,})"
        return True, ""

