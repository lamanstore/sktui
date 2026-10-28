"""Watchlist store — persistent ordered list of scrips to watch.

The store owns:
  - loading / saving the watchlist JSON file
  - add / remove / membership checks
  - deriving the feed key for any scrip
  - the default watchlist seeded on first run
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sktui.config import WATCH_FILE
from sktui.utils import read_json, scrip_label, write_private

DEFAULT_WATCH: list[dict] = [
    {"scripCode": 23481, "tradingSymbol": "ONGC",     "companyName": "Oil and Natural Gas Corp Ltd",  "exchange": "NC"},
    {"scripCode": 2885,  "tradingSymbol": "RELIANCE",  "companyName": "Reliance Industries Ltd",        "exchange": "NC"},
    {"scripCode": 11536, "tradingSymbol": "TCS",       "companyName": "Tata Consultancy Services Ltd", "exchange": "NC"},
    {"scripCode": 1594,  "tradingSymbol": "INFY",      "companyName": "Infosys Ltd",                   "exchange": "NC"},
    {"scripCode": 1333,  "tradingSymbol": "HDFCBANK",  "companyName": "HDFC Bank Ltd",                 "exchange": "NC"},
    {"scripCode": 3045,  "tradingSymbol": "SBIN",      "companyName": "State Bank of India",           "exchange": "NC"},
]


class WatchlistStore:
    """Manages the persistent watchlist.

    Parameters
    ----------
    path:   Override the watchlist JSON path (useful for tests).
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or WATCH_FILE
        saved = read_json(self._path, [])
        self._items: list[dict] = saved if saved else list(DEFAULT_WATCH)
        if not saved:
            self._save()

    # ── Public interface ──────────────────────────────────────────────────────
    @property
    def items(self) -> list[dict]:
        """Ordered list of scrip dicts (do not mutate directly)."""
        return self._items

    @staticmethod
    def feed_key(item: dict) -> str:
        return f"{item['exchange']}{item['scripCode']}"

    def contains(self, item: dict) -> bool:
        k = self.feed_key(item)
        return any(self.feed_key(w) == k for w in self._items)

    def add(self, item: dict) -> bool:
        """Add a scrip; returns False if already present."""
        if self.contains(item):
            return False
        self._items.append(item)
        self._save()
        return True

    def remove(self, item: dict) -> bool:
        """Remove by feed key; returns False if not found."""
        k = self.feed_key(item)
        before = len(self._items)
        self._items = [w for w in self._items if self.feed_key(w) != k]
        if len(self._items) < before:
            self._save()
            return True
        return False

    def feed_keys(self) -> list[str]:
        """Current list of feed keys for the websocket subscription."""
        return [self.feed_key(w) for w in self._items]

    def label(self, item: dict) -> str:
        return scrip_label(item)

    # ── Persistence ───────────────────────────────────────────────────────────
    def _save(self) -> None:
        write_private(self._path, self._items)

    def reload(self) -> None:
        saved = read_json(self._path, [])
        if saved:
            self._items = saved
