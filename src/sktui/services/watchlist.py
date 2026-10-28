"""Watchlist service — add/remove/refresh symbol orchestration.

Sits between the WatchlistStore (data) and the UI (MainScreen).
Owns the feed subscription side-effect so the UI never talks to the
Feed directly for watchlist changes.

Usage::

    svc = WatchlistService(store, feed)
    svc.add(screen, item)
    svc.remove(screen, item)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from sktui.state.watchlist_store import WatchlistStore
from sktui.utils import scrip_label

if TYPE_CHECKING:
    from sktui.api.feed import Feed


class WatchlistService:
    """Orchestrates watchlist mutations and keeps the feed in sync."""

    def __init__(self, store: WatchlistStore, feed: "Feed | None" = None) -> None:
        self._store = store
        self._feed  = feed

    @property
    def store(self) -> WatchlistStore:
        return self._store

    def set_feed(self, feed: "Feed | None") -> None:
        """Inject or replace the active feed after login."""
        self._feed = feed

    # ── Mutations ─────────────────────────────────────────────────────────────
    def add(
        self,
        item: dict,
        on_success: Callable[[dict, str], None] | None = None,
        on_duplicate: Callable[[str], None] | None = None,
    ) -> bool:
        """Add *item* to the watchlist.

        Calls on_success(item, label) if added, on_duplicate(label) if already present.
        Returns True when the item was added.
        """
        sym = scrip_label(item)
        if not self._store.add(item):
            if on_duplicate:
                on_duplicate(sym)
            return False
        if self._feed:
            self._feed.subscribe(self._store.feed_key(item))
        if on_success:
            on_success(item, sym)
        return True

    def remove(
        self,
        item: dict,
        on_success: Callable[[str], None] | None = None,
        on_missing: Callable[[str], None] | None = None,
    ) -> bool:
        """Remove *item* from the watchlist.

        Calls on_success(label) if removed, on_missing(label) if not found.
        Returns True when the item was removed.
        """
        sym = scrip_label(item)
        if not self._store.remove(item):
            if on_missing:
                on_missing(sym)
            return False
        if self._feed:
            self._feed.unsubscribe(self._store.feed_key(item))
        if on_success:
            on_success(sym)
        return True

    # ── Queries ───────────────────────────────────────────────────────────────
    @property
    def items(self) -> list[dict]:
        return self._store.items

    def feed_keys(self) -> list[str]:
        return self._store.feed_keys()

    def contains(self, item: dict) -> bool:
        return self._store.contains(item)
