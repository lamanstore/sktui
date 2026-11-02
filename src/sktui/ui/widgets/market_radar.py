"""Market radar sidebar widget."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static

from sktui.themes import current_palette


class MarketRadarSidebar(Static):
    """Dynamic sidebar for Market Intelligence and Sectors."""

    def compose(self) -> ComposeResult:
        p = current_palette()
        yield Static("MARKET SESSION", classes="nav-section-header")
        yield Static("", id="radar-session", classes="nav-item")
        yield Static("SECTOR RADAR", classes="nav-section-header")
        yield Static("", id="radar-sectors", classes="nav-item")
        yield Static("BREADTH & TREND", classes="nav-section-header")
        yield Static("", id="radar-breadth", classes="nav-item")
        yield Static("SHORTCUTS", classes="nav-section-header")
        shortcuts = Text()
        shortcuts.append("  [1-7]", style=f"bold {p.primary}")
        shortcuts.append("  Tabs\n", style=p.subtle)
        shortcuts.append("  [b/s]", style=f"bold {p.primary}")
        shortcuts.append("  Buy/Sell\n", style=p.subtle)
        shortcuts.append("  [a/Del]", style=f"bold {p.primary}")
        shortcuts.append("  Add/Rem\n", style=p.subtle)
        shortcuts.append("  [c/i]", style=f"bold {p.primary}")
        shortcuts.append("  Chart/Info\n", style=p.subtle)
        shortcuts.append("  [/]", style=f"bold {p.primary}")
        shortcuts.append("  Commands\n", style=p.subtle)
        shortcuts.append("  [ESC]", style=f"bold {p.primary}")
        shortcuts.append("  Close modal", style=p.subtle)
        yield Static(shortcuts, classes="nav-item")
