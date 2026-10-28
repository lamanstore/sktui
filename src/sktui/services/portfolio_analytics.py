"""Portfolio Analytics Engine for SKTUI.

Computes:
- Realized vs Unrealized PnL decomposition
- Sector exposure & attribution (Banking, IT, Auto, Energy, etc.)
- Concentration risk (top holdings % of equity)
- Trade performance metrics: win/loss ratio, profit factor, average win/loss
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

# Canonical Sector Mapping for Common Indian Equities
SECTOR_MAP: dict[str, str] = {
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "SBIN": "Banking",
    "KOTAKBANK": "Banking",
    "AXISBANK": "Banking",
    "TCS": "IT",
    "INFY": "IT",
    "WIPRO": "IT",
    "HCLTECH": "IT",
    "TECHM": "IT",
    "RELIANCE": "Energy",
    "ONGC": "Energy",
    "NTPC": "Energy",
    "POWERGRID": "Energy",
    "BPCL": "Energy",
    "IOC": "Energy",
    "TATAMOTORS": "Auto",
    "M&M": "Auto",
    "MARUTI": "Auto",
    "BAJAJ-AUTO": "Auto",
    "HEROMOTOCO": "Auto",
    "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals",
    "HINDALCO": "Metals",
    "COALINDIA": "Metals",
    "ITC": "FMCG",
    "HINDUNILVR": "FMCG",
    "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG",
    "SUNPHARMA": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "DIVISLAB": "Pharma",
    "LT": "Infrastructure",
    "BHARTIARTL": "Telecom",
}


@dataclass
class PortfolioSummary:
    """Consolidated portfolio risk and performance summary."""
    total_gross_exposure: float = 0.0
    net_exposure: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    sector_breakdown: dict[str, float] = field(default_factory=dict)
    top_concentrations: list[tuple[str, float]] = field(default_factory=list)
    win_count: int = 0
    loss_count: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0


class PortfolioAnalytics:
    """Analyzes positions, orders, and market ticks to generate risk attribution."""

    @staticmethod
    def analyze(
        positions: Sequence[Any],
        raw_ticks: dict[str, dict] | None = None,
    ) -> PortfolioSummary:
        ticks = raw_ticks or {}
        realized = 0.0
        unrealized = 0.0
        gross_exp = 0.0
        net_exp = 0.0
        sector_exp: dict[str, float] = {}
        symbol_exp: dict[str, float] = {}

        wins = 0
        losses = 0
        gross_profit = 0.0
        gross_loss = 0.0

        for p in positions:
            sym = getattr(p, "trading_symbol", None) or (p.get("tradingSymbol") if isinstance(p, dict) else "")
            exch = getattr(p, "exchange", None) or (p.get("exchange") if isinstance(p, dict) else "NC")
            scrip = getattr(p, "scrip_code", None) or (p.get("scripCode") if isinstance(p, dict) else None)
            net_qty = getattr(p, "net_qty", None) or (p.get("netQty") if isinstance(p, dict) else 0)
            avg_price = getattr(p, "avg_price", None) or (p.get("avgPrice") if isinstance(p, dict) else 0.0)
            bpl = getattr(p, "bpl", None) or (p.get("bpl") if isinstance(p, dict) else 0.0)

            try:
                qty = int(net_qty or 0)
                rate = float(avg_price or 0.0)
                pos_realized = float(bpl or 0.0)
            except (ValueError, TypeError):
                qty, rate, pos_realized = 0, 0.0, 0.0

            realized += pos_realized

            # Get latest market price for unrealized PnL
            feed_key = f"{exch}{scrip}" if scrip else ""
            ltp = rate
            if feed_key and feed_key in ticks and ticks[feed_key].get("ltp"):
                try:
                    ltp = float(ticks[feed_key]["ltp"])
                except Exception:
                    ltp = rate

            pos_val = qty * ltp
            abs_val = abs(pos_val)
            gross_exp += abs_val
            net_exp += pos_val

            pos_unrealized = qty * (ltp - rate) if qty != 0 else 0.0
            unrealized += pos_unrealized

            # Sector attribution
            sector = SECTOR_MAP.get(sym.upper(), "Other")
            sector_exp[sector] = sector_exp.get(sector, 0.0) + abs_val
            symbol_exp[sym] = symbol_exp.get(sym, 0.0) + abs_val

            # Win/loss tracking
            total_pos_pnl = pos_realized + pos_unrealized
            if total_pos_pnl > 0:
                wins += 1
                gross_profit += total_pos_pnl
            elif total_pos_pnl < 0:
                losses += 1
                gross_loss += abs(total_pos_pnl)

        total_trades = wins + losses
        win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.9 if gross_profit > 0 else 0.0)

        # Top 3 symbol concentrations
        sorted_symbols = sorted(symbol_exp.items(), key=lambda x: x[1], reverse=True)[:3]
        top_conc = [
            (sym, (val / gross_exp * 100.0) if gross_exp > 0 else 0.0)
            for sym, val in sorted_symbols
        ]

        return PortfolioSummary(
            total_gross_exposure=gross_exp,
            net_exposure=net_exp,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_pnl=realized + unrealized,
            sector_breakdown=sector_exp,
            top_concentrations=top_conc,
            win_count=wins,
            loss_count=losses,
            win_rate_pct=win_rate,
            profit_factor=profit_factor,
        )
