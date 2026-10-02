"""Pixelated braille-dot terminal chart renderer for SKTUI.

Inspired by rate.sx/btc — renders a coloured Unicode braille-dot line chart
with a Y-axis, X-axis, price labels and summary stats.  Pure Python, zero deps.
"""
from __future__ import annotations

import math
from typing import Sequence

from rich.style import Style
from rich.text import Text

# ── Braille dot mapping ───────────────────────────────────────────────────────
#  Each braille cell is 2 cols × 4 rows of dots.
#  Dot positions (col 0‥1, row 0‥3 from TOP) map to braille offsets:
#
#   col 0  col 1
#    1      4    row 0 (top)
#    2      5    row 1
#    3      6    row 2
#    7      8    row 3 (bottom)
#
BRAILLE_BASE = 0x2800
_DOT = [
    [0x01, 0x08],   # row 0: dot 1, dot 4
    [0x02, 0x10],   # row 1: dot 2, dot 5
    [0x04, 0x20],   # row 2: dot 3, dot 6
    [0x40, 0x80],   # row 3: dot 7, dot 8
]

ROWS_PER_CELL = 4   # braille rows per character row
COLS_PER_CELL = 2   # braille cols per character column


# ── Gradient palette (green→yellow→red, for down / neutral / up) ─────────────
_GREEN_GRAD = [
    "#00ff87", "#00ff5f", "#00ff00", "#00d700",
    "#00af00", "#008700", "#005f00",
]
_RED_GRAD = [
    "#ff5f5f", "#ff0000", "#d70000", "#af0000",
    "#870000", "#5f0000",
]
_CYAN_GRAD = [
    "#00ffff", "#00d7ff", "#00afff", "#0087ff",
    "#005fff", "#0000ff",
]


def _gradient_color(idx: int, total: int, up: bool) -> str:
    """Return a hex colour string for column `idx` of `total`, blending the gradient."""
    pal = _GREEN_GRAD if up else _RED_GRAD
    i   = int(idx / max(total - 1, 1) * (len(pal) - 1))
    return pal[min(i, len(pal) - 1)]


# ── Core renderer ─────────────────────────────────────────────────────────────

