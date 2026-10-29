"""Dashboard card and P/L strip rendering helpers.

All text composition for the dashboard tab and the P/L strip lives here.
MainScreen calls these helpers and updates its Static widgets with the
returned Rich Text objects.
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from sktui.config import C_AMBER, C_CYAN, C_DIM, C_GREEN, C_MUTED, C_RED, C_SUBTLE
from sktui.utils import get, is_open_order, sign_style


def update_dashboard(
    dash_summary: Static,
    dash_orders: Static,
    dash_watch: Static,
    orders: list[dict],
    positions: list[dict],
    holdings: list[dict],
    watch: list[dict],
    raw_ticks: dict,
    tick_history: dict,
    sparkline_fn: object,
) -> None:
    """Render and push all three dashboard card panels.

    Parameters are the current data snapshots from MainScreen.
    The sparkline_fn is the function imported from modals (to avoid a
    top-level import cycle).
    """
    bpl = sum(float(str(get(r, "bpl", default=0)).replace(",", "") or 0) for r in positions)
    mtm = sum(float(str(get(r, "mtm", default=0)).replace(",", "") or 0) for r in positions)
    total_pnl = bpl + mtm

    # 1. Summary Strip
    s = Text()
    s.append("  ACCOUNT & PORTFOLIO OVERVIEW\n\n", style=f"bold {C_CYAN}")
    s.append("  Net P/L: ", style=C_MUTED)
    s.append(f"₹{total_pnl:+,.2f}  ", style=sign_style(total_pnl))
    s.append(f"(Realised: ₹{bpl:+,.2f} · MTM: ₹{mtm:+,.2f})\n", style=C_SUBTLE)
    s.append("  Active Positions: ", style=C_MUTED)
    s.append(f"{len(positions)}  ", style=f"bold {C_CYAN}")
    s.append("  Open Orders: ", style=C_MUTED)
    s.append(f"{sum(1 for r in orders if is_open_order(r))}  ", style=f"bold {C_AMBER}")
    s.append("  Holdings: ", style=C_MUTED)
    s.append(f"{len(holdings)}  ", style=f"bold {C_GREEN}")
    s.append("  Watchlist: ", style=C_MUTED)
    s.append(f"{len(watch)} symbols\n", style=C_MUTED)
    dash_summary.update(s)

    # 2. Orders Analytics
    o_text = Text()
    open_cnt   = sum(1 for r in orders if is_open_order(r))
    filled_cnt = sum(1 for r in orders if "fully" in str(get(r, "orderStatus")).lower())
    rej_cnt    = sum(1 for r in orders if any(
        x in str(get(r, "orderStatus")).lower() for x in ("reject", "fail", "cancel")))
    o_text.append("  Orders breakdown: ", style=C_MUTED)
    o_text.append(f"Filled: {filled_cnt}  ", style=f"bold {C_GREEN}")
    o_text.append(f"Pending: {open_cnt}  ", style=f"bold {C_AMBER}")
    o_text.append(f"Cancelled/Rejected: {rej_cnt}\n\n", style=C_SUBTLE)
    if orders:
        o_text.append("  Recent Orders:\n", style=C_MUTED)
        for r in orders[:4]:
            side = str(get(r, "buySell", default="B")).upper()
            clr  = C_GREEN if side.startswith("B") else C_RED
            o_text.append(f"   {side[:1]} ", style=f"bold {clr}")
            o_text.append(f"{get(r, 'orderQty')} × {get(r, 'tradingSymbol')} @ ₹{get(r, 'orderPrice')} ")
            o_text.append(f"[{get(r, 'orderStatus')}]\n", style=C_SUBTLE)
    else:
        o_text.append("  No orders submitted in current session.\n", style=C_DIM)
    dash_orders.update(o_text)

    # 3. Watchlist Quick Monitor
    w_text = Text()
    w_text.append("  Live Market Snapshot:\n\n", style=C_MUTED)
    for item in watch[:6]:
        key  = f"{item['exchange']}{item['scripCode']}"
        q    = raw_ticks.get(key, {})
        ltp  = q.get("ltp") or 0.0
        pct  = q.get("perChange") or 0.0
        hist = tick_history.get(key, [ltp] * 5)
        spk  = sparkline_fn(hist, width=12)
        w_text.append(f"  {item.get('tradingSymbol', ''):<10} ", style=f"bold {C_CYAN}")
        w_text.append(f"₹{ltp:>8.2f} ", style="bold white")
        w_text.append(f"({pct:+6.2f}%) ", style=sign_style(pct))
        w_text.append(f" {spk}\n", style=C_GREEN if pct >= 0 else C_RED)
    dash_watch.update(w_text)


def update_pnl_strip(pnl_strip: Static, rows: list[dict]) -> None:
    """Render the P/L strip from position rows and push to *pnl_strip* widget."""
    try:
        bpl   = sum(float(str(get(r, "bpl", default=0)).replace(",", "") or 0) for r in rows)
        mtm   = sum(float(str(get(r, "mtm", default=0)).replace(",", "") or 0) for r in rows)
        total = bpl + mtm
        c_bpl = C_GREEN if bpl   >= 0 else C_RED
        c_mtm = C_GREEN if mtm   >= 0 else C_RED
        c_tot = C_GREEN if total >= 0 else C_RED
        s  = "+" if bpl   >= 0 else ""
        sm = "+" if mtm   >= 0 else ""
        st = "+" if total >= 0 else ""
        t  = Text()
        t.append("  P/L  ",      style=C_SUBTLE)
        t.append("Realised: ",   style=C_MUTED)
        t.append(f"₹{s}{bpl:,.2f}",    style=f"bold {c_bpl}")
        t.append("   MTM: ",     style=C_MUTED)
        t.append(f"₹{sm}{mtm:,.2f}",   style=f"bold {c_mtm}")
        t.append("   Total: ",   style=C_MUTED)
        t.append(f"₹{st}{total:,.2f}", style=f"bold {c_tot}")
        t.append(f"  ({len(rows)} position{'s' if len(rows) != 1 else ''})", style=C_SUBTLE)
        pnl_strip.update(t)
    except Exception:
        pass
