"""Status service — account bar, indices bar, and market radar rendering.

Owns all status / header / sidebar update logic so MainScreen.compose()
and on_mount() can stay thin.

Usage::

    svc = StatusService(client)
    svc.render_account_bar(public_ip)   -> Rich Text
    svc.render_indices_bar()            -> Rich Text
    svc.render_radar_session()          -> Rich Text
    svc.render_radar_sectors()          -> Rich Text
    svc.render_radar_breadth()          -> Rich Text
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from rich.text import Text

from sktui.config import (
    C_AMBER, C_CYAN, C_DIM, C_GREEN, C_MUTED, C_PANEL, C_RED, C_SUBTLE, C_TEXT,
)
from sktui.utils import sign_style

if TYPE_CHECKING:
    from sktui.api.client import Client


class StatusService:
    """Builds Rich Text objects for the status bars and sidebar radar."""

    def __init__(self, client: "Client") -> None:
        self._client = client

    # ── Account bar ───────────────────────────────────────────────────────────
    def render_account_bar(
        self,
        public_ip: str,
        raw_ticks: dict | None = None,
        quote_store: Any | None = None,
        width: int = 120,
    ) -> Text:
        c = self._client
        t = Text()
        if c.paper:
            t.append(" ⚠ PAPER ", style="bold black on #f59e0b")
        else:
            t.append(" ⬢ LIVE ",  style="bold white on #ff4757")
        t.append(" ")

        # High-visibility connection badge (● LIVE 18ms / ▲ STALE 3.2s / ■ RECONNECTING)
        if quote_store is not None and hasattr(quote_store, "feed_badge"):
            b_text, b_col = quote_store.feed_badge()
            t.append(f" {b_text} ", style=f"bold {b_col} on #0d1526")
            t.append("  ·  ", style=C_MUTED)

        t.append(f"{c.full_name or c.login_id}", style=f"bold {C_TEXT}")
        if width >= 110:
            t.append(f"  ·  CID: {c.customer_id}", style=C_MUTED)
        t.append(f"  ·  IP: {public_ip}", style=f"bold {C_CYAN}")
        if width >= 135:
            t.append("  ·  ", style=C_MUTED)
            exs = c.exchanges if c.exchanges else ["NC", "BC", "NF", "RN"]
            for exch in exs:
                t.append(f" {exch} ", style=f"bold {C_CYAN} on {C_PANEL}")
                t.append(" ")
        if width >= 90:
            t.append("  ·  Risk: ", style=C_MUTED)
            t.append("NORMAL", style=f"bold {C_GREEN}")
        if width >= 145:
            t.append("  ·  K = Flatten   / = cmd   F1 = help", style=C_SUBTLE)
        return t

    # ── Indices bar ───────────────────────────────────────────────────────────
    def render_indices_bar(self, raw_ticks: dict | None = None, width: int = 120) -> Text:
        now   = datetime.now()
        hour  = now.hour + now.minute / 60
        raw   = raw_ticks or {}

        session = (
            "PRE-OPEN" if 9 <= hour < 9.25 else
            "OPEN"     if 9.25 <= hour < 15.5 else
            "POST"     if 15.5 <= hour < 16 else "CLOSED"
        )
        ses_clr = (
            C_GREEN if session == "OPEN" else
            C_AMBER if session in ("PRE-OPEN", "POST") else C_SUBTLE
        )

        nifty_q = raw.get("NIFTY50") or raw.get("NIFTY") or raw.get("NC_NIFTY") or {}
        n_ltp = nifty_q.get("ltp")
        n_chg = nifty_q.get("rsChange")
        n_pct = nifty_q.get("perChange")

        t = Text()
        t.append(f"  ● {session}  ", style=f"bold {ses_clr}")
        t.append("·", style=C_SUBTLE)
        t.append("  NIFTY 50 ", style=C_MUTED)
        if n_ltp is not None:
            t.append(f"{n_ltp:,.2f} ", style="bold white")
            if n_chg is not None and n_pct is not None:
                t.append(f"({n_chg:+.2f} / {n_pct:+.2f}%)", style=sign_style(n_chg))
        else:
            t.append("--.-- ", style=C_SUBTLE)
            t.append("(waiting)", style=C_SUBTLE)

        if width >= 90:
            t.append("  ·  ", style=C_SUBTLE)
            t.append("BANKNIFTY ", style=C_MUTED)
            bn_q = raw.get("BANKNIFTY") or raw.get("NF_BANKNIFTY") or {}
            bn_ltp = bn_q.get("ltp")
            bn_chg = bn_q.get("rsChange")
            bn_pct = bn_q.get("perChange")
            if bn_ltp is not None:
                t.append(f"{bn_ltp:,.2f} ", style="bold white")
                if bn_chg is not None and bn_pct is not None:
                    t.append(f"({bn_chg:+.2f} / {bn_pct:+.2f}%)", style=sign_style(bn_chg))
            else:
                t.append("--.--", style=C_SUBTLE)

        if width >= 135:
            t.append("  ·  ", style=C_SUBTLE)
            t.append("SENSEX ", style=C_MUTED)
            sx_q = raw.get("SENSEX") or raw.get("BC_SENSEX") or {}
            sx_ltp = sx_q.get("ltp")
            sx_chg = sx_q.get("rsChange")
            sx_pct = sx_q.get("perChange")
            if sx_ltp is not None:
                t.append(f"{sx_ltp:,.2f} ", style="bold white")
                if sx_chg is not None and sx_pct is not None:
                    t.append(f"({sx_chg:+.2f} / {sx_pct:+.2f}%)", style=sign_style(sx_chg))
            else:
                t.append("--.--", style=C_SUBTLE)
            t.append(f"  ·  {now.strftime('%d %b %Y  %H:%M')}", style=C_SUBTLE)
        return t

    # ── Radar panels ──────────────────────────────────────────────────────────
    def render_radar_session(self) -> Text:
        now  = datetime.now()
        hour = now.hour + now.minute / 60

        def _sess(lo: float, hi: float) -> tuple[str, str]:
            s = "OPEN" if lo <= hour < hi else "CLOSED"
            return s, C_GREEN if s == "OPEN" else C_SUBTLE

        eq_s, eq_c   = _sess(9.25, 15.5)
        cur_s, cur_c = _sess(9.0, 17.0)
        mcx_s, mcx_c = _sess(9.0, 23.5)

        t = Text()
        t.append("  NSE Equity: ", style=C_MUTED);  t.append(f"{eq_s}\n",  style=f"bold {eq_c}")
        t.append("  Currency:   ", style=C_MUTED);  t.append(f"{cur_s}\n", style=f"bold {cur_c}")
        t.append("  MCX:        ", style=C_MUTED);  t.append(f"{mcx_s}",   style=f"bold {mcx_c}")
        return t

    def render_radar_sectors(self, raw_ticks: dict | None = None) -> Text:
        raw = raw_ticks or {}
        sectors = [
            ("NIFTY BANK", raw.get("BANKNIFTY") or raw.get("NF_BANKNIFTY")),
            ("NIFTY IT", raw.get("NIFTYIT")),
            ("NIFTY AUTO", raw.get("NIFTYAUTO")),
            ("INDIA VIX", raw.get("INDIAVIX") or raw.get("VIX")),
        ]
        t = Text()
        has_any = False
        for name, data in sectors:
            if data and data.get("ltp"):
                has_any = True
                pct = data.get("perChange", 0.0)
                t.append(f"  {name:<11}: ", style=C_MUTED)
                t.append(f"{pct:+.2f}%\n", style=sign_style(pct))
        if not has_any:
            t.append("  Sectors:    ", style=C_MUTED)
            t.append("Awaiting feed\n", style=C_SUBTLE)
            t.append("  Market VIX: ", style=C_MUTED)
            t.append("--.--", style=C_SUBTLE)
        return t

    def render_radar_breadth(self, quotes: Any | None = None) -> Text:
        t = Text()
        advances = 0
        declines = 0
        unchanged = 0
        if quotes and hasattr(quotes, "raw_ticks"):
            ticks = quotes.raw_ticks
            for q in ticks.values():
                chg = q.get("rsChange") or q.get("change") or 0.0
                if chg > 0:
                    advances += 1
                elif chg < 0:
                    declines += 1
                elif chg == 0 and q.get("ltp"):
                    unchanged += 1

        t.append("  Adv / Dec:  ", style=C_MUTED)
        if advances + declines > 0:
            ratio = (advances / declines) if declines > 0 else float(advances)
            t.append(f"{advances} / {declines}\n", style="bold white")
            t.append("  A/D Ratio:  ", style=C_MUTED)
            r_style = f"bold {C_GREEN}" if ratio >= 1.0 else f"bold {C_RED}"
            t.append(f"{ratio:.2f}\n", style=r_style)
            t.append("  Unchanged:  ", style=C_MUTED)
            t.append(f"{unchanged}", style=C_SUBTLE)
        else:
            t.append("-- / --\n", style=C_SUBTLE)
            t.append("  A/D Ratio:  ", style=C_MUTED)
            t.append("--\n", style=C_SUBTLE)
            t.append("  Breadth:    ", style=C_MUTED)
            t.append("Awaiting ticks", style=C_SUBTLE)
        return t
