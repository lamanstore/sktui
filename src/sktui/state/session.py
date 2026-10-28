"""Session state — authenticated client reference and app-level flags."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sktui.api.client import Client


class Session:
    """Holds the authenticated API client and app-level runtime flags.

    This is the single source of truth for "is there a live session?" so
    screens and services never need to reach into SKApp directly.

    Usage::

        session = Session()
        session.client = api.Client(...)
        session.paper  = True
    """

    def __init__(self) -> None:
        self.client: "Client | None" = None
        self.paper: bool = False
        self.public_ip: str = "Fetching…"
        self.enable_feed: bool = True

    @property
    def is_authenticated(self) -> bool:
        return self.client is not None

    @property
    def customer_id(self) -> str:
        return self.client.customer_id if self.client else ""

    @property
    def login_id(self) -> str:
        return self.client.login_id if self.client else ""

    @property
    def full_name(self) -> str:
        return self.client.full_name if self.client else ""

    @property
    def exchanges(self) -> list[str]:
        return self.client.exchanges if self.client else []

    def clear(self) -> None:
        """Clear the session (after logout)."""
        self.client = None
        self.public_ip = "Fetching…"
