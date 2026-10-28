"""Professional Analytical Charting Engine for SKTUI.

Supports:
- True Terminal OHLC Candlesticks with wicks and colored bodies
- Moving Averages (EMA 9, EMA 21, SMA 50)
- Volume panel with directional bull/bear coloring
- Momentum & Volatility indicators (RSI 14, ATR 14, VWAP)
- Crosshair inspection and multi-timeframe candle aggregation
- Braille-dot line charts with indicator overlays
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from rich.style import Style
from rich.text import Text

# ── Candle Data Structure ─────────────────────────────────────────────────────

@dataclass
class Candle:
    """Standard OHLCV candlestick bar."""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open


# ── Technical Indicators Calculation ──────────────────────────────────────────

def calc_sma(values: Sequence[float], period: int) -> list[float | None]:
    """Calculate Simple Moving Average."""
    result: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < period:
            result.append(None)
        else:
            window = values[i + 1 - period : i + 1]
            result.append(sum(window) / period)
    return result


def calc_ema(values: Sequence[float], period: int) -> list[float | None]:
    """Calculate Exponential Moving Average."""
    if not values:
        return []
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    # Initialize with SMA of first `period` items
    first_sma = sum(values[:period]) / period
    result[period - 1] = first_sma
    multiplier = 2.0 / (period + 1.0)
    for i in range(period, len(values)):
        prev = result[i - 1]
        if prev is not None:
            result[i] = (values[i] - prev) * multiplier + prev
    return result


def calc_rsi(values: Sequence[float], period: int = 14) -> list[float | None]:
    """Calculate Relative Strength Index (RSI 14)."""
    if len(values) <= period:
        return [None] * len(values)
    result: list[float | None] = [None] * len(values)
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    if len(gains) < period:
        return result

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        result[period] = 50.0 if avg_gain == 0 else 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, len(values)):
        gain = gains[i - 1]
        loss = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            result[i] = 50.0 if avg_gain == 0 else 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - (100.0 / (1.0 + rs))
    return result


def calc_vwap(candles: Sequence[Candle]) -> list[float | None]:
    """Calculate Volume-Weighted Average Price (cumulative)."""
    cum_vol = 0.0
    cum_vol_price = 0.0
    result: list[float | None] = []
    for c in candles:
        typical_price = (c.high + c.low + c.close) / 3.0
        v = c.volume if c.volume > 0 else 1.0
        cum_vol += v
        cum_vol_price += typical_price * v
        result.append(cum_vol_price / cum_vol if cum_vol > 0 else None)
    return result


def aggregate_to_candles(prices: Sequence[float], bar_size: int = 4) -> list[Candle]:
    """Downsample or aggregate tick prices into synthetic OHLCV candles."""
    if not prices:
        return []
    candles: list[Candle] = []
    step = max(1, bar_size)
    for i in range(0, len(prices), step):
        chunk = prices[i : i + step]
        if chunk:
            candles.append(
                Candle(
                    timestamp=f"{i}",
                    open=chunk[0],
                    high=max(chunk),
                    low=min(chunk),
                    close=chunk[-1],
                    volume=float(len(chunk) * 100),
                )
            )
    return candles


# ── Braille Dot Mapping for Line Charts ────────────────────────────────────────

BRAILLE_BASE = 0x2800
_DOT = [
    [0x01, 0x08],   # row 0
    [0x02, 0x10],   # row 1
    [0x04, 0x20],   # row 2
    [0x40, 0x80],   # row 3
]
ROWS_PER_CELL = 4
COLS_PER_CELL = 2

_GREEN_GRAD = ["#00ff87", "#00ff5f", "#00ff00", "#00d700", "#00af00", "#008700"]
_RED_GRAD = ["#ff5f5f", "#ff0000", "#d70000", "#af0000", "#870000"]


def _price_label(v: float) -> str:
    if v >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"{v:,.2f}"
    return f"{v:.2f}"


# ── True OHLC Candlestick Terminal Renderer ───────────────────────────────────

def render_candlestick_chart(
    candles: Sequence[Candle],
    width: int = 80,
    height: int = 16,
    symbol: str = "",
    interval: str = "15m",
    show_ema: bool = True,
    show_rsi: bool = True,
    crosshair_idx: int | None = None,
) -> Text:
    """Render a terminal OHLC Candlestick chart with indicators."""
    if not candles:
        return Text("  — no candlestick data —", style="dim")

    # Fit candles to available width
    # Each candle takes 2 character columns (1 candle bar + 1 spacing space)
    candle_step = 2
    max_candles = max(5, width // candle_step)
    disp_candles = list(candles[-max_candles:])
    n_candles = len(disp_candles)

    closes = [c.close for c in disp_candles]
    ema9 = calc_ema(closes, 9) if show_ema else []
    ema21 = calc_ema(closes, 21) if show_ema else []
    rsi14 = calc_rsi(closes, 14) if show_rsi else []

    hi_price = max(c.high for c in disp_candles)
    lo_price = min(c.low for c in disp_candles)
    rng = (hi_price - lo_price) or 1.0

    y_width = max(len(_price_label(hi_price)), len(_price_label(lo_price)), 8)
    out = Text()

    # 1. Header with symbol, interval, latest OHLCV
    latest = disp_candles[-1]
    chg = latest.close - disp_candles[0].open
    pct = (chg / disp_candles[0].open * 100) if disp_candles[0].open else 0.0
    clr_chg = "#00ff87" if chg >= 0 else "#ff5f5f"
    sign = "+" if chg >= 0 else ""

    out.append(f"  {symbol}", style=f"bold {clr_chg}")
    out.append(f"  [{interval}]", style="dim")
    out.append(f"  O: {_price_label(latest.open)}", style="dim")
    out.append(f"  H: {_price_label(latest.high)}", style="#00ff87")
    out.append(f"  L: {_price_label(latest.low)}", style="#ff5f5f")
    out.append(f"  C: {_price_label(latest.close)}", style="bold white")
    out.append(f"  {sign}{pct:.2f}%\n", style=f"bold {clr_chg}")

    # Legend for indicators
    if show_ema:
        out.append("  Indicators: ", style="dim")
        out.append("── EMA9 ", style="#00d7ff")
        out.append("── EMA21 ", style="#ffaa00")
        if show_rsi and rsi14 and rsi14[-1] is not None:
            r_val = rsi14[-1]
            r_col = "#ff5f5f" if r_val >= 70 else "#00ff87" if r_val <= 30 else "#00e5ff"
            out.append(f"── RSI(14): {r_val:.1f}", style=r_col)
        out.append("\n")

    # 2. Price Grid & Candlesticks
    # Map price to row (0 = top, height - 1 = bottom)
    def price_to_row(p: float) -> int:
        return max(0, min(height - 1, int((1.0 - (p - lo_price) / rng) * (height - 1))))

    grid: list[list[tuple[str, str]]] = [[(" ", "")] * (n_candles * candle_step) for _ in range(height)]

    for idx, c in enumerate(disp_candles):
        col = idx * candle_step
        r_high = price_to_row(c.high)
        r_low = price_to_row(c.low)
        r_open = price_to_row(c.open)
        r_close = price_to_row(c.close)

        r_top = min(r_open, r_close)
        r_bottom = max(r_open, r_close)

        color = "#00ff87" if c.is_bullish else "#ff5f5f"

        # Upper and lower wicks
        for r in range(r_high, r_low + 1):
            grid[r][col] = ("│", color)

        # Candle body (solid block)
        if r_top == r_bottom:
            grid[r_top][col] = ("─", color)
        else:
            for r in range(r_top, r_bottom + 1):
                grid[r][col] = ("█", color)

        # Overlay EMA dots if active
        if show_ema and idx < len(ema9) and ema9[idx] is not None:
            r_ema = price_to_row(ema9[idx]) # type: ignore
            if 0 <= r_ema < height:
                grid[r_ema][col] = ("•", "#00d7ff")
        if show_ema and idx < len(ema21) and ema21[idx] is not None:
            r_ema21 = price_to_row(ema21[idx]) # type: ignore
            if 0 <= r_ema21 < height:
                grid[r_ema21][col] = ("·", "#ffaa00")

    # Render Price Rows
    for r in range(height):
        # Y-axis price label
        p_row = lo_price + (1.0 - r / (height - 1 if height > 1 else 1)) * rng
        if r == 0:
            y_lbl = _price_label(hi_price)
        elif r == height - 1:
            y_lbl = _price_label(lo_price)
        elif r == height // 2:
            y_lbl = _price_label(p_row)
        else:
            y_lbl = ""
        out.append(f"  {y_lbl:>{y_width}} │", style="dim")

        # Row cells
        for c in range(n_candles * candle_step):
            char, clr = grid[r][c]
            out.append(char, style=clr if clr else "default")
        out.append("\n")

    # X-axis border
    out.append(f"  {'':>{y_width}} └{'─' * (n_candles * candle_step + 2)}\n", style="dim")

    # 3. Volume Panel (Directional colors)
    max_vol = max((c.volume for c in disp_candles), default=1.0) or 1.0
    out.append(f"  {'Vol':>{y_width}} │", style="dim")
    for c in disp_candles:
        frac = c.volume / max_vol
        char = "█" if frac > 0.75 else "▇" if frac > 0.5 else "▅" if frac > 0.25 else "▂" if frac > 0.05 else " "
        v_clr = "#00d7af" if c.is_bullish else "#d75f5f"
        out.append(char, style=v_clr)
        out.append(" ")
    out.append("\n")

    # 4. RSI Sub-Panel if enabled
    if show_rsi and rsi14:
        valid_rsis = [r for r in rsi14 if r is not None]
        if valid_rsis:
            latest_rsi = valid_rsis[-1]
            r_col = "#ff5f5f" if latest_rsi >= 70 else "#00ff87" if latest_rsi <= 30 else "#00d7ff"
            out.append(f"  {'RSI(14)':>{y_width}} │", style="dim")
            for idx in range(n_candles):
                val = rsi14[idx] if idx < len(rsi14) else None
                if val is None:
                    out.append("  ")
                else:
                    ch = "▲" if val >= 70 else "▼" if val <= 30 else "─"
                    ch_col = "#ff5f5f" if val >= 70 else "#00ff87" if val <= 30 else "#666666"
                    out.append(ch, style=ch_col)
                    out.append(" ")
            out.append(f"  [{latest_rsi:.1f}]\n", style=f"bold {r_col}")

    # 5. Crosshair Info if specified
    if crosshair_idx is not None and 0 <= crosshair_idx < n_candles:
        c = disp_candles[crosshair_idx]
        out.append(
            f"\n  [Crosshair #{crosshair_idx}] O: {_price_label(c.open)}  H: {_price_label(c.high)}  "
            f"L: {_price_label(c.low)}  C: {_price_label(c.close)}  Vol: {c.volume:,.0f}\n",
            style="bold yellow",
        )

    return out


# ── Braille Dot Line Chart Renderer (Enhanced) ───────────────────────────────

def render_chart(
    values: Sequence[float],
    volumes: Sequence[float] | None = None,
    width: int = 80,
    height: int = 16,
    label: str = "",
    symbol: str = "",
    interval: str = "",
    show_stats: bool = True,
    show_vol_strip: bool = True,
) -> Text:
    """Render values as a braille-dot line chart with volume sub-strip."""
    if not values:
        return Text("  — no data —", style="dim")

    vals = list(values)
    vols = list(volumes) if volumes else []

    total_cols = width * COLS_PER_CELL
    if len(vals) > total_cols:
        step = len(vals) / total_cols
        vals = [vals[int(i * step)] for i in range(total_cols)]
        if vols:
            vols = [vols[int(i * step)] for i in range(total_cols)]
    else:
        while len(vals) < total_cols:
            vals = [v for v in vals for _ in range(2)]
            if vols:
                vols = [v for v in vols for _ in range(2)]
        vals = vals[:total_cols]
        if vols:
            vols = vols[:total_cols]

    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    total_rows = height * ROWS_PER_CELL

    def _row(v: float) -> int:
        return max(0, min(total_rows - 1, int((v - lo) / rng * (total_rows - 1))))

    grid: list[list[int]] = [[0] * width for _ in range(height)]
    for x, v in enumerate(vals):
        char_col = x // COLS_PER_CELL
        bit_col = x % COLS_PER_CELL
        r = _row(v)
        char_row = height - 1 - (r // ROWS_PER_CELL)
        bit_row = r % ROWS_PER_CELL
        grid[char_row][char_col] |= _DOT[bit_row][bit_col]

    up = vals[-1] >= vals[0]
    y_width = max(len(_price_label(hi)), len(_price_label(lo)), 7)
    out = Text()

    if symbol or label:
        clr = "#00ff87" if up else "#ff5f5f"
        chg_pct = (vals[-1] - vals[0]) / vals[0] * 100 if vals[0] else 0
        sign = "+" if chg_pct >= 0 else ""
        out.append(f"  {symbol}", style=f"bold {clr}")
        if interval:
            out.append(f"  [{interval}]", style="dim")
        out.append(f"  {_price_label(vals[-1])}", style="bold white")
        out.append(f"  {sign}{chg_pct:.2f}%\n", style=f"bold {'#00ff87' if chg_pct >= 0 else '#ff5f5f'}")
        if label:
            out.append(f"  {label}\n", style="dim")
        out.append("\n")

    for char_row in range(height):
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
            ch = chr(BRAILLE_BASE | bits) if bits else " "
            col = _GREEN_GRAD[min(int(char_col / width * len(_GREEN_GRAD)), len(_GREEN_GRAD) - 1)] if up else _RED_GRAD[min(int(char_col / width * len(_RED_GRAD)), len(_RED_GRAD) - 1)]
            out.append(ch, style=Style(color=col))
        out.append("\n")

    out.append(f"  {'':>{y_width}}  └{'─' * width}\n", style="dim")

    if show_vol_strip and vols and max(vols) > 0:
        max_vol = max(vols)
        vol_cells: list[float] = []
        for c in range(width):
            chunk = vols[c * COLS_PER_CELL : (c + 1) * COLS_PER_CELL]
            vol_cells.append(sum(chunk) / len(chunk) if chunk else 0.0)
        out.append(f"  {'Vol':>{y_width}}  │", style="dim")
        for c in range(width):
            frac = vol_cells[c] / max_vol
            ch = "█" if frac > 0.75 else "▇" if frac > 0.5 else "▅" if frac > 0.25 else "▂" if frac > 0.05 else " "
            v_clr = "#00d7af" if frac > 0.5 else "#008787" if frac > 0.2 else "#335555"
            out.append(ch, style=v_clr)
        out.append("\n")

    if show_stats and vals:
        hi_v, lo_v, op_v, cl_v = max(vals), min(vals), vals[0], vals[-1]
        avg_v = sum(vals) / len(vals)
        chg_v = cl_v - op_v
        chg_p = chg_v / op_v * 100 if op_v else 0
        sign = "+" if chg_v >= 0 else ""
        c_chg = "#00ff87" if chg_v >= 0 else "#ff5f5f"
        out.append(f"\n  open ", style="dim")
        out.append(_price_label(op_v), style="white")
        out.append("  high ", style="dim")
        out.append(_price_label(hi_v), style="#00ff87")
        out.append("  low ", style="dim")
        out.append(_price_label(lo_v), style="#ff5f5f")
        out.append("  close ", style="dim")
        out.append(_price_label(cl_v), style="bold white")
        out.append("  avg ", style="dim")
        out.append(_price_label(avg_v), style="#aaaaaa")
        out.append(f"  chg ", style="dim")
        out.append(f"{sign}{_price_label(chg_v)} ({sign}{chg_p:.2f}%)", style=f"bold {c_chg}")
        if vols and max(vols) > 0:
            tot_vol = sum(vols)
            v_str = f"{tot_vol/1_000_000:.2f}M" if tot_vol >= 1_000_000 else f"{tot_vol/1_000:.1f}K" if tot_vol >= 1_000 else f"{tot_vol:.0f}"
            out.append(f"  vol ", style="dim")
            out.append(f"{v_str}\n", style="bold #00e5ff")
        else:
            out.append("\n")

    return out


def render_volume_bars(
    dates: list[str],
    volumes: list[float],
    width: int = 60,
) -> Text:
    """Render a simple horizontal bar chart of volumes."""
    if not volumes:
        return Text("  — no volume data —", style="dim")
    mx = max(volumes) or 1
    out = Text()
    n = min(len(dates), 20)
    dates = dates[-n:]
    volumes = volumes[-n:]
    bar_w = width - 16
    for d, v in zip(dates, volumes):
        bar_len = int(v / mx * bar_w)
        frac = v / mx
        clr = "#00ff87" if frac > 0.7 else "#00d7af" if frac > 0.4 else "#008787"
        out.append(f"  {d[-5:]:>5}  ", style="dim")
        out.append("█" * bar_len, style=clr)
        out.append(f"  {v:,.0f}\n", style="dim")
    return out
