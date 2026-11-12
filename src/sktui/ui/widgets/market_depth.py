"""Level-2 Market Depth (Order Book) Ladder Widget for SKTUI."""
from __future__ import annotations

from typing import Any
from rich.text import Text
from textual.widgets import Static

from sktui.themes import current_palette
from sktui.utils import compact_number, safe_float, scrip_label


class MarketDepthWidget(Static):
    """Displays 5-level Bid/Ask order book depth ladder with liquidity balance indicator."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.item: dict | None = None
        self.quote: dict = {}
        self.depth: dict[str, Any] = {}

    def update_depth_context(
        self,
        item: dict | None,
        quote: dict | None = None,
        depth: dict[str, Any] | None = None,
        width: int = 60,
    ) -> None:
        self.item = item
        if quote is not None:
            self.quote = quote
        if depth is not None:
            self.depth = depth
        if getattr(self, "is_mounted", False):
            try:
                self.update(self.render_content(width=width))
            except Exception:
                pass

    def render_content(self, width: int = 60) -> Text:
        p = current_palette()
        t = Text()

        if not self.item:
            t.append("  [ L2 Market Depth Ladder — Select instrument in Watchlist ]", style=p.subtle)
            return t

        sym = scrip_label(self.item)
        exch = str(self.item.get("exchange", "NC"))
        ltp = safe_float(self.quote.get("ltp")) or 0.0

        bids = self.depth.get("bids", [])
        asks = self.depth.get("asks", [])
        tot_b = self.depth.get("total_bid_qty", 0)
        tot_a = self.depth.get("total_ask_qty", 0)
        spread = self.depth.get("spread", 0.0)
        spread_bps = (spread / ltp * 10000.0) if ltp > 0 else 0.0
        imbal = self.depth.get("imbalance_pct", 0.0)

        # ── Header ──
        t.append(" DEPTH L2 ", style=f"bold {p.on_primary} on {p.primary}")
        t.append(f" {sym} ", style=f"bold {p.fg_strong}")
        t.append(f"[{exch}]  ", style=p.subtle)
        t.append(f"LTP ₹{ltp:,.2f}  ·  ", style=p.fg)
        t.append("Spread: ", style=p.muted)
        t.append(f"₹{spread:,.2f} ({spread_bps:.1f} bps)\n", style=p.warn if spread_bps > 15 else p.bull)

        # ── Ladder Table Columns ──
        # Left: Qty (w8) Price (w10) | Right: Price (w10) Qty (w8)
        t.append("    BID QTY      BID PRICE  │  ASK PRICE      ASK QTY    \n", style=f"bold {p.subtle}")

        max_vol = max(
            [q for _, q in bids] + [q for _, q in asks] + [1]
        )

        for i in range(5):
            # Bid side
            if i < len(bids):
                bp, bq = bids[i]
                b_bar_len = min(6, max(1, int((bq / max_vol) * 6)))
                b_bars = "█" * b_bar_len
                b_str = f"{compact_number(bq):>8}  ₹{bp:>9,.2f}"
                t.append(f"{b_str} ", style=p.bull)
                t.append(f"{b_bars:<6}", style=f"dim {p.bull}")
            else:
                t.append("       --          --.     --    ", style=p.subtle)

            t.append(" │ ", style=p.subtle)

            # Ask side
            if i < len(asks):
                ap, aq = asks[i]
                a_bar_len = min(6, max(1, int((aq / max_vol) * 6)))
                a_bars = "█" * a_bar_len
                a_str = f"₹{ap:<9,.2f}  {compact_number(aq):>8}"
                t.append(f"{a_bars:>6} ", style=f"dim {p.bear}")
                t.append(f"{a_str}", style=p.bear)
            else:
                t.append("   --.          --       --", style=p.subtle)
            t.append("\n")

        # ── Total and Liquidity Imbalance Bar ──
        t.append("─" * min(58, max(36, width - 4)) + "\n", style=p.divider)
        t.append(f"Total: {compact_number(tot_b):<10}          │  Total: {compact_number(tot_a):<10}\n", style=p.muted)

        # Buyer vs Seller Pressure Bar (e.g., 20 blocks)
        tot_both = tot_b + tot_a
        b_pct = (tot_b / tot_both * 100.0) if tot_both > 0 else 50.0
        s_pct = 100.0 - b_pct
        b_blocks = int(b_pct / 5.0)
        s_blocks = 20 - b_blocks
        t.append("Flow: ", style=p.muted)
        t.append(f"{b_pct:.0f}% Buy ", style=f"bold {p.bull}")
        t.append("[" + ("█" * b_blocks), style=p.bull)
        t.append(("█" * s_blocks) + "]", style=p.bear)
        t.append(f" {s_pct:.0f}% Sell", style=f"bold {p.bear}")

        return t
