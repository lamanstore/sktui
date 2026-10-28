"""Execution audit trail service for SKTUI.

Maintains an immutable, append-only log of all order intents, risk validations,
exchange acknowledgements, fills, cancellations, and rejections.
Enables full post-session replay and trade auditing.
"""
from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sktui.config import DATA


@dataclass
class AuditEvent:
    """A single immutable audit record."""
    timestamp: str
    event_type: str  # e.g., ORDER_INTENT, RISK_PASS, RISK_BLOCK, ORDER_SUBMIT, FILL, REJECT, CANCEL
    symbol: str
    exchange: str
    side: str
    quantity: int
    price: float
    order_id: str = ""
    status: str = ""
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class AuditTrail:
    """Manages the on-disk JSONL audit trail and in-memory recent event ring."""

    def __init__(self, audit_dir: Path | None = None, max_recent: int = 200) -> None:
        self.audit_dir = audit_dir or (DATA / "audit")
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.audit_dir / "audit.jsonl"
        self._recent: deque[AuditEvent] = deque(maxlen=max_recent)
        self._load_recent()

    def _load_recent(self) -> None:
        """Load recent events from the log file on startup if it exists."""
        if not self.log_file.exists():
            return
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()[-self._recent.maxlen:]
                for line in lines:
                    line = line.strip()
                    if line:
                        try:
                            d = json.loads(line)
                            self._recent.append(AuditEvent(**d))
                        except Exception:
                            pass
        except Exception:
            pass

    def record(
        self,
        event_type: str,
        symbol: str,
        exchange: str = "NC",
        side: str = "",
        quantity: int = 0,
        price: float = 0.0,
        order_id: str = "",
        status: str = "",
        reason: str = "",
        payload: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Record an audit event to disk and in-memory ring."""
        event = AuditEvent(
            timestamp=datetime.now().isoformat(timespec="milliseconds"),
            event_type=event_type,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_id=order_id,
            status=status,
            reason=reason,
            payload=payload or {},
        )
        self._recent.append(event)
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
        except Exception:
            pass
        return event

    def recent_events(self, limit: int = 50) -> list[AuditEvent]:
        """Return the most recent audit events."""
        return list(self._recent)[-limit:]


# Global singleton audit instance
audit_trail = AuditTrail()
