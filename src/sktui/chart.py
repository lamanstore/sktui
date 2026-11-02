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
    """Standard OHLCV candlestick bar.

    ``ts`` is the optional epoch-seconds start of the bar's time bucket; it is
    used by the real-time engine to roll over forming candles accurately.
    """
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    ts: float = 0.0

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open


class ChartText(Text):
    """Rich ``Text`` carrying ``_chart_meta`` (grid geometry for mouse mapping)."""

    _chart_meta: dict


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


# ── Real-time candle helpers ──────────────────────────────────────────────────

def _bucket_label(epoch: float, interval_sec: int) -> str:
    from datetime import datetime
    dt = datetime.fromtimestamp(epoch)
    if interval_sec < 60:
        return dt.strftime("%H:%M:%S")
    if interval_sec < 86400:
        return dt.strftime("%H:%M")
    return dt.strftime("%Y-%m-%d")


def compress_candles(candles: Sequence[Candle], target_bars: int) -> list[Candle]:
    """Aggregate *candles* into at most *target_bars* bars, preserving OHLCV.

    Each group keeps the first open, the max high, the min low, the last close
    and the summed volume — so wicks/extremes are never lost when zooming out.
    """
    n = len(candles)
    if target_bars <= 0 or n <= target_bars:
        return list(candles)
    out: list[Candle] = []
    for g in range(target_bars):
        a = (g * n) // target_bars
        b = ((g + 1) * n) // target_bars
        chunk = candles[a:b]
        if not chunk:
            continue
        out.append(Candle(
            timestamp=chunk[0].timestamp,
            open=chunk[0].open,
            high=max(c.high for c in chunk),
            low=min(c.low for c in chunk),
            close=chunk[-1].close,
            volume=sum(c.volume for c in chunk),
            ts=chunk[0].ts,
        ))
    return out


