"""Watchlist DataTable helpers.

Owns the column definition and the row add/update logic so MainScreen
does not need to know the exact cell format for every field.
"""
from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.widgets import DataTable

from sktui.themes import current_palette
from sktui.utils import compact_number, fmt, scrip_label, sign_style

# ── Column definitions ─────────────────────────────────────────────────────────
WATCH_COLS: list[tuple[str, str]] = [
    ("sym",  "Symbol"),
    ("exch", "Ex"),
    ("ltp",  "   LTP"),
    ("pct",  "  Chg%"),
    ("chg",  "   Chg"),
    ("vol",  "  Vol"),
    ("bid",  "   Bid"),
    ("ask",  "   Ask"),
]


def add_watch_row(table: DataTable, item: dict, quote: dict) -> None:
    """Add a new row for *item* using *quote* data. No-op if key exists."""
    key = f"{item['exchange']}{item['scripCode']}"
    if key in table.rows:
        return
    p = current_palette()
    ltp = quote.get("ltp") or 0.0
    chg = quote.get("rsChange") or 0.0
    pct = quote.get("perChange") or 0.0
    vol = quote.get("qty") or quote.get("volume") or 0
    dot_clr = p.bull if chg > 0 else (p.bear if chg < 0 else p.primary)
    sym_txt = Text()
    sym_txt.append("● ", style=f"bold {dot_clr}")
    sym_txt.append(scrip_label(item), style=f"bold {p.fg}")
    table.add_row(
        sym_txt,
        Text(str(item["exchange"]), style=p.subtle),
        Text(fmt(ltp), style=f"bold {p.bull}" if ltp else p.subtle),
        Text(f"{pct:+.2f}%" if isinstance(pct, (int, float)) else fmt(pct), style=sign_style(pct)),
        Text(fmt(chg), style=sign_style(chg)),
        Text(compact_number(vol) if vol else "—", style=p.muted),
        Text(fmt(quote.get("bidPrice")), style=p.subtle),
        Text(fmt(quote.get("offPrice")), style=p.subtle),
        key=key,
    )


def update_watch_row(
    table: DataTable,
    key: str,
    tick: dict,
    prev_ltp: float | None,
    new_ltp: float | None,
    is_stale: bool = False,
    symbol_name: str | None = None,
) -> None:
    """Update an existing watchlist row in-place from a live tick dict with staleness flag."""
    if key not in table.rows:
        return
    p = current_palette()

    def _set(col: str, val: Any) -> None:
        try:
            table.update_cell(key, col, val)
        except Exception:
            pass

    chg = tick.get("rsChange") if tick.get("rsChange") is not None else (tick.get("change") or tick.get("netPriceChange"))
    pct = tick.get("perChange") if tick.get("perChange") is not None else (tick.get("pChange") or tick.get("percentChange"))
    bid = tick.get("bidPrice") or tick.get("bid")
    ask = tick.get("offPrice") or tick.get("ask")
    vol = tick.get("qty")      or tick.get("volume") or tick.get("vol")

    # Update symbol indicator (● Live vs ▲ Stale)
    if symbol_name:
        if is_stale:
            _set("sym", Text(f"▲ {symbol_name}", style=f"bold {p.warn}"))
        else:
            dot_clr = p.bull if (chg or 0) > 0 else (p.bear if (chg or 0) < 0 else p.primary)
            t_sym = Text()
            t_sym.append("● ", style=f"bold {dot_clr}")
            t_sym.append(symbol_name, style=f"bold {p.fg}")
            _set("sym", t_sym)

    if new_ltp is not None:
        fltp = new_ltp
        if is_stale:
            _set("ltp", Text(f"~ {fmt(fltp)}", style=p.subtle))
        elif prev_ltp is not None:
            if fltp > prev_ltp:
                _set("ltp", Text(f"▲ {fmt(fltp)}", style=f"bold {p.bull}"))
            elif fltp < prev_ltp:
                _set("ltp", Text(f"▼ {fmt(fltp)}", style=f"bold {p.bear}"))
            else:
                _set("ltp", Text(fmt(fltp), style=f"bold {p.fg}"))
        else:
            _set("ltp", Text(fmt(fltp), style=f"bold {p.bull}"))

    if chg is not None:
        c_style = p.subtle if is_stale else sign_style(chg)
        _set("chg", Text(fmt(chg), style=c_style))
    if pct is not None:
        fpct = float(pct)
        p_style = p.subtle if is_stale else sign_style(fpct)
        _set("pct", Text(f"{fpct:+.2f}%", style=p_style))
    if bid is not None:
        _set("bid", Text(fmt(bid), style=p.muted))
    if ask is not None:
        _set("ask", Text(fmt(ask), style=p.muted))
    if vol is not None:
        _set("vol", Text(compact_number(vol), style=p.muted))

    # Secondary columns if configured
    op  = tick.get("open")     or tick.get("openPrice")
    hi  = tick.get("high")     or tick.get("highPrice")
    lo  = tick.get("low")      or tick.get("lowPrice")
    cl  = tick.get("close")    or tick.get("closePrice")
    oi  = tick.get("currentOI") or tick.get("openInterest") or tick.get("oi")
    if op  is not None: _set("open",  Text(fmt(op), style=p.fg))
    if hi  is not None: _set("high",  Text(fmt(hi), style=p.bull))
    if lo  is not None: _set("low",   Text(fmt(lo), style=p.bear))
    if cl  is not None: _set("close", Text(fmt(cl), style=p.fg))
    if oi  is not None: _set("oi",    Text(fmt(oi), style=p.primary))


def refresh_watchlist_theme(table: DataTable, watch: list[dict], quotes: Any) -> None:
    """Re-color all existing watchlist rows using the newly active `ThemePalette`."""
    p = current_palette()
    for item in watch:
        key = f"{item['exchange']}{item['scripCode']}"
        if key not in table.rows:
            continue
        q = quotes.get(key) if hasattr(quotes, "get") else {}
        is_stale = quotes.is_stale(key, threshold=5.0) if (q and hasattr(quotes, "is_stale")) else False
        sym = scrip_label(item)
        ltp = q.get("ltp")
        try:
            table.update_cell(key, "exch", Text(str(item["exchange"]), style=p.subtle))
            if not q:
                dot_clr = p.primary
                sym_txt = Text()
                sym_txt.append("● ", style=f"bold {dot_clr}")
                sym_txt.append(sym, style=f"bold {p.fg}")
                table.update_cell(key, "sym", sym_txt)
                table.update_cell(key, "ltp", Text(fmt(0.0), style=p.subtle))
                table.update_cell(key, "pct", Text("+0.00%", style=sign_style(0.0)))
                table.update_cell(key, "chg", Text(fmt(0.0), style=sign_style(0.0)))
                table.update_cell(key, "vol", Text("—", style=p.muted))
                table.update_cell(key, "bid", Text(fmt(None), style=p.subtle))
                table.update_cell(key, "ask", Text(fmt(None), style=p.subtle))
                continue
        except Exception:
            pass
        update_watch_row(
            table,
            key,
            q,
            prev_ltp=ltp,
            new_ltp=ltp,
            is_stale=is_stale,
            symbol_name=sym,
        )
