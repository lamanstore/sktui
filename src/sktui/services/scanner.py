"""Real-Time Market Scanner Service for SKTUI.

Scans the centralized QuoteStore and active Watchlist for:
- Top Gainers / Losers (% change)
- High Volume Spikes
- Intraday Range Breakouts (near Day High / Day Low)
- VWAP Momentum & Trend Bias
"""
from __future__ import annotations

from typing import Any, Sequence

from sktui.state.quote_store import QuoteStore


class MarketScanner:
    """Analytical market scanner operating over QuoteStore state."""

    def __init__(self, quote_store: QuoteStore, watch: Sequence[dict] | None = None) -> None:
        self.quote_store = quote_store
        self.watch = list(watch) if watch else []

    def _extract_candidates(self) -> list[dict[str, Any]]:
        """Extract all candidate quotes with normalized analytics fields."""
        candidates: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        # 1. Gather all tracked watchlist scrips
        for item in self.watch:
            sym = str(item.get("tradingSymbol") or item.get("symbol") or "")
            exch = str(item.get("exchange") or "NC")
            code = str(item.get("scripCode") or "")
            key = f"{exch}{code}"
            seen_keys.add(key)

            quote = self.quote_store.get(key)
            candidates.append(self._normalize_candidate(sym, exch, code, quote, item))

        # 2. Add any additional live symbols in QuoteStore not in watch
        for key in self.quote_store.keys():
            if key in seen_keys:
                continue
            quote = self.quote_store.get(key)
            sym = str(quote.get("tradingSymbol") or quote.get("tsym") or key)
            exch = str(quote.get("exchangeCode") or quote.get("exchange") or "NC")
            code = str(quote.get("scripCode") or "")
            candidates.append(self._normalize_candidate(sym, exch, code, quote, {}))

        return candidates

    def _normalize_candidate(
        self, sym: str, exch: str, code: str, quote: dict, meta: dict
    ) -> dict[str, Any]:
        """Normalize raw quote fields into standardized scanner metrics."""
        ltp = float(quote.get("ltp") or quote.get("lastTradedPrice") or meta.get("price") or 0.0)
        open_p = float(quote.get("open") or quote.get("openPrice") or ltp or 1.0)
        high_p = float(quote.get("high") or quote.get("highPrice") or max(ltp, open_p))
        low_p = float(quote.get("low") or quote.get("lowPrice") or min(ltp, open_p))
        close_p = float(quote.get("close") or quote.get("closePrice") or open_p)

        chg = float(quote.get("rsChange") or quote.get("change") or (ltp - close_p if ltp and close_p else 0.0))
        pct = float(quote.get("perChange") or quote.get("pChange") or ((chg / close_p * 100.0) if close_p > 0 else 0.0))
        vol = float(quote.get("qty") or quote.get("volume") or quote.get("vol") or 0.0)
        bid = float(quote.get("bidPrice") or quote.get("bid") or 0.0)
        ask = float(quote.get("offPrice") or quote.get("ask") or 0.0)

        # Intraday range & position %
        range_span = max(0.01, high_p - low_p)
        pct_of_range = max(0.0, min(100.0, ((ltp - low_p) / range_span * 100.0)))

        # VWAP / Average Traded Price
        vwap = float(quote.get("atp") or quote.get("vwap") or ((high_p + low_p + close_p) / 3.0))
        vwap_dist = ((ltp - vwap) / vwap * 100.0) if vwap > 0 else 0.0

        return {
            "symbol": sym,
            "exchange": exch,
            "scripCode": code,
            "ltp": ltp,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "change": chg,
            "pctChange": pct,
            "volume": vol,
            "bid": bid,
            "ask": ask,
            "pctOfRange": pct_of_range,
            "vwap": vwap,
            "vwapDist": vwap_dist,
            "spread": max(0.0, ask - bid) if ask > 0 and bid > 0 else 0.0,
        }

    # ── Scanner Queries ───────────────────────────────────────────────────────

    def scan_top_movers(self, limit: int = 15) -> list[dict[str, Any]]:
        """Rank symbols by absolute percentage move (biggest gainers & losers)."""
        cands = self._extract_candidates()
        cands.sort(key=lambda x: abs(x["pctChange"]), reverse=True)
        return cands[:limit]

    def scan_volume_spikes(self, limit: int = 15) -> list[dict[str, Any]]:
        """Rank symbols with highest trading volume activity."""
        cands = self._extract_candidates()
        cands.sort(key=lambda x: x["volume"], reverse=True)
        return cands[:limit]

    def scan_breakouts(self, limit: int = 15) -> list[dict[str, Any]]:
        """Symbols near Day High (>=90% of day range) or Day Low (<=10% of day range)."""
        cands = self._extract_candidates()
        breakouts = [
            c for c in cands
            if (c["pctOfRange"] >= 90.0 or c["pctOfRange"] <= 10.0) and c["ltp"] > 0
        ]
        breakouts.sort(
            key=lambda x: abs(x["pctOfRange"] - 50.0), reverse=True
        )
        return breakouts[:limit] if breakouts else cands[:limit]

    def scan_vwap_trend(self, limit: int = 15) -> list[dict[str, Any]]:
        """Rank symbols by deviation from VWAP (strong trend leaders)."""
        cands = self._extract_candidates()
        cands.sort(key=lambda x: abs(x["vwapDist"]), reverse=True)
        return cands[:limit]
