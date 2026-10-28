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
        t.append(f"  ·  CID: {c.customer_id}", style=C_MUTED)
        t.append(f"  ·  IP: {public_ip}", style=f"bold {C_CYAN}")
        t.append("  ·  ", style=C_MUTED)
        exs = c.exchanges if c.exchanges else ["NC", "BC", "NF", "RN"]
        for exch in exs:
            t.append(f" {exch} ", style=f"bold {C_CYAN} on {C_PANEL}")
            t.append(" ")
        t.append("  ·  Risk: ", style=C_MUTED)
        t.append("NORMAL", style=f"bold {C_GREEN}")
        t.append("  ·  K = Flatten   / = cmd   F1 = help", style=C_SUBTLE)
        return t

    # ── Indices bar ───────────────────────────────────────────────────────────
    def render_indices_bar(self, raw_ticks: dict | None = None) -> Text:
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

        nifty_q = raw.get("NIFTY50", {})
        n_ltp = nifty_q.get("ltp") or 25120.40
        n_chg = nifty_q.get("rsChange") or 84.50
        n_pct = nifty_q.get("perChange") or 0.34

        t = Text()
        t.append(f"  ◉ {session}  ", style=f"bold {ses_clr}")
        t.append("·", style=C_SUBTLE)
        t.append("  NIFTY 50 ", style=C_MUTED)
        t.append(f"{n_ltp:,.2f} ", style="bold white")
        t.append(f"({n_chg:+.2f} / {n_pct:+.2f}%)", style=sign_style(n_chg))
        t.append("  ·  ", style=C_SUBTLE)
        t.append("BANKNIFTY ", style=C_MUTED)
        t.append("52,410.80 ", style="bold white")
        t.append("(+185.20 / +0.35%)", style=f"bold {C_GREEN}")
        t.append("  ·  ", style=C_SUBTLE)
        t.append("SENSEX ", style=C_MUTED)
        t.append("82,140.10 ", style="bold white")
        t.append("(+240.10 / +0.29%)", style=f"bold {C_GREEN}")
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

    def render_radar_sectors(self) -> Text:
        t = Text()
        t.append("  NIFTY BANK: ", style=C_MUTED); t.append("+0.35% 🟢\n", style=f"bold {C_GREEN}")
        t.append("  NIFTY IT:   ", style=C_MUTED); t.append("-0.12% 🔴\n", style=f"bold {C_RED}")
        t.append("  NIFTY AUTO: ", style=C_MUTED); t.append("+1.15% 🟢\n", style=f"bold {C_GREEN}")
        t.append("  INDIA VIX:  ", style=C_MUTED); t.append("13.42  🟢",   style=f"bold {C_GREEN}")
        return t

    def render_radar_breadth(self) -> Text:
        t = Text()
        t.append("  Adv / Dec:  ", style=C_MUTED); t.append("1420 / 890\n", style="bold white")
        t.append("  Ratio:      ", style=C_MUTED); t.append("1.60 🟢\n",    style=f"bold {C_GREEN}")
        t.append("  FII Cash:   ", style=C_MUTED); t.append("+120Cr",       style=f"bold {C_GREEN}")
        return t
