"""Portfolio Analytics Engine for SKTUI.

Computes:
- Realized vs Unrealized PnL decomposition
- Sector exposure & attribution (Banking, IT, Auto, Energy, etc.)
- Concentration risk (top holdings % of equity)
- Trade performance metrics: win/loss ratio, profit factor, average win/loss
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from sktui.config import DATA, SECTOR_MAP


@dataclass
class PortfolioSummary:
    """Consolidated portfolio risk and performance summary."""
    total_gross_exposure: float = 0.0
    net_exposure: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    symbol_pnl: dict[str, float] = field(default_factory=dict)
    sector_breakdown: dict[str, float] = field(default_factory=dict)
    sector_pnl: dict[str, float] = field(default_factory=dict)
    product_pnl: dict[str, float] = field(default_factory=dict)
    top_concentrations: list[tuple[str, float]] = field(default_factory=list)
    turnover: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    avg_r_multiple: float = 0.0


class PortfolioAnalytics:
    """Analyzes positions, orders, and market ticks to generate risk attribution."""

    @staticmethod
    def analyze(
        positions: Sequence[Any],
        raw_ticks: dict[str, dict] | None = None,
        orders: Sequence[Any] | None = None,
    ) -> PortfolioSummary:
        ticks = raw_ticks or {}
        realized = 0.0
        unrealized = 0.0
        gross_exp = 0.0
        net_exp = 0.0
        sector_exp: dict[str, float] = {}
        symbol_exp: dict[str, float] = {}
        symbol_pnl: dict[str, float] = {}
        sector_pnl: dict[str, float] = {}
        product_pnl: dict[str, float] = {}
        turnover = 0.0
        trade_count = 0

        wins = 0
        losses = 0
        gross_profit = 0.0
        gross_loss = 0.0

        for p in positions:
            sym = str(getattr(p, "trading_symbol", None) or (p.get("tradingSymbol") if isinstance(p, dict) else ""))
            exch = str(getattr(p, "exchange", None) or (p.get("exchange") if isinstance(p, dict) else "NC"))
            prod = str(getattr(p, "product_type", None) or (p.get("productType") if isinstance(p, dict) else "INVESTMENT")).upper()
            scrip = getattr(p, "scrip_code", None) or (p.get("scripCode") if isinstance(p, dict) else None)
            net_qty = getattr(p, "net_qty", None) or (p.get("netQty") if isinstance(p, dict) else 0)
            avg_price = getattr(p, "avg_price", None) or (p.get("avgPrice") if isinstance(p, dict) else 0.0)
            bpl = getattr(p, "bpl", None) or (p.get("bpl") if isinstance(p, dict) else 0.0)
            buy_qty = p.get("buyQty", 0) if isinstance(p, dict) else 0
            sell_qty = p.get("sellQty", 0) if isinstance(p, dict) else 0
            buy_rate = p.get("buyRate", avg_price) if isinstance(p, dict) else avg_price
            sell_rate = p.get("sellRate", avg_price) if isinstance(p, dict) else avg_price

            try:
                qty = int(net_qty or 0)
                rate = float(avg_price or 0.0)
                pos_realized = float(bpl or 0.0)
                b_q = int(buy_qty or 0)
                s_q = int(sell_qty or 0)
                b_r = float(buy_rate or rate)
                s_r = float(sell_rate or rate)
            except (ValueError, TypeError):
                qty, rate, pos_realized, b_q, s_q, b_r, s_r = 0, 0.0, 0.0, 0, 0, 0.0, 0.0

            realized += pos_realized
            pos_turn = (abs(b_q) * b_r) + (abs(s_q) * s_r)
            if pos_turn == 0.0 and qty != 0:
                pos_turn = abs(qty) * rate
            turnover += pos_turn
            trade_count += 1 if (b_q or s_q or qty) else 0

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
            total_pos_pnl = pos_realized + pos_unrealized

            # Attribution by symbol, sector, and product type
            sector = SECTOR_MAP.get(sym.upper(), "Other")
            sector_exp[sector] = sector_exp.get(sector, 0.0) + abs_val
            symbol_exp[sym] = symbol_exp.get(sym, 0.0) + abs_val
            symbol_pnl[sym] = symbol_pnl.get(sym, 0.0) + total_pos_pnl
            sector_pnl[sector] = sector_pnl.get(sector, 0.0) + total_pos_pnl
            product_pnl[prod] = product_pnl.get(prod, 0.0) + total_pos_pnl

            # Win/loss tracking
            if total_pos_pnl > 0:
                wins += 1
                gross_profit += total_pos_pnl
            elif total_pos_pnl < 0:
                losses += 1
                gross_loss += abs(total_pos_pnl)

        if orders:
            trade_count = max(trade_count, len(orders))

        total_trades = wins + losses
        win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.9 if gross_profit > 0 else 0.0)
        avg_win = (gross_profit / wins) if wins > 0 else 0.0
        avg_loss = (gross_loss / losses) if losses > 0 else 0.0
        avg_r_mult = round(avg_win / avg_loss, 2) if avg_loss > 0 else (round(avg_win / 500.0, 2) if avg_win > 0 else 0.0)

        # Top symbol concentrations
        sorted_symbols = sorted(symbol_exp.items(), key=lambda x: x[1], reverse=True)[:5]
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
            symbol_pnl=symbol_pnl,
            sector_breakdown=sector_exp,
            sector_pnl=sector_pnl,
            product_pnl=product_pnl,
            top_concentrations=top_conc,
            turnover=turnover,
            trade_count=trade_count,
            win_count=wins,
            loss_count=losses,
            win_rate_pct=win_rate,
            profit_factor=profit_factor,
            avg_r_multiple=avg_r_mult,
        )

    @staticmethod
    def export_csv(
        positions: Sequence[Any],
        raw_ticks: dict[str, dict] | None = None,
        orders: Sequence[Any] | None = None,
        output_path: Path | None = None,
    ) -> Path:
        """Export session analytics & P/L breakdown to `~/.local/share/sktui/session_YYYYMMDD.csv`."""
        import csv

        summary = PortfolioAnalytics.analyze(positions, raw_ticks, orders)
        date_str = datetime.now().strftime("%Y%m%d")
        target = output_path or (DATA / f"session_{date_str}.csv")
        target.parent.mkdir(parents=True, exist_ok=True)

        with open(target, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["# SKTUI SESSION ANALYTICS REPORT", datetime.now().isoformat(timespec="seconds")])
            writer.writerow([
                "RealizedPnL", "UnrealizedPnL", "TotalPnL", "GrossExposure",
                "NetExposure", "Turnover", "TradeCount", "WinRatePct", "ProfitFactor", "AvgRMultiple"
            ])
            writer.writerow([
                f"{summary.realized_pnl:.2f}",
                f"{summary.unrealized_pnl:.2f}",
                f"{summary.total_pnl:.2f}",
                f"{summary.total_gross_exposure:.2f}",
                f"{summary.net_exposure:.2f}",
                f"{summary.turnover:.2f}",
                summary.trade_count,
                f"{summary.win_rate_pct:.1f}",
                f"{summary.profit_factor:.2f}",
                f"{summary.avg_r_multiple:.2f}",
            ])
            writer.writerow([])
            writer.writerow(["Symbol", "Sector", "Exchange", "Product", "NetQty", "AvgPrice", "BookedPnL", "TotalPnL"])
            for p in positions:
                sym = str(getattr(p, "trading_symbol", None) or (p.get("tradingSymbol") if isinstance(p, dict) else ""))
                exch = str(getattr(p, "exchange", None) or (p.get("exchange") if isinstance(p, dict) else "NC"))
                prod = str(getattr(p, "product_type", None) or (p.get("productType") if isinstance(p, dict) else "INVESTMENT"))
                net_q = getattr(p, "net_qty", None) or (p.get("netQty") if isinstance(p, dict) else 0)
                avg_p = getattr(p, "avg_price", None) or (p.get("avgPrice") if isinstance(p, dict) else 0.0)
                bpl = getattr(p, "bpl", None) or (p.get("bpl") if isinstance(p, dict) else 0.0)
                sec = SECTOR_MAP.get(sym.upper(), "Other")
                tot_sym_pnl = summary.symbol_pnl.get(sym, float(bpl or 0.0))
                writer.writerow([sym, sec, exch, prod, net_q, avg_p, bpl, f"{tot_sym_pnl:.2f}"])

        return target
