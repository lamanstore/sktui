"""Interactive chart canvas — a focusable Static that maps mouse input to chart space.

The chart renderers in :mod:`sktui.chart` attach ``_chart_meta`` (grid origin,
column density, price range) to the ``Text`` they return.  This widget keeps
that metadata so a mouse click can be translated into ``(bar_index, price)``
and the wheel into zoom / pan requests, which are posted as messages for the
owning panel or screen to act on.
"""
from __future__ import annotations

from typing import Any

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widgets import Static


class InteractiveChartCanvas(Static):
    """Static chart surface emitting :class:`Clicked` and :class:`Wheel` messages."""

    can_focus = True

    DEFAULT_CSS = """
    InteractiveChartCanvas {
        text-wrap: nowrap;
        text-overflow: clip;
        overflow: hidden hidden;
    }
    """

    class Clicked(Message):
        """User clicked inside the chart. ``idx`` is relative to the visible window."""

        def __init__(self, canvas: "InteractiveChartCanvas", idx: int | None, price: float | None) -> None:
            super().__init__()
            self.canvas = canvas
            self.idx = idx
            self.price = price

    class Wheel(Message):
        """Mouse wheel over the chart: ``direction`` −1 = up (zoom in), +1 = down."""

        def __init__(self, canvas: "InteractiveChartCanvas", direction: int, shift: bool) -> None:
            super().__init__()
            self.canvas = canvas
            self.direction = direction
            self.shift = shift

    def __init__(self, renderable: Any = "", **kwargs: Any) -> None:
        super().__init__(renderable, **kwargs)
        self.meta: dict | None = None

    # ── Rendering ─────────────────────────────────────────────────────────────
    def set_chart(self, text: Text | str) -> None:
        """Display *text* and remember its grid geometry for hit-testing."""
        self.meta = getattr(text, "_chart_meta", None)
        try:
            self.update(text)
        except Exception:
            pass

    @property
    def chart_size(self) -> tuple[int, int]:
        """Usable ``(width, height)`` in cells (content area, sans padding/border)."""
        sz = self.content_size
        return max(0, sz.width), max(0, sz.height)

    # ── Hit-testing ───────────────────────────────────────────────────────────
    def locate(self, x: int, y: int) -> tuple[int | None, float | None]:
        """Map content-relative ``(x, y)`` to ``(window_bar_idx, price)``."""
        m = self.meta
        if not m:
            return None, None
        idx: int | None = None
        price: float | None = None
        r = y - int(m.get("grid_row0", 0))
        rows = int(m.get("grid_rows", 0))
        if 0 <= r < rows:
            hi, lo = float(m["hi"]), float(m["lo"])
            price = hi - (r / max(1, rows - 1)) * (hi - lo)
        c = x - int(m.get("plot_x0", 0))
        n = int(m.get("n", 0))
        plot_w = int(m.get("plot_w", 0))
        if n > 0 and 0 <= c < plot_w:
            if m.get("kind") == "line":
                dots = plot_w * 2
                idx = int(round(c * 2 * (n - 1) / max(1, dots - 1))) if n > 1 else 0
            else:
                idx = c // max(1, int(m.get("step", 1)))
            idx = max(0, min(n - 1, idx))
        return idx, price

    def on_click(self, event: events.Click) -> None:
        off = event.get_content_offset(self)
        if off is None:
            return
        idx, price = self.locate(off.x, off.y)
        if idx is None and price is None:
            return
        event.stop()
        self.post_message(self.Clicked(self, idx, price))

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        event.prevent_default()
        self.post_message(self.Wheel(self, -1, bool(event.shift)))

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        event.prevent_default()
        self.post_message(self.Wheel(self, 1, bool(event.shift)))

