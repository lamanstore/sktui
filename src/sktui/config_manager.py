"""Profile-based configuration manager for SKTUI.

Supports named runtime profiles (default, live, paper) loaded from
~/.config/sktui/config.json and validated on startup.

Profiles allow traders to maintain separate configurations for live trading,
paper simulation, and alternative API accounts without editing JSON directly.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sktui.config import CONF, CONFIG_FILE


# ── Profile Definitions ───────────────────────────────────────────────────────

@dataclass
class ProfileConfig:
    """Runtime configuration for a single named profile."""
    name: str = "default"
    paper: bool = False
    log_level: str = "INFO"
    max_reconnect_attempts: int = 5
    reconnect_delay_s: float = 2.0
    stale_threshold_s: float = 10.0
    max_order_qty: int = 10_000
    max_order_value: float = 1_000_000.0
    max_daily_loss: float = 50_000.0
    max_orders_per_minute: int = 30
    watchlist_file: str | None = None
    session_file: str | None = None
    debug: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "paper": self.paper,
            "log_level": self.log_level,
            "max_reconnect_attempts": self.max_reconnect_attempts,
            "reconnect_delay_s": self.reconnect_delay_s,
            "stale_threshold_s": self.stale_threshold_s,
            "max_order_qty": self.max_order_qty,
            "max_order_value": self.max_order_value,
            "max_daily_loss": self.max_daily_loss,
            "max_orders_per_minute": self.max_orders_per_minute,
            "watchlist_file": self.watchlist_file,
            "session_file": self.session_file,
            "debug": self.debug,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProfileConfig":
        return cls(
            name=str(d.get("name", "default")),
            paper=bool(d.get("paper", False)),
            log_level=str(d.get("log_level", "INFO")).upper(),
            max_reconnect_attempts=int(d.get("max_reconnect_attempts", 5)),
            reconnect_delay_s=float(d.get("reconnect_delay_s", 2.0)),
            stale_threshold_s=float(d.get("stale_threshold_s", 10.0)),
            max_order_qty=int(d.get("max_order_qty", 10_000)),
            max_order_value=float(d.get("max_order_value", 1_000_000.0)),
            max_daily_loss=float(d.get("max_daily_loss", 50_000.0)),
            max_orders_per_minute=int(d.get("max_orders_per_minute", 30)),
            watchlist_file=d.get("watchlist_file"),
            session_file=d.get("session_file"),
            debug=bool(d.get("debug", False)),
        )


# ── Built-in Profile Presets ──────────────────────────────────────────────────

BUILTIN_PROFILES: dict[str, ProfileConfig] = {
    "default": ProfileConfig(name="default"),
    "live": ProfileConfig(
        name="live",
        paper=False,
        log_level="INFO",
        max_order_qty=5_000,
        max_order_value=500_000.0,
        max_daily_loss=25_000.0,
        max_orders_per_minute=20,
    ),
    "paper": ProfileConfig(
        name="paper",
        paper=True,
        log_level="DEBUG",
        max_order_qty=100_000,
        max_order_value=5_000_000.0,
        max_daily_loss=1_000_000.0,
        max_orders_per_minute=100,
    ),
}


# ── Config Manager ────────────────────────────────────────────────────────────

class ConfigManager:
    """Profile-aware configuration manager.

    Loads profiles from ~/.config/sktui/config.json and validates settings.
    Falls back to built-in presets for missing profiles.
    """

    def __init__(self, conf_dir: Path | None = None) -> None:
        self._conf_dir = conf_dir or CONF
        self._conf_file = self._conf_dir / "config.json"
        self._profiles: dict[str, ProfileConfig] = dict(BUILTIN_PROFILES)
        self._load()

    def _load(self) -> None:
        """Load user-defined profiles from config.json."""
        if not self._conf_file.exists():
            return
        try:
            with open(self._conf_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            profiles_data = raw.get("profiles", [])
            if isinstance(profiles_data, list):
                for d in profiles_data:
                    p = ProfileConfig.from_dict(d)
                    self._profiles[p.name] = p
        except Exception:
            pass

    def get_profile(self, name: str) -> ProfileConfig:
        """Return named profile; falls back to 'default' if not found."""
        return self._profiles.get(name) or self._profiles.get("default") or ProfileConfig()

    def save_profile(self, profile: ProfileConfig) -> None:
        """Persist a profile to config.json."""
        self._profiles[profile.name] = profile
        try:
            self._conf_dir.mkdir(parents=True, exist_ok=True)
            existing_raw: dict[str, Any] = {}
            if self._conf_file.exists():
                try:
                    with open(self._conf_file, "r", encoding="utf-8") as f:
                        existing_raw = json.load(f)
                except Exception:
                    pass
            # Merge: only save user-defined profiles (not built-in presets unless modified)
            user_profiles = {
                n: p for n, p in self._profiles.items()
                if n not in BUILTIN_PROFILES or p != BUILTIN_PROFILES.get(n)
            }
            existing_raw["profiles"] = [p.to_dict() for p in user_profiles.values()]
            with open(self._conf_file, "w", encoding="utf-8") as f:
                json.dump(existing_raw, f, indent=2)
        except Exception:
            pass

    def validate(self, profile: ProfileConfig) -> list[str]:
        """Return list of validation warnings for a profile."""
        warnings: list[str] = []
        if not profile.paper:
            if not os.environ.get("SK_API_KEY"):
                warnings.append("SK_API_KEY environment variable is not set")
            api_key = os.environ.get("SK_API_KEY", "")
            if api_key and len(api_key) < 16:
                warnings.append("SK_API_KEY appears too short — verify your API key")
        if profile.max_daily_loss <= 0:
            warnings.append("max_daily_loss must be > 0 for drawdown protection")
        if profile.max_order_qty <= 0:
            warnings.append("max_order_qty must be positive")
        if profile.max_orders_per_minute > 60:
            warnings.append("max_orders_per_minute > 60 may trigger exchange rate limits")
        return warnings

    def list_profile_names(self) -> list[str]:
        return sorted(self._profiles.keys())

    def startup_validation_report(self, profile_name: str) -> tuple[ProfileConfig, list[str]]:
        """Run startup validation and return (profile, warning_list)."""
        profile = self.get_profile(profile_name)
        warnings = self.validate(profile)
        return profile, warnings


# Global singleton
config_manager = ConfigManager()
