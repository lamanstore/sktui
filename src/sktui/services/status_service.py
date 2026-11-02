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

from sktui.themes import current_palette
from sktui.utils import sign_style

if TYPE_CHECKING:
    from sktui.api.client import Client


class StatusService:
    """Builds Rich Text objects for the status bars and sidebar radar."""

    def __init__(self, client: "Client") -> None:
        self._client = client

    # ── Account bar (Top Telemetry Row 1) ─────────────────────────────────────
    def render_account_bar(
        self,
        public_ip: str,
        raw_ticks: dict | None = None,
        quote_store: Any | None = None,
        width: int = 120,
        alerts_count: int = 0,
        daily_pnl: float | None = None,
    ) -> Text:
        p = current_palette()
        c = self._client
        t = Text()
        if getattr(c, "paper", False):
            t.append(" ◈ PAPER ", style=f"bold {p.on_warn} on {p.warn}")
        else:
            t.append(" ◈ LIVE ", style=f"bold {p.on_bear} on {p.bear}")
        t.append(" ")

        # High-visibility connection badge (● LIVE 18ms / ▲ STALE 3.2s / ■ RECONNECTING)
        if quote_store is not None and hasattr(quote_store, "feed_badge"):
            b_text, b_col = quote_store.feed_badge()
            safe_col = p.badge_color(b_col)
            t.append(f" {b_text} ", style=f"bold {safe_col} on {p.panel}")
            t.append(" │ ", style=p.divider)

        acct_label = getattr(c, "full_name", "") or getattr(c, "login_id", "") or "OPERATOR"
        t.append(f"▸ {acct_label}", style=f"bold {p.fg}")
        if width >= 115 and getattr(c, "customer_id", ""):
            t.append(f" ({c.customer_id})", style=p.subtle)

        if daily_pnl is not None and width >= 100:
            t.append(" │ ", style=p.divider)
            t.append("P&L ", style=p.muted)
            t.append(f"₹{daily_pnl:+,.2f}", style=sign_style(daily_pnl))

        t.append(" │ ", style=p.divider)
        t.append("IP ", style=p.subtle)
        t.append(f"{public_ip}", style=f"bold {p.primary}")

        if width >= 135:
            t.append(" │ ", style=p.divider)
            exs = getattr(c, "exchanges", None) or ["NC", "BC", "NF", "RN"]
            for exch in exs[:5]:
                t.append(f" {exch} ", style=f"bold {p.secondary} on {p.panel}")
                t.append(" ")

        if width >= 90:
            t.append(" │ ", style=p.divider)
            t.append("Risk ", style=p.subtle)
            t.append("● NOMINAL", style=f"bold {p.bull}")

        if alerts_count > 0 and width >= 110:
            t.append(" │ ", style=p.divider)
            t.append(f"🔔 {alerts_count} Alert{'s' if alerts_count != 1 else ''}", style=f"bold {p.warn}")

        if width >= 150:
            t.append(" │ ", style=p.divider)
            t.append("[1-7] Panes · [b/s] Trade · [c] Chart · [K] Flatten · [/] Cmd", style=p.subtle)
        return t

    # ── Indices bar (Top Telemetry Row 2) ─────────────────────────────────────
    def render_indices_bar(self, raw_ticks: dict | None = None, width: int = 120) -> Text:
        p     = current_palette()
        now   = datetime.now()
        hour  = now.hour + now.minute / 60
        raw   = raw_ticks or {}

        session = (
            "PRE-OPEN" if 9 <= hour < 9.25 else
            "OPEN"     if 9.25 <= hour < 15.5 else
            "POST"     if 15.5 <= hour < 16 else "CLOSED"
        )
        ses_clr = (
            p.bull if session == "OPEN" else
            p.warn if session in ("PRE-OPEN", "POST") else p.subtle
        )
        ses_dot = "●" if session == "OPEN" else "◐" if session in ("PRE-OPEN", "POST") else "○"

        from sktui.config import KNOWN_BASE_PRICES

        nifty_q = raw.get("NIFTY50") or raw.get("NIFTY") or raw.get("NC_NIFTY") or raw.get("NC21808") or {}
        n_ltp = nifty_q.get("ltp")
        n_chg = nifty_q.get("rsChange")
        n_pct = nifty_q.get("perChange")

        t = Text()
        t.append(f" {ses_dot} {session} ", style=f"bold {ses_clr} on {p.panel}")
        t.append(" │ ", style=p.divider)
        t.append("NIFTY 50 ", style=f"bold {p.muted}")
        if n_ltp is not None:
            arrow = "▲" if (n_chg or 0) >= 0 else "▼"
            t.append(f"{n_ltp:,.2f} ", style=f"bold {p.fg_strong}")
            if n_chg is not None and n_pct is not None:
                t.append(f"{arrow} {n_chg:+.2f} ({n_pct:+.2f}%)", style=sign_style(n_chg))
        else:
            t.append("--.-- ", style=p.subtle)
            t.append("(waiting)", style=p.subtle)

        if width >= 90:
            t.append("  │  ", style=p.divider)
            t.append("BANKNIFTY ", style=f"bold {p.muted}")
            bn_q = raw.get("BANKNIFTY") or raw.get("NF_BANKNIFTY") or raw.get("NF45004") or {}
            bn_ltp = bn_q.get("ltp")
            bn_chg = bn_q.get("rsChange")
            bn_pct = bn_q.get("perChange")
            if bn_ltp is not None:
                arrow = "▲" if (bn_chg or 0) >= 0 else "▼"
                t.append(f"{bn_ltp:,.2f} ", style=f"bold {p.fg_strong}")
                if bn_chg is not None and bn_pct is not None:
                    t.append(f"{arrow} {bn_chg:+.2f} ({bn_pct:+.2f}%)", style=sign_style(bn_chg))
            else:
                t.append("--.--", style=p.subtle)

        if width >= 130:
            t.append("  │  ", style=p.divider)
            t.append("SENSEX ", style=f"bold {p.muted}")
            sx_q = raw.get("SENSEX") or raw.get("BC_SENSEX") or {}
            sx_ltp = sx_q.get("ltp")
            sx_chg = sx_q.get("rsChange")
            sx_pct = sx_q.get("perChange")
            if sx_ltp is not None:
                arrow = "▲" if (sx_chg or 0) >= 0 else "▼"
                t.append(f"{sx_ltp:,.2f} ", style=f"bold {p.fg_strong}")
                if sx_chg is not None and sx_pct is not None:
                    t.append(f"{arrow} {sx_chg:+.2f} ({sx_pct:+.2f}%)", style=sign_style(sx_chg))
            else:
                t.append("--.--", style=p.subtle)

            # Market breadth mini-badge
            adv = sum(1 for q in raw.values() if isinstance(q, dict) and (q.get("rsChange") or 0) > 0)
            dec = sum(1 for q in raw.values() if isinstance(q, dict) and (q.get("rsChange") or 0) < 0)
            if adv + dec > 0:
                t.append("  │  ", style=p.divider)
                t.append("Breadth ", style=p.subtle)
                t.append(f"▲{adv}", style=f"bold {p.bull}")
                t.append("/", style=p.subtle)
                t.append(f"▼{dec}", style=f"bold {p.bear}")

            t.append(f"  │  {now.strftime('%d %b %Y  %H:%M:%S')} IST", style=p.subtle)
        return t

    # ── Radar panels ──────────────────────────────────────────────────────────
    def render_radar_session(self) -> Text:
        p    = current_palette()
        now  = datetime.now()
        hour = now.hour + now.minute / 60

        def _sess(lo: float, hi: float) -> tuple[str, str]:
            s = "OPEN" if lo <= hour < hi else "CLOSED"
            return s, p.bull if s == "OPEN" else p.subtle

        eq_s, eq_c   = _sess(9.25, 15.5)
        cur_s, cur_c = _sess(9.0, 17.0)
        mcx_s, mcx_c = _sess(9.0, 23.5)

        t = Text()
        t.append("  NSE Equity: ", style=p.muted);  t.append(f"{eq_s}\n",  style=f"bold {eq_c}")
        t.append("  Currency:   ", style=p.muted);  t.append(f"{cur_s}\n", style=f"bold {cur_c}")
        t.append("  MCX:        ", style=p.muted);  t.append(f"{mcx_s}",   style=f"bold {mcx_c}")
        return t

    def render_radar_sectors(self, raw_ticks: dict | None = None) -> Text:
        p = current_palette()
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
                t.append(f"  {name:<11}: ", style=p.muted)
                t.append(f"{pct:+.2f}%\n", style=sign_style(pct))
        if not has_any:
            t.append("  Sectors:    ", style=p.muted)
            t.append("Awaiting feed\n", style=p.subtle)
            t.append("  Market VIX: ", style=p.muted)
            t.append("--.--", style=p.subtle)
        return t

    def render_radar_breadth(self, quotes: Any | None = None) -> Text:
        p = current_palette()
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

        t.append("  Adv / Dec:  ", style=p.muted)
        if advances + declines > 0:
            ratio = (advances / declines) if declines > 0 else float(advances)
            t.append(f"{advances} / {declines}\n", style=f"bold {p.fg_strong}")
            t.append("  A/D Ratio:  ", style=p.muted)
            r_style = f"bold {p.bull}" if ratio >= 1.0 else f"bold {p.bear}"
            t.append(f"{ratio:.2f}\n", style=r_style)
            t.append("  Unchanged:  ", style=p.muted)
            t.append(f"{unchanged}", style=p.subtle)
        else:
            t.append("-- / --\n", style=p.subtle)
            t.append("  A/D Ratio:  ", style=p.muted)
            t.append("--\n", style=p.subtle)
            t.append("  Breadth:    ", style=p.muted)
            t.append("Awaiting ticks", style=p.subtle)
        return t
