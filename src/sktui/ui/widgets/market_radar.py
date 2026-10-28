"""Market radar sidebar widget."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static


class MarketRadarSidebar(Static):
    """Dynamic sidebar for Market Intelligence and Sectors."""

    def compose(self) -> ComposeResult:
        yield Static("MARKET SESSION", classes="nav-section-header")
        yield Static("", id="radar-session", classes="nav-item")
        yield Static("SECTOR RADAR", classes="nav-section-header")
        yield Static("", id="radar-sectors", classes="nav-item")
        yield Static("BREADTH & TREND", classes="nav-section-header")
        yield Static("", id="radar-breadth", classes="nav-item")
        yield Static("SHORTCUTS", classes="nav-section-header")
        shortcuts = Text()
        shortcuts.append("  [1-7]", style="bold #00e5ff")
        shortcuts.append("  Tabs\n", style="#475569")
        shortcuts.append("  [b/s]", style="bold #00e5ff")
        shortcuts.append("  Buy/Sell\n", style="#475569")
        shortcuts.append("  [a/Del]", style="bold #00e5ff")
        shortcuts.append("  Add/Rem\n", style="#475569")
        shortcuts.append("  [c/i]", style="bold #00e5ff")
        shortcuts.append("  Chart/Info\n", style="#475569")
        shortcuts.append("  [/]", style="bold #00e5ff")
        shortcuts.append("  Commands\n", style="#475569")
        shortcuts.append("  [ESC]", style="bold #00e5ff")
        shortcuts.append("  Close modal", style="#475569")
        yield Static(shortcuts, classes="nav-item")
