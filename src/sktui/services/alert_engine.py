"""Alert Engine for SKTUI.

Monitors incoming quotes against trader-defined thresholds:
- Price alerts (above / below target)
- Technical alerts (RSI overbought / oversold)
- Volume spike alerts
- Market session milestone reminders (IST clock)
- JSON persistence across sessions
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sktui.config import ALERTS_FILE


@dataclass
class Alert:
    """A configured price or technical trigger."""
    id: str
    symbol: str
    condition: str  # "ABOVE" | "BELOW" | "RSI_OB" | "RSI_OS" | "VOL_SPIKE"
    target_value: float
    message: str = ""
    triggered: bool = False
    triggered_at: str = ""
    repeat: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Alert:
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


def parse_alert_command(cmd_str: str) -> tuple[str, str, float] | None:
    """Parse a slash command string into (symbol, condition, target_value).

    Supported syntaxes:
    - /alert RELIANCE > 3000
    - /alert RELIANCE >= 3000
    - /alert INFY < 1400
    - /alert INFY <= 1400
    - /alert TCS ABOVE 3600
    - /alert TCS BELOW 3400
    - /alert TCS RSI > 70
    - /alert TCS RSI < 30
    - /alert TCS VOL > 2.5
    """
    s = cmd_str.strip()
    if s.lower().startswith("/alert"):
        s = s[6:].strip()
    elif s.lower().startswith("alert"):
        s = s[5:].strip()

    # Match RSI pattern: SYM RSI > 70
    rsi_match = re.match(r"^([A-Za-z0-9_\-]+)\s+RSI\s*([><]=?)\s*(\d+(?:\.\d+)?)$", s, re.IGNORECASE)
    if rsi_match:
        sym, op, val = rsi_match.groups()
        cond = "RSI_OB" if ">" in op else "RSI_OS"
        return sym.upper(), cond, float(val)

    # Match Volume pattern: SYM VOL > 2.0
    vol_match = re.match(r"^([A-Za-z0-9_\-]+)\s+VOL(?:UME)?\s*([><]=?)\s*(\d+(?:\.\d+)?)$", s, re.IGNORECASE)
    if vol_match:
        sym, op, val = vol_match.groups()
        return sym.upper(), "VOL_SPIKE", float(val)

    # Match Price operator pattern: SYM > 3000 or SYM < 1400
    op_match = re.match(r"^([A-Za-z0-9_\-]+)\s*([><]=?)\s*(\d+(?:\.\d+)?)$", s)
    if op_match:
        sym, op, val = op_match.groups()
        cond = "ABOVE" if ">" in op else "BELOW"
        return sym.upper(), cond, float(val)

    # Match Price word pattern: SYM ABOVE 3000 or SYM BELOW 1400
    word_match = re.match(r"^([A-Za-z0-9_\-]+)\s+(ABOVE|BELOW)\s+(\d+(?:\.\d+)?)$", s, re.IGNORECASE)
    if word_match:
        sym, cond, val = word_match.groups()
        return sym.upper(), cond.upper(), float(val)

    return None


class AlertEngine:
    """Evaluates market state, persists triggers, and dispatches notifications."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or ALERTS_FILE
        self.alerts: list[Alert] = []
        self._listeners: list[Callable[[Alert, float], None]] = []
        self._last_session_check: float = 0.0
        self._session_notified: set[str] = set()
        self.load()

    # ── Persistence ───────────────────────────────────────────────────────────
    def load(self) -> None:
        """Load stored alerts from JSON file."""
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self.alerts = [Alert.from_dict(d) for d in data if isinstance(d, dict)]
        except Exception:
            pass

    def save(self) -> None:
        """Atomically persist alerts list to storage path with safe permissions."""
        if not self.storage_path:
            return
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.storage_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([a.to_dict() for a in self.alerts], f, indent=2)
            os.replace(tmp, self.storage_path)
            try:
                self.storage_path.chmod(0o600)
            except Exception:
                pass
        except Exception:
            pass

    # ── Alert Management ──────────────────────────────────────────────────────
    def add_alert(self, symbol: str, condition: str, target: float, message: str = "") -> Alert:
        sym = symbol.upper().strip()
        cond = condition.upper().strip()
        alert = Alert(
            id=f"ALT-{len(self.alerts) + 1}-{int(time.time())}",
            symbol=sym,
            condition=cond,
            target_value=target,
            message=message or f"{sym} {cond} {target:,.2f}",
        )
        self.alerts.append(alert)
        self.save()
        return alert

    def remove_alert(self, alert_id: str) -> bool:
        initial_len = len(self.alerts)
        self.alerts = [a for a in self.alerts if a.id != alert_id]
        if len(self.alerts) < initial_len:
            self.save()
            return True
        return False

    def clear_all(self) -> None:
        self.alerts.clear()
        self.save()

    def add_listener(self, cb: Callable[[Alert, float], None]) -> None:
        self._listeners.append(cb)

    # ── Evaluation ────────────────────────────────────────────────────────────
    def evaluate_quote(self, symbol: str, ltp: float, rsi: float | None = None, vol: float = 0.0) -> list[Alert]:
        """Check all active alerts against new tick data and fire notifications."""
        sym = symbol.upper()
        triggered_now: list[Alert] = []
        now_str = datetime.now().strftime("%H:%M:%S")

        for alert in self.alerts:
            if alert.triggered and not alert.repeat:
                continue
            if alert.symbol != sym:
                continue

            fire = False
            if alert.condition == "ABOVE" and ltp >= alert.target_value:
                fire = True
            elif alert.condition == "BELOW" and ltp <= alert.target_value:
                fire = True
            elif alert.condition == "RSI_OB" and rsi is not None and rsi >= alert.target_value:
                fire = True
            elif alert.condition == "RSI_OS" and rsi is not None and rsi <= alert.target_value:
                fire = True

            if fire:
                alert.triggered = True
                alert.triggered_at = now_str
                triggered_now.append(alert)
                for cb in self._listeners:
                    try:
                        cb(alert, ltp)
                    except Exception:
                        pass

        if triggered_now:
            self.save()

        return triggered_now

    def evaluate_tick(self, tick: dict) -> list[Alert]:
        """Convenience method to evaluate a raw or normalized tick dict."""
        sym = str(tick.get("tradingSymbol") or tick.get("tsym") or tick.get("symbol") or "")
        ltp = float(tick.get("ltp") or tick.get("lastTradedPrice") or 0.0)
        vol = float(tick.get("qty") or tick.get("volume") or 0.0)
        if not sym or ltp <= 0.0:
            return []
        return self.evaluate_quote(sym, ltp, vol=vol)

    def check_market_session(self) -> str | None:
        """Check Indian market session hours (IST) and return announcement if at milestone."""
        now = time.monotonic()
        if now - self._last_session_check < 30.0:
            return None
        self._last_session_check = now

        now_dt = datetime.now()
        current_time_str = now_dt.strftime("%H:%M")

        milestones = {
            "09:00": "🔔 09:00 IST — NSE/BSE Pre-Market Session Open",
            "09:15": "⚡ 09:15 IST — Normal Market Trading Session Open",
            "15:15": "⚠ 15:15 IST — Intraday MIS/Auto-Square-off Warning (15m to close)",
            "15:30": "🏁 15:30 IST — Market Close",
        }

        if current_time_str in milestones and current_time_str not in self._session_notified:
            self._session_notified.add(current_time_str)
            return milestones[current_time_str]
        return None
