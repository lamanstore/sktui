"""Order state store — lifecycle management, state transitions, and audit tracking.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from sktui.services.audit import audit_trail


class OrderStatus(str, Enum):
    NEW = "NEW"
    PENDING_SUBMIT = "PENDING_SUBMIT"
    OPEN = "OPEN"
    TRIGGER_PENDING = "TRIGGER_PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderRejectCode(str, Enum):
    """Categorized RMS and exchange rejection reason codes."""
    NONE = "NONE"
    RMS_INSUFFICIENT_MARGIN = "RMS_INSUFFICIENT_MARGIN"
    RMS_CIRCUIT_LIMIT = "RMS_CIRCUIT_LIMIT"
    RMS_MAX_QTY_EXCEEDED = "RMS_MAX_QTY_EXCEEDED"
    RMS_DRAWDOWN_LOCKOUT = "RMS_DRAWDOWN_LOCKOUT"
    RMS_DERIVATIVE_NO_SL = "RMS_DERIVATIVE_NO_SL"
    RMS_RATE_LIMIT_EXCEEDED = "RMS_RATE_LIMIT_EXCEEDED"
    MARKET_CLOSED = "MARKET_CLOSED"
    EXCHANGE_UNREACHABLE = "EXCHANGE_UNREACHABLE"
    INVALID_PRICE_TICK = "INVALID_PRICE_TICK"
    USER_CANCELLED = "USER_CANCELLED"
    UNKNOWN = "UNKNOWN"


def parse_reject_code(error_msg: str) -> OrderRejectCode:
    """Classify arbitrary error message strings into typed reject reason codes."""
    msg = (error_msg or "").lower()
    if not msg:
        return OrderRejectCode.NONE
    if any(w in msg for w in ("circuit", "freeze", "price band", "band", "range")):
        return OrderRejectCode.RMS_CIRCUIT_LIMIT
    if any(w in msg for w in ("rate limit", "too many requests", "throttle")):
        return OrderRejectCode.RMS_RATE_LIMIT_EXCEEDED
    if any(w in msg for w in ("drawdown", "loss limit")):
        return OrderRejectCode.RMS_DRAWDOWN_LOCKOUT
    if any(w in msg for w in ("stop loss", "stop-loss", "sl required")):
        return OrderRejectCode.RMS_DERIVATIVE_NO_SL
    if any(w in msg for w in ("qty", "quantity", "max order")):
        return OrderRejectCode.RMS_MAX_QTY_EXCEEDED
    if any(w in msg for w in ("margin", "fund", "balance", "trading limit")):
        return OrderRejectCode.RMS_INSUFFICIENT_MARGIN
    if any(w in msg for w in ("closed", "outside trading hours", "session")):
        return OrderRejectCode.MARKET_CLOSED
    if any(w in msg for w in ("unreachable", "timeout", "connection", "network")):
        return OrderRejectCode.EXCHANGE_UNREACHABLE
    if any(w in msg for w in ("tick", "multiple", "lot")):
        return OrderRejectCode.INVALID_PRICE_TICK
    if any(w in msg for w in ("cancelled", "user cancel")):
        return OrderRejectCode.USER_CANCELLED
    return OrderRejectCode.UNKNOWN


@dataclass
class TrackedOrder:
    order_id: str
    trading_symbol: str
    exchange: str
    side: str
    quantity: int
    price: float
    trigger_price: float = 0.0
    executed_qty: int = 0
    average_price: float = 0.0
    status: OrderStatus = OrderStatus.NEW
    raw_status: str = ""
    rejection_reason: str = ""
    reject_code: OrderRejectCode = OrderRejectCode.NONE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    raw_record: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.NEW, OrderStatus.PENDING_SUBMIT, OrderStatus.OPEN, OrderStatus.TRIGGER_PENDING, OrderStatus.PARTIALLY_FILLED)

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED

    @property
    def is_terminal(self) -> bool:
        return self.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)


class OrderStore:
    """Manages active and historical orders with deterministic state progression."""

    def __init__(self) -> None:
        self._orders: dict[str, TrackedOrder] = {}
        self._listeners: list[Callable[[TrackedOrder], None]] = []

    def load_from_audit(self) -> None:
        """Reconstruct order state machine history from immutable audit trail.

        Call this explicitly after startup (e.g. in MainScreen.on_mount) so that
        unit-tested OrderStore instances remain isolated from persisted sessions.
        """
        for ev in audit_trail.recent_events(limit=500):
            oid = ev.order_id
            if not oid:
                continue
            if ev.event_type == "ORDER_INTENT":
                order = TrackedOrder(
                    order_id=oid,
                    trading_symbol=ev.symbol,
                    exchange=ev.exchange,
                    side=ev.side,
                    quantity=ev.quantity,
                    price=ev.price,
                    status=OrderStatus.PENDING_SUBMIT,
                    raw_record=ev.payload,
                )
                self._orders[oid] = order
            elif oid in self._orders:
                order = self._orders[oid]
                if ev.status:
                    order.status = self.normalize_status(ev.status)
                if ev.reason:
                    order.rejection_reason = ev.reason
                    if order.status == OrderStatus.REJECTED:
                        order.reject_code = parse_reject_code(ev.reason)

    def get_timeline(self, order_id: str) -> list[Any]:
        """Return all historical audit events associated with a specific order ID."""
        return [ev for ev in audit_trail.recent_events(limit=500) if ev.order_id == order_id]

    def add_listener(self, callback: Callable[[TrackedOrder], None]) -> None:
        self._listeners.append(callback)

    def _notify(self, order: TrackedOrder) -> None:
        for listener in self._listeners:
            try:
                listener(order)
            except Exception:
                pass

    def normalize_status(self, raw_status: str) -> OrderStatus:
        s = str(raw_status).strip().upper()
        if "FUL" in s or "EXEC" in s or "COMPLETE" in s:
            return OrderStatus.FILLED
        if "PART" in s:
            return OrderStatus.PARTIALLY_FILLED
        if "CANCEL" in s:
            return OrderStatus.CANCELLED
        if "REJ" in s or "FAIL" in s:
            return OrderStatus.REJECTED
        if "TRIG" in s:
            return OrderStatus.TRIGGER_PENDING
        if "OPEN" in s or "CONFIRM" in s or "VALID" in s:
            return OrderStatus.OPEN
        if "PEND" in s:
            return OrderStatus.PENDING_SUBMIT
        return OrderStatus.OPEN

    def record_intent(self, params: dict[str, Any]) -> TrackedOrder:
        order_id = str(params.get("orderId") or f"INTENT-{int(datetime.now().timestamp()*1000)}")
        symbol = str(params.get("tradingSymbol", ""))
        exch = str(params.get("exchange", "NC"))
        side = str(params.get("transactionType", "B"))
        qty = int(params.get("quantity") or 0)
        try:
            price = float(params.get("price") or 0.0)
        except Exception:
            price = 0.0
        try:
            trig = float(params.get("triggerPrice") or 0.0)
        except Exception:
            trig = 0.0

        order = TrackedOrder(
            order_id=order_id,
            trading_symbol=symbol,
            exchange=exch,
            side=side,
            quantity=qty,
            price=price,
            trigger_price=trig,
            status=OrderStatus.PENDING_SUBMIT,
            raw_record=params,
        )
        self._orders[order_id] = order
        audit_trail.record(
            event_type="ORDER_INTENT",
            symbol=symbol,
            exchange=exch,
            side=side,
            quantity=qty,
            price=price,
            order_id=order_id,
            status="PENDING_SUBMIT",
            payload=params,
        )
        self._notify(order)
        return order

    def update_from_feed(self, raw_order: dict[str, Any]) -> TrackedOrder:
        order_id = str(raw_order.get("orderId") or "")
        if not order_id:
            order_id = str(raw_order.get("ordId") or "")
        symbol = str(raw_order.get("tradingSymbol") or "")
        raw_status = str(raw_order.get("orderStatus") or "")
        norm_status = self.normalize_status(raw_status)
        reason = str(raw_order.get("errorMsg") or raw_order.get("reason") or "")

        try:
            exec_qty = int(raw_order.get("execQty") or raw_order.get("executedQty") or 0)
        except Exception:
            exec_qty = 0
        try:
            avg_price = float(raw_order.get("execPrice") or raw_order.get("averagePrice") or 0.0)
        except Exception:
            avg_price = 0.0

        if order_id in self._orders:
            order = self._orders[order_id]
            prev_status = order.status
            order.status = norm_status
            order.raw_status = raw_status
            order.executed_qty = exec_qty
            order.average_price = avg_price
            order.rejection_reason = reason
            if norm_status == OrderStatus.REJECTED:
                order.reject_code = parse_reject_code(reason)
            order.updated_at = datetime.now()
            order.raw_record = raw_order

            if prev_status != norm_status:
                ev_type = (
                    "ORDER_FILLED" if norm_status == OrderStatus.FILLED
                    else "ORDER_CANCELLED" if norm_status == OrderStatus.CANCELLED
                    else "ORDER_REJECTED" if norm_status == OrderStatus.REJECTED
                    else "ORDER_STATUS_UPDATE"
                )
                audit_trail.record(
                    event_type=ev_type,
                    symbol=order.trading_symbol,
                    exchange=order.exchange,
                    side=order.side,
                    quantity=order.quantity,
                    price=order.price,
                    order_id=order_id,
                    status=norm_status.value,
                    reason=f"[{order.reject_code.value}] {reason}" if reason else order.reject_code.value,
                    payload=raw_order,
                )
        else:
            try:
                qty = int(raw_order.get("orderQty") or raw_order.get("quantity") or 0)
            except Exception:
                qty = 0
            try:
                price = float(raw_order.get("orderPrice") or raw_order.get("price") or 0.0)
            except Exception:
                price = 0.0
            order = TrackedOrder(
                order_id=order_id,
                trading_symbol=symbol,
                exchange=str(raw_order.get("exchange") or "NC"),
                side=str(raw_order.get("buySell") or raw_order.get("transactionType") or "B"),
                quantity=qty,
                price=price,
                executed_qty=exec_qty,
                average_price=avg_price,
                status=norm_status,
                raw_status=raw_status,
                rejection_reason=reason,
                reject_code=parse_reject_code(reason) if norm_status == OrderStatus.REJECTED else OrderRejectCode.NONE,
                raw_record=raw_order,
            )
            self._orders[order_id] = order

        self._notify(order)
        return order

    def get_order(self, order_id: str) -> TrackedOrder | None:
        return self._orders.get(order_id)

    def active_orders(self) -> list[TrackedOrder]:
        return [o for o in self._orders.values() if o.is_active]

    def all_orders(self) -> list[TrackedOrder]:
        return sorted(self._orders.values(), key=lambda o: o.created_at, reverse=True)