def merge_live_tick_into_candles(
    candles: list[Candle],
    ltp: float,
    vol_delta: float,
    interval_sec: int,
    now_ts: float | None = None,
    max_len: int = 5000,
) -> tuple[list[Candle], float]:
    """Merge a live tick into *candles* in place.

    Updates the forming right-edge candle, or appends a new one when the
    wall-clock bucket ``int(now_ts // interval_sec)`` advances. ``interval_sec
    <= 0`` (TICK chart) appends one bar per tick.

    Returns ``(candles, seconds_remaining_in_bar)``.
    """
    import time as _time
    now = _time.time() if now_ts is None else now_ts
    if interval_sec <= 0:
        prev = candles[-1].close if candles else ltp
        candles.append(Candle(
            timestamp=_bucket_label(now, 1), open=prev,
            high=max(prev, ltp), low=min(prev, ltp), close=ltp,
            volume=vol_delta, ts=now,
        ))
        if len(candles) > max_len:
            del candles[: len(candles) - max_len]
        return candles, 0.0

    bucket = int(now // interval_sec)
    remaining = interval_sec - (now - bucket * interval_sec)
    if candles:
        last = candles[-1]
        if last.ts <= 0:
            # Unknown bucket (e.g. unparsable REST timestamp): adopt current bucket
            last.ts = float(bucket * interval_sec)
        last_bucket = int(last.ts // interval_sec)
        if bucket <= last_bucket:
            last.high = max(last.high, ltp)
            last.low = min(last.low, ltp)
            last.close = ltp
            last.volume += vol_delta
            return candles, remaining
    start = float(bucket * interval_sec)
    candles.append(Candle(
        timestamp=_bucket_label(start, interval_sec),
        open=ltp, high=ltp, low=ltp, close=ltp, volume=vol_delta, ts=start,
    ))
    if len(candles) > max_len:
        del candles[: len(candles) - max_len]
    return candles, remaining


@dataclass
class Viewport:
    """Visible slice of a series plus the column density used to draw it."""
    start: int
    end: int
    step: int          # terminal columns per bar (1 = dense)
    compress_to: int   # >0 when the slice is OHLCV-compressed to this many bars
    pan: int           # bars scrolled back from the live (right) edge

    @property
    def span(self) -> int:
        return self.end - self.start


def compute_viewport(
    n_total: int,
    plot_w: int,
    zoom_bars: int | None = None,
    pan_offset: int = 0,
    fit_all: bool = False,
) -> Viewport:
    """Choose the visible window and density for *n_total* bars in *plot_w* cols.

    * ``fit_all`` shows every bar (compressing when needed).
    * ``zoom_bars`` beyond ``plot_w`` compresses instead of being clamped, so
      zooming out always works.
    * Few bars are spread out (2–6 cols each) so zooming in widens candles.
    """
    plot_w = max(4, plot_w)
    comfy = max(5, plot_w // 2)
    if n_total <= 0:
        return Viewport(0, 0, 2, 0, 0)
    if fit_all:
        bars, pan = n_total, 0
    else:
        bars = zoom_bars if zoom_bars and zoom_bars > 0 else comfy
        bars = min(max(5, bars), n_total)
        pan = max(0, min(int(pan_offset or 0), n_total - bars))
    end = n_total - pan
    start = max(0, end - bars)
    span = end - start
    if span <= comfy:
        step, comp = max(2, min(6, plot_w // max(1, span))), 0
    elif span <= plot_w:
        step, comp = 1, 0
    else:
        step, comp = 1, plot_w
    return Viewport(start, end, step, comp, pan)


def step_zoom(cur_bars: int, n_total: int, direction: int, min_bars: int = 8) -> int:
    """Next visible-bar count for a zoom step (−1 = in, +1 = out), ~30% per step.

    Zooming out is bounded only by *n_total*, so the whole series is reachable.
    """
    cur_bars = max(1, int(cur_bars))
    if direction < 0:
        new = int(cur_bars * 0.7)
    else:
        new = int(math.ceil(cur_bars / 0.7)) + 1
    return max(min(min_bars, n_total), min(max(1, n_total), new))


def _ts_short(s: str) -> str:
    s = str(s or "").strip()
    if "T" in s and len(s) > 10:
        s = s.split("T", 1)[1]
    elif " " in s:
        s = s.split(" ")[-1]
    return s[:8]


def _compact_vol(v: float) -> str:
    if v >= 10_000_000:
        return f"{v/10_000_000:.2f}Cr"
    if v >= 100_000:
        return f"{v/100_000:.2f}L"
    if v >= 1_000:
        return f"{v/1_000:.1f}K"
    return f"{v:.0f}"


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

_VOL_BLOCKS = " ▁▂▃▄▅▆▇█"


def chart_chrome_rows(
    show_rsi: bool = True,
    show_volume: bool = True,
    compact_header: bool = False,
    crosshair: bool = False,
    total_height: int = 30,
) -> tuple[int, int]:
    """Return ``(non_grid_rows, volume_rows)`` used by the candlestick layout."""
    vol_rows = 0
    if show_volume:
        vol_rows = 3 if total_height >= 36 else 2 if total_height >= 22 else 1
    rows = 1 + (0 if compact_header else 1) + 2 + vol_rows + (1 if show_rsi else 0) + 1
    rows += 1 if crosshair else 0
    return rows, vol_rows


def render_candlestick_chart(
    candles: Sequence[Candle],
    width: int = 80,
    height: int = 16,
    symbol: str = "",
    interval: str = "15m",
    show_ema: bool = True,
    show_rsi: bool = True,
    show_vwap: bool = True,
    show_sr: bool = True,
    compare_symbol: str = "",
    compare_closes: Sequence[float] | None = None,
    zoom_bars: int | None = None,
    crosshair_idx: int | None = None,
    pan_offset: int = 0,
    fit_all: bool = False,
    crosshair_price: float | None = None,
    show_volume: bool = True,
    live_ltp: float | None = None,
    pos_price: float | None = None,
    pos_qty: int = 0,
    bar_countdown_sec: float | None = None,
    compact_header: bool = False,
    total_height: int | None = None,
    status_note: str = "",
) -> Text:
    """Render a full-viewport terminal OHLC candlestick chart.

    ``width`` is the total text width available.  ``height`` is the number of
    price-grid rows, unless ``total_height`` is given, in which case the grid
    expands to fill all remaining rows after header/axis/volume/RSI chrome.

    ``crosshair_idx`` is relative to the visible window.  The returned text
    carries ``_chart_meta`` describing the grid so mouse clicks can be mapped
    back to ``(bar index, price)``.
    """
    if not candles:
        return Text("  — no candlestick data —", style="dim")

    from sktui.themes import current_palette
    pal = current_palette()

    all_c = list(candles)
    n_all = len(all_c)
    glob_hi = max(c.high for c in all_c)
    glob_lo = min(c.low for c in all_c)
    y_width = max(len(_price_label(glob_hi)), len(_price_label(glob_lo)), 7)
    gutter_w = y_width + 2
    plot_x0 = 2 + y_width + 2
    plot_w = max(10, width - plot_x0 - gutter_w)

    vp = compute_viewport(n_all, plot_w, zoom_bars, pan_offset, fit_all)

    # ── Indicator source series (full history unless compressed) ─────────────
    if vp.compress_to:
        disp = compress_candles(all_c[vp.start:vp.end], vp.compress_to)
        src, s0 = disp, 0
    else:
        src, s0 = all_c, vp.start
        disp = all_c[vp.start:vp.end]
    n_disp = len(disp)
    step = vp.step
    c_off = 0 if step <= 2 else step // 2
    body_half = 1 if step >= 4 else 0

    src_closes = [c.close for c in src]

    def _win(series: list[float | None]) -> list[float | None]:
        return series[s0:s0 + n_disp] if series else []

    ema9 = _win(calc_ema(src_closes, 9)) if show_ema else []
    sma20 = _win(calc_sma(src_closes, 20)) if show_ema else []
    ema21 = _win(calc_ema(src_closes, 21)) if show_ema else []
    vwap_vals = _win(calc_vwap(src)) if show_vwap else []
    rsi14 = _win(calc_rsi(src_closes, 14)) if show_rsi else []

    highs = [c.high for c in disp]
    lows = [c.low for c in disp]
    from sktui.services.indicators import support_resistance
    res_levels, sup_levels = (
        support_resistance(highs, lows, window=3) if show_sr and n_disp >= 7 else ([], [])
    )

    # ── Layout rows ──────────────────────────────────────────────────────────
    xh_active = crosshair_idx is not None and 0 <= crosshair_idx < n_disp
    if total_height is not None:
        chrome, vol_rows = chart_chrome_rows(
            show_rsi, show_volume, compact_header, xh_active, total_height,
        )
        grid_h = max(4, total_height - chrome)
    else:
        grid_h = max(4, height)
        vol_rows = 1 if show_volume else 0

    # ── Price range with breathing room ─────────────────────────────────────
    hi_price = max(highs)
    lo_price = min(lows)
    span_p = hi_price - lo_price
    pad = span_p * 0.06 if span_p > 0 else max(abs(hi_price) * 0.002, 0.05)
    hi_p = hi_price + pad
    lo_p = lo_price - pad
    rng = (hi_p - lo_p) or 1.0

    def price_to_row(p: float) -> int:
        return max(0, min(grid_h - 1, int(round((hi_p - p) / rng * (grid_h - 1)))))

    def row_to_price(r: int) -> float:
        return hi_p - (r / max(1, grid_h - 1)) * rng

    def in_range(p: float | None) -> bool:
        return p is not None and lo_p <= p <= hi_p

    out = ChartText(no_wrap=True, overflow="crop")
    lines = 0

    # ── 1. Header ────────────────────────────────────────────────────────────
    latest = disp[-1]
    first_open = disp[0].open
    chg = latest.close - first_open
    pct = (chg / first_open * 100) if first_open else 0.0
    clr_chg = pal.bull if chg >= 0 else pal.bear
    sign = "+" if chg >= 0 else ""

    out.append(f"  {symbol}", style=f"bold {clr_chg}")
    out.append(f"  [{interval}]", style=f"bold {pal.primary}")
    out.append(f"  O {_price_label(latest.open)}", style=pal.muted)
    out.append(f"  H {_price_label(latest.high)}", style=pal.bull)
    out.append(f"  L {_price_label(latest.low)}", style=pal.bear)
    out.append(f"  C {_price_label(latest.close)}", style=f"bold {pal.fg_strong}")
    out.append(f"  {sign}{pct:.2f}%", style=f"bold {clr_chg}")
    if compare_closes and len(compare_closes) >= 2:
        c_slice = list(compare_closes[-n_disp:]) if len(compare_closes) >= n_disp else list(compare_closes)
        if c_slice and c_slice[0] > 0:
            bench_pct = (c_slice[-1] - c_slice[0]) / c_slice[0] * 100.0
            rel_alpha = pct - bench_pct
            b_lbl = compare_symbol or "NIFTY50"
            a_sign = "+" if rel_alpha >= 0 else ""
            a_clr = pal.bull if rel_alpha >= 0 else pal.bear
            out.append(f"  │ vs {b_lbl}: {bench_pct:+.2f}% (α {a_sign}{rel_alpha:.2f}%)", style=a_clr)
    if bar_countdown_sec is not None and bar_countdown_sec > 0:
        out.append(f"  ⏱ {bar_countdown_sec:04.1f}s", style=f"bold {pal.warn}")
    if vp.pan == 0 and not fit_all:
        out.append("  ● LIVE", style=f"bold {pal.bull}")
    out.append("\n")
    lines += 1

    # Legend for indicators & S/R zones
    if not compact_header:
        out.append("  ", style=pal.subtle)
        if show_ema:
            out.append("━ EMA9 ", style=pal.primary)
            out.append("━ SMA20 ", style=pal.secondary)
            out.append("━ EMA21 ", style=pal.warn)
        if show_vwap and vwap_vals and vwap_vals[-1] is not None:
            out.append(f"━ VWAP {_price_label(vwap_vals[-1])} ", style=pal.teal)
        if show_rsi and rsi14 and rsi14[-1] is not None:
            r_val = rsi14[-1]
            r_col = pal.bear if r_val >= 70 else pal.bull if r_val <= 30 else pal.primary
            out.append(f"━ RSI14 {r_val:.1f} ", style=r_col)
        if sup_levels:
            out.append(f"┈ Sup {_price_label(sup_levels[0])} ", style=pal.bull)
        if res_levels:
            out.append(f"┈ Res {_price_label(res_levels[-1])} ", style=pal.bear)
        if pos_price and pos_qty:
            out.append(f"═ Pos {pos_qty:+d} @ {_price_label(pos_price)}", style=pal.accent)
        out.append("\n")
        lines += 1

    grid_row0 = lines

    # ── 2. Grid construction ─────────────────────────────────────────────────
    EMPTY = (" ", "")
    grid: list[list[tuple[str, str]]] = [[EMPTY] * plot_w for _ in range(grid_h)]
    soft = {" ", "·", "┈", "═"}

    def put(r: int, c: int, ch: str, st: str, force: bool = True) -> None:
        if 0 <= r < grid_h and 0 <= c < plot_w:
            if force or grid[r][c][0] in soft:
                grid[r][c] = (ch, st)

    label_rows = set(range(0, grid_h, 4)) | {grid_h - 1}
    for r in label_rows:
        for c in range(0, plot_w, 3):
            put(r, c, "·", pal.divider)

    if show_sr:
        for s_lvl in sup_levels[:1]:
            rs = price_to_row(s_lvl)
            for c in range(0, plot_w, 2):
                put(rs, c, "┈", pal.bull_grad[-1])
        for r_lvl in res_levels[-1:]:
            rr = price_to_row(r_lvl)
            for c in range(0, plot_w, 2):
                put(rr, c, "┈", pal.bear_grad[-1])

    pos_row = price_to_row(pos_price) if (pos_price and pos_qty and in_range(pos_price)) else None
    if pos_row is not None:
        for c in range(plot_w):
            put(pos_row, c, "═", pal.accent)

    ltp_val = live_ltp if live_ltp is not None else (all_c[-1].close if vp.pan == 0 else None)
    ltp_clr = pal.bull if all_c[-1].close >= all_c[-1].open else pal.bear
    ltp_row = price_to_row(ltp_val) if in_range(ltp_val) else None
    if ltp_row is not None:
        for c in range(plot_w):
            put(ltp_row, c, "┈", ltp_clr)

    def col_of(i: int) -> int:
        return i * step + c_off

    for idx, c in enumerate(disp):
        col = col_of(idx)
        if col >= plot_w:
            break
        r_high = price_to_row(c.high)
        r_low = price_to_row(c.low)
        r_top = price_to_row(max(c.open, c.close))
        r_bot = price_to_row(min(c.open, c.close))
        color = pal.bull if c.is_bullish else pal.bear
        for r in range(r_high, r_low + 1):
            put(r, col, "│", color)
        if r_top == r_bot:
            body = "━" if body_half else ("─" if c.close == c.open else "■")
            for dc in range(-body_half, body_half + 1):
                put(r_top, col + dc, body, color)
        else:
            body = "█" if c.is_bullish else "█"
            for r in range(r_top, r_bot + 1):
                for dc in range(-body_half, body_half + 1):
                    put(r, col + dc, body, color)

    # Indicator overlays (only on empty / soft cells so candles stay readable)
    def overlay(series: list[float | None], ch: str, st: str) -> None:
        for i, v in enumerate(series):
            if v is None:
                continue
            col = col_of(i)
            put(price_to_row(v), col, ch, st, force=False)
            if step >= 2 and i + 1 < len(series) and series[i + 1] is not None:
                for k in range(1, step):
                    vv = v + (series[i + 1] - v) * k / step  # type: ignore[operator]
                    put(price_to_row(vv), col + k, ch, st, force=False)

    if show_vwap:
        overlay(vwap_vals, "∘", pal.teal)
    if show_ema:
        overlay(sma20, "∙", pal.secondary)
        overlay(ema21, "·", pal.warn)
        overlay(ema9, "•", pal.primary)

    # ── 2D crosshair ─────────────────────────────────────────────────────────
    xh_row: int | None = None
    xh_col: int | None = None
    xh_px: float | None = None
    if xh_active:
        xc = disp[crosshair_idx]  # type: ignore[index]
        xh_col = col_of(crosshair_idx)  # type: ignore[arg-type]
        xh_px = crosshair_price if crosshair_price is not None else xc.close
        xh_row = price_to_row(xh_px)
        for r in range(grid_h):
            ch, st = grid[r][xh_col] if xh_col < plot_w else EMPTY
            if ch in soft:
                put(r, xh_col, "┆", pal.warn)
            else:
                put(r, xh_col, ch, f"{st or pal.fg} on {pal.primary_tint}")
        for c in range(plot_w):
            put(xh_row, c, "┄", pal.warn, force=False)
        put(xh_row, xh_col, "┼", f"bold {pal.warn}")
    elif crosshair_price is not None and in_range(crosshair_price):
        xh_px = crosshair_price
        xh_row = price_to_row(crosshair_price)
        for c in range(plot_w):
            put(xh_row, c, "┄", pal.warn, force=False)

    # ── Right gutter tags ────────────────────────────────────────────────────
    gutter: dict[int, tuple[str, str]] = {}
    if pos_row is not None:
        gutter[pos_row] = (f" E{_price_label(pos_price)}", f"bold {pal.accent}")  # type: ignore[arg-type]
    if ltp_row is not None and ltp_val is not None:
        gutter[ltp_row] = (f"◀{_price_label(ltp_val)} ", f"bold {pal.on_bull if ltp_clr == pal.bull else pal.on_bear} on {ltp_clr}")
        if bar_countdown_sec is not None and bar_countdown_sec > 0:
            cd_row = ltp_row + 1 if ltp_row + 1 < grid_h else ltp_row - 1
            if cd_row not in gutter:
                gutter[cd_row] = (f" ⏱{bar_countdown_sec:04.1f}s", pal.warn)
    elif ltp_val is not None and vp.pan == 0:
        edge = 0 if ltp_val > hi_p else grid_h - 1
        arrow = "▲" if ltp_val > hi_p else "▼"
        gutter[edge] = (f"{arrow}{_price_label(ltp_val)}", f"bold {ltp_clr}")

    # ── 3. Emit grid rows ────────────────────────────────────────────────────
    for r in range(grid_h):
        if r == xh_row and xh_px is not None:
            out.append(" ")
            out.append(f"{_price_label(xh_px):>{y_width + 1}}", style=f"bold {pal.on_warn} on {pal.warn}")
            out.append(" ┤", style=pal.subtle)
        elif r in label_rows:
            out.append(f"  {_price_label(row_to_price(r)):>{y_width}} ┤", style=pal.subtle)
        else:
            out.append(f"  {'':>{y_width}} │", style=pal.subtle)
        row = grid[r]
        # Batch identical-style runs for speed
        run_ch: list[str] = []
        run_st = row[0][1] if row else ""
        for ch, st in row:
            if st != run_st:
                out.append("".join(run_ch), style=run_st or None)
                run_ch, run_st = [], st
            run_ch.append(ch)
        if run_ch:
            out.append("".join(run_ch), style=run_st or None)
        g = gutter.get(r)
        if g:
            out.append(g[0][:gutter_w], style=g[1])
        out.append("\n")
        lines += 1

    # ── 4. X-axis + time ruler ───────────────────────────────────────────────
    axis = ["─"] * plot_w
    labels = [" "] * plot_w
    min_gap = max(10, len(_ts_short(disp[-1].timestamp)) + 3)
    last_end = -min_gap
    every = max(1, (min_gap + step - 1) // step)
    for i in range(0, n_disp, every):
        col = col_of(i)
        lbl = _ts_short(disp[i].timestamp)
        if not lbl or col >= plot_w:
            continue
        a = max(0, col - len(lbl) // 2)
        if a < last_end + 2 or a + len(lbl) > plot_w:
            continue
        axis[col] = "┬"
        for k, ch in enumerate(lbl):
            labels[a + k] = ch
        last_end = a + len(lbl)
    if xh_col is not None and xh_col < plot_w:
        axis[xh_col] = "▲"
    out.append(f"  {'':>{y_width}} └{''.join(axis)}\n", style=pal.subtle)
    out.append(f"  {'':>{y_width}}  {''.join(labels)}\n", style=pal.muted)
    lines += 2

    # ── 5. Volume panel (multi-row, eighth-block precision) ─────────────────
    if vol_rows:
        max_vol = max((c.volume for c in disp), default=0.0) or 1.0
        levels = [c.volume / max_vol * vol_rows * 8 for c in disp]
        for vr in range(vol_rows - 1, -1, -1):
            lbl = "Vol" if vr == vol_rows - 1 else ""
            out.append(f"  {lbl:>{y_width}} │", style=pal.subtle)
            cells = [(" ", "")] * plot_w
            for i, c in enumerate(disp):
                col = col_of(i)
                if col >= plot_w:
                    break
                fill = max(0, min(8, int(round(levels[i] - vr * 8))))
                ch = _VOL_BLOCKS[fill]
                st = pal.bull if c.is_bullish else pal.bear
                if xh_active and i != crosshair_idx:
                    st = pal.subtle if fill else st
                for dc in range(-body_half, body_half + 1):
                    if 0 <= col + dc < plot_w:
                        cells[col + dc] = (ch, st)
            for ch, st in cells:
                out.append(ch, style=st or None)
            if vr == 0:
                out.append(f" {_compact_vol(latest.volume)}", style=pal.muted)
            out.append("\n")
            lines += 1

    # ── 6. RSI strip ─────────────────────────────────────────────────────────
    if show_rsi:
        valid_rsis = [r for r in rsi14 if r is not None]
        out.append(f"  {'RSI(14)':>{y_width}} │", style=pal.subtle)
        cells = [(" ", "")] * plot_w
        for i in range(n_disp):
            val = rsi14[i] if i < len(rsi14) else None
            col = col_of(i)
            if val is None or col >= plot_w:
                continue
            ch = "▲" if val >= 70 else "▼" if val <= 30 else "─"
            cells[col] = (ch, pal.bear if val >= 70 else pal.bull if val <= 30 else pal.subtle)
        for ch, st in cells:
            out.append(ch, style=st or None)
        if valid_rsis:
            lr = valid_rsis[-1]
            r_col = pal.bear if lr >= 70 else pal.bull if lr <= 30 else pal.primary
            out.append(f" [{lr:.1f}]", style=f"bold {r_col}")
        out.append("\n")
        lines += 1

    # ── 7. Viewport minimap / status ────────────────────────────────────────
    tw = max(10, min(32, plot_w // 3))
    a = int(vp.start / n_all * tw)
    b = max(a + 1, int(math.ceil(vp.end / n_all * tw)))
    out.append(f"  {'':>{y_width}}  ", style=pal.subtle)
    out.append(f"Bars {vp.start + 1}–{vp.end}/{n_all} ", style=pal.muted)
    out.append("━" * a, style=pal.divider)
    out.append("█" * (b - a), style=pal.primary)
    out.append("━" * (tw - b), style=pal.divider)
    if fit_all:
        out.append("  ⤢ FIT ALL", style=f"bold {pal.accent}")
    elif vp.pan == 0:
        out.append("  ● LIVE", style=f"bold {pal.bull}")
    else:
        out.append(f"  ◀ {vp.pan} bars back · End=live", style=f"bold {pal.warn}")
    if vp.compress_to:
        out.append(f"  ×{vp.span / max(1, n_disp):.1f} bars/col", style=pal.muted)
    if status_note:
        out.append(f"  {status_note}", style=pal.muted)
    out.append("\n")
    lines += 1

    # ── 8. Crosshair inspector ───────────────────────────────────────────────
    if xh_active:
        c = disp[crosshair_idx]  # type: ignore[index]
        c_chg = (c.close - c.open) / c.open * 100 if c.open else 0.0
        out.append(f"  ┼ {_ts_short(c.timestamp) or crosshair_idx}", style=f"bold {pal.warn}")
        out.append(f"  O {_price_label(c.open)}", style=pal.muted)
        out.append(f"  H {_price_label(c.high)}", style=pal.bull)
        out.append(f"  L {_price_label(c.low)}", style=pal.bear)
        out.append(f"  C {_price_label(c.close)}", style=f"bold {pal.fg_strong}")
        out.append(f"  {c_chg:+.2f}%", style=pal.bull if c_chg >= 0 else pal.bear)
        out.append(f"  Vol {_compact_vol(c.volume)}", style=pal.muted)
        if xh_px is not None and ltp_val:
            d = xh_px - ltp_val
            out.append(
                f"  │ ⌖ {_price_label(xh_px)}  Δ {d:+.2f} ({d / ltp_val * 100:+.2f}%) vs LTP",
                style=f"bold {pal.warn}",
            )
        out.append("\n")
        lines += 1

    out._chart_meta = {
        "kind": "candle",
        "grid_row0": grid_row0,
        "grid_rows": grid_h,
        "plot_x0": plot_x0,
        "plot_w": plot_w,
        "step": step,
        "c_off": c_off,
        "n": n_disp,
        "lo": lo_p,
        "hi": hi_p,
        "start": vp.start,
        "end": vp.end,
        "n_total": n_all,
        "pan": vp.pan,
        "compressed": bool(vp.compress_to),
        "lines": lines,
    }
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
    zoom_bars: int | None = None,
    pan_offset: int = 0,
    fit_all: bool = False,
    timestamps: Sequence[str] | None = None,
    crosshair_idx: int | None = None,
    crosshair_price: float | None = None,
    live_ltp: float | None = None,
    bar_countdown_sec: float | None = None,
    compact_header: bool = False,
    total_height: int | None = None,
    status_note: str = "",
) -> Text:
    """Render values as a smooth braille-dot line chart with volume sub-strip.

    ``width`` is the total text width.  Points are linearly interpolated so the
    line is continuous at any zoom level; ``zoom_bars``/``pan_offset``/
    ``fit_all`` select the visible window exactly like the candlestick view.
    """
    if not values:
        return Text("  — no data —", style="dim")

    from sktui.themes import current_palette
    pal = current_palette()

    all_v = [float(v) for v in values]
    all_vol = [float(v) for v in volumes] if volumes else []
    all_ts = list(timestamps) if timestamps else []
    n_all = len(all_v)

    y_width = max(len(_price_label(max(all_v))), len(_price_label(min(all_v))), 7)
    gutter_w = y_width + 2
    plot_x0 = 2 + y_width + 3
    plot_w = max(10, width - plot_x0 - gutter_w)
    dots_x = plot_w * COLS_PER_CELL

    # Window selection
    if fit_all:
        bars, pan = n_all, 0
    else:
        bars = zoom_bars if zoom_bars and zoom_bars > 0 else min(n_all, dots_x)
        bars = min(max(2, bars), n_all)
        pan = max(0, min(int(pan_offset or 0), n_all - bars))
    end = n_all - pan
    start = max(0, end - bars)
    vals = all_v[start:end]
    vols = all_vol[start:end] if all_vol else []
    tss = all_ts[start:end] if all_ts else []
    span = len(vals)

    xh_active = crosshair_idx is not None and 0 <= crosshair_idx < span
    if total_height is not None:
        chrome = 1 + (1 if label and not compact_header else 0) + 2
        chrome += 1 if (show_vol_strip and vols and max(vols) > 0) else 0
        chrome += 1  # status
        chrome += 1 if show_stats else 0
        chrome += 1 if xh_active else 0
        height = max(4, total_height - chrome)

    lo, hi = min(vals), max(vals)
    span_p = hi - lo
    pad = span_p * 0.06 if span_p > 0 else max(abs(hi) * 0.002, 0.05)
    lo_p, hi_p = lo - pad, hi + pad
    rng = (hi_p - lo_p) or 1.0
    total_rows = height * ROWS_PER_CELL

    def _dot_row(v: float) -> int:
        return max(0, min(total_rows - 1, int(round((v - lo_p) / rng * (total_rows - 1)))))

    def _char_row(v: float) -> int:
        return height - 1 - (_dot_row(v) // ROWS_PER_CELL)

    def _value_at(x: int) -> float:
        if span == 1:
            return vals[0]
        f = x * (span - 1) / max(1, dots_x - 1)
        i = int(f)
        if i >= span - 1:
            return vals[-1]
        return vals[i] + (vals[i + 1] - vals[i]) * (f - i)

    def _idx_to_col(i: int) -> int:
        if span <= 1:
            return 0
        return min(plot_w - 1, int(round(i * (dots_x - 1) / (span - 1))) // COLS_PER_CELL)

    grid: list[list[int]] = [[0] * plot_w for _ in range(height)]
    prev_r: int | None = None
    for x in range(dots_x):
        r = _dot_row(_value_at(x))
        lo_r, hi_r = (r, r) if prev_r is None else (min(r, prev_r), max(r, prev_r))
        for rr in range(lo_r, hi_r + 1):
            char_row = height - 1 - (rr // ROWS_PER_CELL)
            grid[char_row][x // COLS_PER_CELL] |= _DOT[ROWS_PER_CELL - 1 - (rr % ROWS_PER_CELL)][x % COLS_PER_CELL]
        prev_r = r

    up = vals[-1] >= vals[0]
    out = ChartText(no_wrap=True, overflow="crop")
    lines = 0

    clr = pal.bull if up else pal.bear
    chg_pct = (vals[-1] - vals[0]) / vals[0] * 100 if vals[0] else 0
    sign = "+" if chg_pct >= 0 else ""
    out.append(f"  {symbol}", style=f"bold {clr}")
    if interval:
        out.append(f"  [{interval}]", style=f"bold {pal.primary}")
    out.append(f"  {_price_label(vals[-1])}", style=f"bold {pal.fg_strong}")
    out.append(f"  {sign}{chg_pct:.2f}%", style=f"bold {pal.bull if chg_pct >= 0 else pal.bear}")
    if bar_countdown_sec is not None and bar_countdown_sec > 0:
        out.append(f"  ⏱ {bar_countdown_sec:04.1f}s", style=f"bold {pal.warn}")
    if pan == 0 and not fit_all and (live_ltp is not None or bar_countdown_sec is not None):
        out.append("  ● LIVE", style=f"bold {pal.bull}")
    out.append("\n")
    lines += 1
    if label and not compact_header:
        out.append(f"  {label}\n", style=pal.muted)
        lines += 1
    grid_row0 = lines

    ltp_val = live_ltp if live_ltp is not None else (all_v[-1] if pan == 0 else None)
    ltp_row = _char_row(ltp_val) if (ltp_val is not None and lo_p <= ltp_val <= hi_p) else None
    xh_col = _idx_to_col(crosshair_idx) if xh_active else None  # type: ignore[arg-type]
    xh_px = crosshair_price if crosshair_price is not None else (vals[crosshair_idx] if xh_active else None)  # type: ignore[index]
    xh_row = _char_row(xh_px) if (xh_px is not None and lo_p <= xh_px <= hi_p) else None

    grad = pal.bull_grad if up else pal.bear_grad
    label_rows = set(range(0, height, 4)) | {height - 1}
    for char_row in range(height):
        price_at = hi_p - (char_row / max(1, height - 1)) * rng
        if char_row == xh_row and xh_px is not None:
            out.append(" ")
            out.append(f"{_price_label(xh_px):>{y_width + 1}}", style=f"bold {pal.on_warn} on {pal.warn}")
            out.append("  ┤", style=pal.subtle)
        elif char_row in label_rows:
            out.append(f"  {_price_label(price_at):>{y_width}}  ┤", style=pal.subtle)
        else:
            out.append(f"  {'':>{y_width}}  │", style=pal.subtle)

        for char_col in range(plot_w):
            bits = grid[char_row][char_col]
            if bits:
                col = grad[min(int(char_col / plot_w * len(grad)), len(grad) - 1)]
                st = Style(color=col, bgcolor=pal.primary_tint) if char_col == xh_col else Style(color=col)
                out.append(chr(BRAILLE_BASE | bits), style=st)
            elif char_col == xh_col and char_row == xh_row:
                out.append("┼", style=f"bold {pal.warn}")
            elif char_col == xh_col:
                out.append("┆", style=pal.warn)
            elif char_row == xh_row:
                out.append("┄", style=pal.warn)
            elif char_row == ltp_row:
                out.append("┈", style=clr)
            elif char_row in label_rows and char_col % 3 == 0:
                out.append("·", style=pal.divider)
            else:
                out.append(" ")
        if char_row == ltp_row and ltp_val is not None:
            out.append(f"◀{_price_label(ltp_val)} ", style=f"bold {pal.on_bull if up else pal.on_bear} on {clr}")
        out.append("\n")
        lines += 1

    # X-axis + timestamps
    axis = ["─"] * plot_w
    lbls = [" "] * plot_w
    if tss:
        min_gap = 10
        last_end = -min_gap
        n_lbl = max(1, plot_w // min_gap)
        for k in range(n_lbl + 1):
            i = min(span - 1, int(k * (span - 1) / max(1, n_lbl)))
            col = _idx_to_col(i)
            t = _ts_short(tss[i])
            a = max(0, col - len(t) // 2)
            if not t or a < last_end + 2 or a + len(t) > plot_w:
                continue
            axis[col] = "┬"
            for j, ch in enumerate(t):
                lbls[a + j] = ch
            last_end = a + len(t)
    if xh_col is not None:
        axis[xh_col] = "▲"
    out.append(f"  {'':>{y_width}}  └{''.join(axis)}\n", style=pal.subtle)
    lines += 1
    out.append(f"  {'':>{y_width}}   {''.join(lbls)}\n", style=pal.muted)
    lines += 1

    if show_vol_strip and vols and max(vols) > 0:
        max_vol = max(vols)
        out.append(f"  {'Vol':>{y_width}}  │", style=pal.subtle)
        for c in range(plot_w):
            a = int(c * span / plot_w)
            b = max(a + 1, int((c + 1) * span / plot_w))
            chunk = vols[a:b]
            frac = (sum(chunk) / len(chunk) if chunk else 0.0) / max_vol
            ch = _VOL_BLOCKS[max(0, min(8, int(round(frac * 8))))]
            v_clr = pal.bull if frac > 0.5 else pal.teal if frac > 0.2 else pal.subtle
            out.append(ch, style=v_clr)
        out.append("\n")
        lines += 1

    # Viewport minimap
    tw = max(10, min(32, plot_w // 3))
    a = int(start / n_all * tw)
    b = max(a + 1, int(math.ceil(end / n_all * tw)))
    out.append(f"  {'':>{y_width}}   ", style=pal.subtle)
    out.append(f"Pts {start + 1}–{end}/{n_all} ", style=pal.muted)
    out.append("━" * a, style=pal.divider)
    out.append("█" * (b - a), style=pal.primary)
    out.append("━" * (tw - b), style=pal.divider)
    if fit_all:
        out.append("  ⤢ FIT ALL", style=f"bold {pal.accent}")
    elif pan == 0:
        out.append("  ● LIVE", style=f"bold {pal.bull}")
    else:
        out.append(f"  ◀ {pan} back · End=live", style=f"bold {pal.warn}")
    if status_note:
        out.append(f"  {status_note}", style=pal.muted)
    out.append("\n")
    lines += 1

    if xh_active:
        i = crosshair_idx  # type: ignore[assignment]
        t = _ts_short(tss[i]) if tss else f"#{start + i}"  # type: ignore[index]
        out.append(f"  ┼ {t}  {_price_label(vals[i])}", style=f"bold {pal.warn}")  # type: ignore[index]
        if vols:
            out.append(f"  Vol {_compact_vol(vols[i])}", style=pal.muted)  # type: ignore[index]
        if xh_px is not None and ltp_val:
            d = xh_px - ltp_val
            out.append(f"  │ ⌖ {_price_label(xh_px)}  Δ {d:+.2f} ({d / ltp_val * 100:+.2f}%) vs LTP", style=f"bold {pal.warn}")
        out.append("\n")
        lines += 1

    if show_stats and vals:
        hi_v, lo_v, op_v, cl_v = max(vals), min(vals), vals[0], vals[-1]
        avg_v = sum(vals) / len(vals)
        chg_v = cl_v - op_v
        chg_p = chg_v / op_v * 100 if op_v else 0
        sign = "+" if chg_v >= 0 else ""
        c_chg = pal.bull if chg_v >= 0 else pal.bear
        out.append("  open ", style=pal.subtle)
        out.append(_price_label(op_v), style=pal.fg)
        out.append("  high ", style=pal.subtle)
        out.append(_price_label(hi_v), style=pal.bull)
        out.append("  low ", style=pal.subtle)
        out.append(_price_label(lo_v), style=pal.bear)
        out.append("  close ", style=pal.subtle)
        out.append(_price_label(cl_v), style=f"bold {pal.fg_strong}")
        out.append("  avg ", style=pal.subtle)
        out.append(_price_label(avg_v), style=pal.muted)
        out.append("  chg ", style=pal.subtle)
        out.append(f"{sign}{_price_label(chg_v)} ({sign}{chg_p:.2f}%)", style=f"bold {c_chg}")
        if vols and max(vols) > 0:
            tot_vol = sum(vols)
            out.append("  vol ", style=pal.subtle)
            out.append(_compact_vol(tot_vol), style=f"bold {pal.primary}")
        out.append("\n")
        lines += 1

    out._chart_meta = {
        "kind": "line",
        "grid_row0": grid_row0,
        "grid_rows": height,
        "plot_x0": plot_x0,
        "plot_w": plot_w,
        "n": span,
        "lo": lo_p,
        "hi": hi_p,
        "start": start,
        "end": end,
        "n_total": n_all,
        "pan": pan,
        "lines": lines,
    }
    return out


def render_volume_bars(
    dates: list[str],
    volumes: list[float],
    width: int = 60,
) -> Text:
    """Render a simple horizontal bar chart of volumes."""
    if not volumes:
        return Text("  — no volume data —", style="dim")
    from sktui.themes import current_palette
    pal = current_palette()
    mx = max(volumes) or 1
    out = Text()
    n = min(len(dates), 20)
    dates = dates[-n:]
    volumes = volumes[-n:]
    bar_w = width - 16
    for d, v in zip(dates, volumes):
        bar_len = int(v / mx * bar_w)
        frac = v / mx
        clr = pal.bull if frac > 0.7 else pal.teal if frac > 0.4 else pal.secondary
        out.append(f"  {d[-5:]:>5}  ", style=pal.subtle)
        out.append("█" * bar_len, style=clr)
        out.append(f"  {v:,.0f}\n", style=pal.muted)
    return out
