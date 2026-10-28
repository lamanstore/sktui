"""Alert Store — in-memory + JSON-backed alert registry for SKTUI.

Manages the full lifecycle of configured price/technical alerts:
  - Create, retrieve, update, and delete alerts
  - Persist alerts to ~/.config/sktui/alerts.json
  - Track trigger history and repeat behaviour

Decoupled from AlertEngine — the engine uses this store as its backing.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sktui.config import ALERTS_FILE


@dataclass
class Alert:
    """A single configured price or technical trigger."""
    id: str
    symbol: str
    condition: str      # ABOVE | BELOW | RSI_OB | RSI_OS | VOL_SPIKE
    target_value: float
    message: str = ""
    triggered: bool = False
    triggered_at: str = ""
    repeat: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Alert":
        return cls(
            id=str(d.get("id", "")),
            symbol=str(d.get("symbol", "")).upper(),
            condition=str(d.get("condition", "ABOVE")).upper(),
            target_value=float(d.get("target_value") or 0.0),
            message=str(d.get("message", "")),
            triggered=bool(d.get("triggered", False)),
            triggered_at=str(d.get("triggered_at", "")),
            repeat=bool(d.get("repeat", False)),
        )

    @property
    def is_active(self) -> bool:
        """Return True if this alert has not yet fired (or is set to repeat)."""
        return not self.triggered or self.repeat

    def human_description(self) -> str:
        """Return a human-readable one-liner for display."""
        cond_map = {
            "ABOVE": ">",
            "BELOW": "<",
            "RSI_OB": "RSI >",
            "RSI_OS": "RSI <",
            "VOL_SPIKE": "VOL >",
        }
        op = cond_map.get(self.condition, self.condition)
        return f"{self.symbol} {op} {self.target_value}"


class AlertStore:
    """Manages configured alerts with JSON persistence.

    JSON file: ~/.config/sktui/alerts.json (0o600 permissions)
    """

    def __init__(self, alerts_file: Path | None = None) -> None:
        self._file: Path = alerts_file or ALERTS_FILE
        self._alerts: dict[str, Alert] = {}
        self._listeners: list[Callable[[Alert], None]] = []
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load alerts from JSON file (ignore errors to avoid startup crashes)."""
        if not self._file.exists():
            return
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for d in data:
                a = Alert.from_dict(d)
                self._alerts[a.id] = a
        except Exception:
            pass

    def save(self) -> None:
        """Persist all alerts to JSON with restricted file permissions."""
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps([a.to_dict() for a in self._alerts.values()], indent=2)
            tmp = self._file.with_suffix(".json.tmp")
            tmp.write_text(raw, encoding="utf-8")
            tmp.replace(self._file)
            try:
                os.chmod(self._file, 0o600)
            except Exception:
                pass
        except Exception:
            pass

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(
        self,
        symbol: str,
        condition: str,
        target_value: float,
        message: str = "",
        repeat: bool = False,
    ) -> Alert:
        """Create a new alert and persist it."""
        alert_id = f"{symbol}_{condition}_{int(datetime.now().timestamp() * 1000)}"
        alert = Alert(
            id=alert_id,
            symbol=symbol.upper(),
            condition=condition.upper(),
            target_value=target_value,
            message=message or f"{symbol} {condition} {target_value}",
            repeat=repeat,
        )
        self._alerts[alert_id] = alert
        self.save()
        return alert

    def remove(self, alert_id: str) -> bool:
        """Delete an alert by ID. Returns True if it existed."""
        existed = alert_id in self._alerts
        self._alerts.pop(alert_id, None)
        if existed:
            self.save()
        return existed

    def clear_triggered(self) -> int:
        """Delete all alerts that have been triggered and are not set to repeat."""
        remove_ids = [
            aid for aid, a in self._alerts.items()
            if a.triggered and not a.repeat
        ]
        for aid in remove_ids:
            del self._alerts[aid]
        if remove_ids:
            self.save()
        return len(remove_ids)

    def clear_all(self) -> int:
        """Delete all alerts. Returns count removed."""
        count = len(self._alerts)
        self._alerts.clear()
        self.save()
        return count

    def get(self, alert_id: str) -> Alert | None:
        return self._alerts.get(alert_id)

    def all_alerts(self) -> list[Alert]:
        return list(self._alerts.values())

    def active_alerts(self) -> list[Alert]:
        return [a for a in self._alerts.values() if a.is_active]

    def triggered_alerts(self) -> list[Alert]:
        return [a for a in self._alerts.values() if a.triggered]

    def alerts_for_symbol(self, symbol: str) -> list[Alert]:
        return [a for a in self._alerts.values() if a.symbol == symbol.upper()]

    # ── Trigger ───────────────────────────────────────────────────────────────

    def mark_triggered(self, alert_id: str) -> Alert | None:
        """Mark an alert as triggered, record timestamp, and persist."""
        alert = self._alerts.get(alert_id)
        if alert:
            alert.triggered = True
            alert.triggered_at = datetime.now().isoformat(timespec="seconds")
            self.save()
            for listener in self._listeners:
                try:
                    listener(alert)
                except Exception:
                    pass
        return alert

    def add_trigger_listener(self, callback: Callable[[Alert], None]) -> None:
        """Register a callback invoked whenever an alert is marked triggered."""
        self._listeners.append(callback)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self._alerts),
            "active": len(self.active_alerts()),
            "triggered": len(self.triggered_alerts()),
        }