def render_chart(
    values:    Sequence[float],
    volumes:   Sequence[float] | None = None,
    width:     int   = 80,
    height:    int   = 16,
    label:     str   = "",
    symbol:    str   = "",
    interval:  str   = "",
    show_stats: bool = True,
    show_vol_strip: bool = True,
) -> Text:
    """
    Render *values* as a braille-dot line chart and return a Rich ``Text`` object.

    Parameters
    ----------
    values:         Sequence of price / close values (oldest → newest).
    volumes:        Sequence of volume values corresponding to price bars.
    width:          Character-width of the chart body.
    height:         Character-height of the price chart body.
    label:          Extra label shown above the chart.
    symbol:         Instrument name shown in the header.
    interval:       Interval string shown next to the symbol.
    show_stats:     Whether to append an OHLCV-style summary line.
    show_vol_strip: Whether to render a mini volume bar strip beneath the chart.
    """
    if not values:
        return Text("  — no data —", style="dim")

    vals = list(values)
    vols = list(volumes) if volumes else []

    # ── Downsample so we have exactly width*COLS_PER_CELL data points ─────────
    total_cols = width * COLS_PER_CELL
    if len(vals) > total_cols:
        step  = len(vals) / total_cols
        vals  = [vals[int(i * step)] for i in range(total_cols)]
        if vols:
            vols = [vols[int(i * step)] for i in range(total_cols)]
    else:
        # upsample (repeat) to fill width
        while len(vals) < total_cols:
            vals = [v for v in vals for _ in range(2)]
            if vols:
                vols = [v for v in vols for _ in range(2)]
        vals = vals[:total_cols]
        if vols:
            vols = vols[:total_cols]

    lo, hi   = min(vals), max(vals)
    rng      = (hi - lo) or 1.0
    total_rows = height * ROWS_PER_CELL

    # Map each sample to a braille-row index (0 = bottom, total_rows-1 = top)
    def _row(v: float) -> int:
        return max(0, min(total_rows - 1, int((v - lo) / rng * (total_rows - 1))))

    # ── Build a 2D bit grid: grid[char_row][char_col] = braille bitmask ───────
    grid: list[list[int]] = [[0] * width for _ in range(height)]

    for x, v in enumerate(vals):
        char_col  = x // COLS_PER_CELL
        bit_col   = x %  COLS_PER_CELL
        r         = _row(v)
        char_row  = height - 1 - (r // ROWS_PER_CELL)
        bit_row   = r % ROWS_PER_CELL
        grid[char_row][char_col] |= _DOT[bit_row][bit_col]

    # ── Determine if overall trend is up ──────────────────────────────────────
    up = vals[-1] >= vals[0]

    # ── Y-axis label width ────────────────────────────────────────────────────
    def _price_label(v: float) -> str:
        if v >= 1_000_000:
            return f"{v/1_000_000:.2f}M"
        if v >= 1_000:
            return f"{v:,.2f}"
        return f"{v:.2f}"

    y_width = max(len(_price_label(hi)), len(_price_label(lo)), 7)

    out = Text()

    # ── Header line ───────────────────────────────────────────────────────────
    if symbol or label:
        clr = "#00ff87" if up else "#ff5f5f"
        chg_pct = (vals[-1] - vals[0]) / vals[0] * 100 if vals[0] else 0
        sign    = "+" if chg_pct >= 0 else ""
        out.append(f"  {symbol}", style=f"bold {clr}")
        if interval:
            out.append(f"  [{interval}]", style="dim")
        out.append(f"  {_price_label(vals[-1])}", style="bold white")
        out.append(f"  {sign}{chg_pct:.2f}%\n",
                   style=f"bold {'#00ff87' if chg_pct >= 0 else '#ff5f5f'}")
        if label:
            out.append(f"  {label}\n", style="dim")
        out.append("\n")

    # ── Chart rows ────────────────────────────────────────────────────────────
    for char_row in range(height):
        # Y-axis label (top and bottom price + midpoint)
        row_frac = 1.0 - char_row / (height - 1) if height > 1 else 1.0
        price_at = lo + row_frac * rng
        if char_row == 0:
            y_lbl = _price_label(hi)
        elif char_row == height - 1:
            y_lbl = _price_label(lo)
        elif char_row == height // 2:
            y_lbl = _price_label(price_at)
        else:
            y_lbl = ""
        out.append(f"  {y_lbl:>{y_width}}  │", style="dim")

        for char_col in range(width):
            bits = grid[char_row][char_col]
            ch   = chr(BRAILLE_BASE | bits) if bits else " "
            # Colour gradient left→right
            col  = _gradient_color(char_col, width, up)
            out.append(ch, style=Style(color=col))

        out.append("\n")

    # ── X-axis ────────────────────────────────────────────────────────────────
    out.append(f"  {'':>{y_width}}  └{'─' * width}\n", style="dim")

    # ── Volume sub-strip (2 rows of volume bars beneath price chart) ───────────
    if show_vol_strip and vols and max(vols) > 0:
        max_vol = max(vols)
        vol_cells: list[float] = []
        for c in range(width):
            chunk = vols[c * COLS_PER_CELL : (c + 1) * COLS_PER_CELL]
            vol_cells.append(sum(chunk) / len(chunk) if chunk else 0.0)
        
        # Row 1: Volume bars
        out.append(f"  {'Vol':>{y_width}}  │", style="dim")
        for c in range(width):
            frac = vol_cells[c] / max_vol
            ch   = "█" if frac > 0.75 else "▇" if frac > 0.5 else "▅" if frac > 0.25 else "▂" if frac > 0.05 else " "
            v_clr = "#00d7af" if frac > 0.5 else "#008787" if frac > 0.2 else "#335555"
            out.append(ch, style=v_clr)
        out.append("\n")

    # ── Stats line ────────────────────────────────────────────────────────────
    if show_stats and vals:
        hi_v, lo_v, op_v, cl_v = max(vals), min(vals), vals[0], vals[-1]
        avg_v  = sum(vals) / len(vals)
        chg_v  = cl_v - op_v
        chg_p  = chg_v / op_v * 100 if op_v else 0
        sign   = "+" if chg_v >= 0 else ""
        c_chg  = "#00ff87" if chg_v >= 0 else "#ff5f5f"
        out.append(f"\n  open ", style="dim")
        out.append(_price_label(op_v),  style="white")
        out.append("  high ", style="dim")
        out.append(_price_label(hi_v),  style="#00ff87")
        out.append("  low ", style="dim")
        out.append(_price_label(lo_v),  style="#ff5f5f")
        out.append("  close ", style="dim")
        out.append(_price_label(cl_v),  style="bold white")
        out.append("  avg ", style="dim")
        out.append(_price_label(avg_v), style="#aaaaaa")
        out.append(f"  chg ", style="dim")
        out.append(f"{sign}{_price_label(chg_v)} ({sign}{chg_p:.2f}%)",
                   style=f"bold {c_chg}")
        if vols and max(vols) > 0:
            tot_vol = sum(vols)
            v_str = f"{tot_vol/1_000_000:.2f}M" if tot_vol >= 1_000_000 else f"{tot_vol/1_000:.1f}K" if tot_vol >= 1_000 else f"{tot_vol:.0f}"
            out.append(f"  vol ", style="dim")
            out.append(f"{v_str}\n", style="bold #00e5ff")
        else:
            out.append("\n")

    return out


# ── Bar / Pie chart helpers ───────────────────────────────────────────────────

def render_volume_bars(
    dates:   list[str],
    volumes: list[float],
    width:   int = 60,
) -> Text:
    """Render a simple horizontal bar chart of volumes as a Rich Text."""
    if not volumes:
        return Text("  — no volume data —", style="dim")
    mx = max(volumes) or 1
    out = Text()
    # Show last N bars to fit width
    n = min(len(dates), 20)
    dates   = dates[-n:]
    volumes = volumes[-n:]
    bar_w   = width - 16
    for d, v in zip(dates, volumes):
        bar_len = int(v / mx * bar_w)
        frac    = v / mx
        clr     = "#00ff87" if frac > 0.7 else "#00d7af" if frac > 0.4 else "#008787"
        out.append(f"  {d[-5:]:>5}  ", style="dim")
        out.append("█" * bar_len, style=clr)
        out.append(f"  {v:,.0f}\n", style="dim")
    return out
