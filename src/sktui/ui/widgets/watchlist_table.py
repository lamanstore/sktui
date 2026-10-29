"""Watchlist DataTable helpers.

Owns the column definition and the row add/update logic so MainScreen
does not need to know the exact cell format for every field.
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import DataTable

from sktui.config import C_GREEN, C_RED, C_TEXT
from sktui.utils import fmt, scrip_label, sign_style

# ── Column definitions ─────────────────────────────────────────────────────────
WATCH_COLS: list[tuple[str, str]] = [
    ("sym",  "Symbol"),
    ("exch", "Exch"),
    ("ltp",  "LTP"),
    ("chg",  "Chg"),
    ("pct",  "Chg%"),
    ("bid",  "Bid"),
    ("ask",  "Ask"),
    ("vol",  "Volume"),
]


def add_watch_row(table: DataTable, item: dict, quote: dict) -> None:
    """Add a new row for *item* using *quote* data. No-op if key exists."""
    key = f"{item['exchange']}{item['scripCode']}"
    if key in table.rows:
        return
    ltp = quote.get("ltp") or 0.0
    chg = quote.get("rsChange") or 0.0
    pct = quote.get("perChange") or 0.0
    table.add_row(
        Text(f"● {scrip_label(item)}", style=f"bold {C_TEXT}"),
        item["exchange"],
        Text(fmt(ltp), style=f"bold {C_GREEN}"),
        Text(fmt(chg), style=sign_style(chg)),
        Text(f"{pct:+.2f}%" if isinstance(pct, (int, float)) else fmt(pct), style=sign_style(pct)),
        Text(fmt(quote.get("bidPrice"))),
        Text(fmt(quote.get("offPrice"))),
        Text(fmt(quote.get("qty"))),
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

    def _set(col: str, val: Any) -> None:
        try:
            table.update_cell(key, col, val)
        except Exception:
            pass

    # Update symbol indicator (● Live vs ▲ Stale)
    if symbol_name:
        if is_stale:
            _set("sym", Text(f"▲ {symbol_name}", style="bold #f59e0b"))
        else:
            _set("sym", Text(f"● {symbol_name}", style=f"bold {C_TEXT}"))

    chg = tick.get("rsChange") or tick.get("change") or tick.get("netPriceChange")
    pct = tick.get("perChange") or tick.get("pChange") or tick.get("percentChange")
    bid = tick.get("bidPrice") or tick.get("bid")
    ask = tick.get("offPrice") or tick.get("ask")
    vol = tick.get("qty")      or tick.get("volume") or tick.get("vol")

    if new_ltp is not None:
        fltp = new_ltp
        if is_stale:
            _set("ltp", Text(f"~ {fmt(fltp)}", style="dim #888888"))
        elif prev_ltp is not None:
            if fltp > prev_ltp:
                _set("ltp", Text(f"▲ {fmt(fltp)}", style=f"bold {C_GREEN}"))
            elif fltp < prev_ltp:
                _set("ltp", Text(f"▼ {fmt(fltp)}", style=f"bold {C_RED}"))
            else:
                _set("ltp", Text(fmt(fltp), style=C_TEXT))
        else:
            _set("ltp", Text(fmt(fltp), style=f"bold {C_GREEN}"))

    if chg is not None:
        c_style = "dim #888888" if is_stale else sign_style(chg)
        _set("chg", Text(fmt(chg), style=c_style))
    if pct is not None:
        fpct = float(pct)
        p_style = "dim #888888" if is_stale else sign_style(fpct)
        _set("pct", Text(f"{fpct:+.2f}%", style=p_style))
    if bid is not None: _set("bid", Text(fmt(bid)))
    if ask is not None: _set("ask", Text(fmt(ask)))
    if vol is not None: _set("vol", Text(fmt(vol)))

    # Secondary columns if configured
    op  = tick.get("open")     or tick.get("openPrice")
    hi  = tick.get("high")     or tick.get("highPrice")
    lo  = tick.get("low")      or tick.get("lowPrice")
    cl  = tick.get("close")    or tick.get("closePrice")
    oi  = tick.get("currentOI") or tick.get("openInterest") or tick.get("oi")
    if op  is not None: _set("open",  Text(fmt(op)))
    if hi  is not None: _set("high",  Text(fmt(hi), style=C_GREEN))
    if lo  is not None: _set("low",   Text(fmt(lo), style=C_RED))
    if cl  is not None: _set("close", Text(fmt(cl)))
    if oi  is not None: _set("oi",    Text(fmt(oi)))
