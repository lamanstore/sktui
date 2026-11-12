#!/usr/bin/env python3
"""SKTUI - Professional Terminal Trading CLI for Mirae Asset Sharekhan API."""
from __future__ import annotations

import argparse
import os

from textual.app import App
from textual.binding import Binding

from sktui import api
from sktui.config import (
    C_AMBER, C_BG, C_BORDER, C_CYAN, C_DIM, C_GREEN, C_MUTED, C_PANEL, C_RED,
    C_SUBTLE, C_TEXT, C_DARK, C_NAVY, C_TEAL, CASH, CONF, CONFIG_FILE, DATA,
    EXCH_NAMES, INTERVALS, INTERVAL_LABELS, PRODUCTS, SESSION_FILE,
    SLASH_COMMANDS, VALIDITIES, WATCH_FILE,
)
from sktui.screens.login import LOGIN_LOGO, LoginScreen
from sktui.screens.main import MainScreen
from sktui.screens.modals import ThemeModal
from sktui.styles import CSS
from sktui.themes import (
    DEFAULT_THEME, SKTUI_THEMES, load_configured_theme, save_configured_theme,
    sync_palette_from_app,
)
from sktui.utils import (
    build_order, cell, dec, expiry_key, fill_table, fmt, get, human, is_open_order,
    norm_expiry, normalize_scrip, order_summary, read_json, scrip_label, sign_style,
    strike_str, write_private,
)


class SKApp(App):
    TITLE     = "SKTUI  \u00b7  Sharekhan Terminal"
    SUB_TITLE = "Mirae Asset  \u00b7  Professional Trading CLI"
    CSS       = CSS

    BINDINGS = [
        Binding("ctrl+t", "open_themes", "Theme"),
    ]

    # Responsive size classes applied to every Screen on resize (see styles.py).
    HORIZONTAL_BREAKPOINTS = [(0, "-xs"), (90, "-sm"), (120, "-md"), (160, "-lg"), (200, "-xl")]
    VERTICAL_BREAKPOINTS   = [(0, "-short"), (30, "-medium"), (45, "-tall")]

    def __init__(
        self,
        paper: bool = False,
        initial_theme: str | None = None,
        auto_paper: bool = False,
    ) -> None:
        super().__init__()
        self.paper       = paper
        self.auto_paper  = auto_paper
        self.client:     api.Client | None = None
        self.raw_ticks:  dict[str, dict]   = {}
        self.quotes:     object | None     = None
        self.enable_feed = True
        self._theme_ready = False

        for custom_theme in SKTUI_THEMES:
            self.register_theme(custom_theme)

        raw_target = (initial_theme or load_configured_theme(CONFIG_FILE)).strip()
        if raw_target not in self.available_themes and f"sktui-{raw_target}" in self.available_themes:
            raw_target = f"sktui-{raw_target}"
        target = raw_target if raw_target in self.available_themes else DEFAULT_THEME
        self.theme = target
        sync_palette_from_app(self)
        self._theme_ready = True

    def on_mount(self) -> None:
        sync_palette_from_app(self)
        if self.auto_paper and self.paper:
            from datetime import date
            sess = {
                "date": str(date.today()),
                "api_key": "PAPER_SANDBOX_KEY",
                "vendor": "",
                "access_token": "PAPER_SANDBOX_TOKEN",
                "customer_id": "PAPER-01",
                "login_id": "PAPER_TRADER",
                "exchanges": ["NC", "BC", "NF", "RN", "MX"],
                "full_name": "PAPER SANDBOX DESK",
            }
            self.client = api.Client(
                sess["api_key"], sess["access_token"], sess["customer_id"],
                sess.get("login_id", ""), sess.get("vendor", ""),
                sess.get("exchanges", []), sess.get("full_name", ""), True,
            )
            self.push_screen(MainScreen())
        else:
            self.push_screen(LoginScreen())

    def watch_theme(self, theme_name: str) -> None:
        """Sync Rich color palette, persist selection, and refresh all mounted screens."""
        sync_palette_from_app(self)
        if getattr(self, "_theme_ready", False) and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                top_scr = self.screen
            except Exception:
                top_scr = None
            if not isinstance(top_scr, ThemeModal):
                save_configured_theme(theme_name, CONFIG_FILE)
        for scr in list(self.screen_stack):
            if getattr(scr, "is_mounted", False) and hasattr(scr, "on_theme_changed"):
                try:
                    scr.on_theme_changed()
                except Exception:
                    pass

    def action_open_themes(self) -> None:
        """Open the live-preview workstation Theme Studio modal."""
        try:
            if not isinstance(self.screen, ThemeModal):
                self.push_screen(ThemeModal())
        except Exception:
            self.push_screen(ThemeModal())


# ── CLI Subcommand Handlers (M1 Foundation / Future Service Entrypoints) ─────

class MinConfAction(argparse.Action):
    """Argparse action ensuring min_conf and min_confidence remain synchronized."""
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, "min_conf", values)
        setattr(namespace, "min_confidence", values)


def _print_comparison_table(console: Any, ranked: list[dict[str, Any]], rank_by: str) -> None:
    from rich.table import Table

    t_cmp = Table(title=f"Multi-Stock Technical & Quant Ranking (Ranked by {rank_by.capitalize()})", border_style="cyan")
    t_cmp.add_column("Rank", justify="center", style="bold")
    t_cmp.add_column("Symbol", style="bold", no_wrap=True)
    t_cmp.add_column("LTP (₹)", justify="right", no_wrap=True)
    t_cmp.add_column("Return %", justify="right", no_wrap=True)
    t_cmp.add_column("Vol %", justify="right", no_wrap=True)
    t_cmp.add_column("Sharpe", justify="right", no_wrap=True)
    t_cmp.add_column("Sortino", justify="right", no_wrap=True)
    t_cmp.add_column("MaxDD %", justify="right", no_wrap=True)
    t_cmp.add_column("RSI", justify="right", no_wrap=True)
    t_cmp.add_column("Signal", justify="center", no_wrap=True)

    for item in ranked:
        i = item.get("rank", 1)
        sym = item.get("symbol", "")
        ltp = item.get("ltp", 0.0)
        ret = item.get("return_pct", 0.0)
        vol = item.get("volatility_pct", 0.0)
        sharpe = item.get("sharpe", 0.0)
        sortino = item.get("sortino", 0.0)
        maxdd = item.get("max_drawdown_pct", 0.0)
        rsi_val = item.get("rsi", 50.0)
        sig = item.get("signal", "NEUTRAL")

        sig_style = "bold green" if "BUY" in sig else ("bold red" if "SELL" in sig else "yellow")
        rank_style = "bold gold1" if i == 1 else "white"

        t_cmp.add_row(
            f"#{i}",
            sym,
            f"₹{ltp:,.2f}",
            f"{ret:+.2f}%",
            f"{vol:.2f}%",
            f"{sharpe:.2f}",
            f"{sortino:.2f}",
            f"{maxdd:.2f}%",
            f"{rsi_val:.1f}",
            f"[{sig_style}]{sig}[/]",
            style=rank_style if i == 1 else None,
        )

    console.print(t_cmp)


def handle_analyze(args: argparse.Namespace, logger: Any = None) -> int:
    """Execute headless technical and quantitative analysis for a symbol."""
    import sys
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from sktui.screens.modals import sparkline
    from sktui.services.stock_analyzer import StockAnalyzer

    symbol = getattr(args, "symbol", "") or ""
    if not symbol.strip():
        print("[!] Error: Symbol must not be empty.", file=sys.stderr)
        return 1

    clean_sym = symbol.strip().upper()
    period = getattr(args, "period", "1y") or "1y"
    compare_arg = getattr(args, "compare", None)

    analyzer = StockAnalyzer()
    analysis = analyzer.analyze_stock(clean_sym, period=period)
    metrics = analysis.metrics
    sig = analysis.signal

    console = Console(width=160)

    # 1. Header with Signal Chip & Sparkline
    sig_action = sig.action.upper()
    badge_style = "bold white on green" if "BUY" in sig_action else ("bold white on red" if "SELL" in sig_action else "bold black on yellow")
    ltp = analysis.current_price
    chg = analysis.change
    pct = analysis.change_pct
    chg_str = f"{chg:+.2f} ({pct:+.2f}%)"

    closes = [analysis.current_price]
    bars = analyzer._fetch_bars(clean_sym, period)
    if bars and "close" in bars:
        closes = bars["close"]
    spk = sparkline(closes, width=40)

    hdr_text = Text()
    hdr_text.append(f"  {clean_sym}  ", style="bold white")
    hdr_text.append(f"₹{ltp:,.2f}  ", style="bold cyan")
    hdr_text.append(f"{chg_str}   ", style="bold green" if chg >= 0 else "bold red")
    hdr_text.append(f" [{sig_action}] ", style=badge_style)
    hdr_text.append(f"  Confidence: {sig.confidence_pct:.1f}%\n", style="bold yellow")
    hdr_text.append(f"  Trend Sparkline : {spk}\n", style="cyan")
    hdr_text.append(f"  Signal Rationale: {', '.join(sig.reasoning) or 'Normal market equilibrium'}", style="dim")

    console.print(Panel(hdr_text, title=f"[bold]SKTUI Analysis — {clean_sym}[/bold]", border_style="cyan"))

    # 2. Technical Indicators Table
    t_ind = Table(title="Technical Indicators Summary", border_style="dim")
    t_ind.add_column("Indicator", style="bold")
    t_ind.add_column("Value", justify="right")
    t_ind.add_column("Status / Condition")
    t_ind.add_column("Interpretation")

    t_ind.add_row("RSI (14)", f"{analysis.rsi:.1f}", analysis.rsi_condition, "Momentum")
    t_ind.add_row("MACD (12, 26, 9)", f"{analysis.macd_line:+.2f} / {analysis.macd_signal:+.2f}", analysis.macd_condition, "Trend Convergence")
    stoch_k_str = f"{analysis.stoch_k:.1f}" if analysis.stoch_k is not None else "N/A"
    stoch_d_str = f"{analysis.stoch_d:.1f}" if analysis.stoch_d is not None else "N/A"
    t_ind.add_row("Stochastic (%K, %D)", f"{stoch_k_str} / {stoch_d_str}", analysis.stoch_condition, "Oscillator")
    adx_str = f"{analysis.adx:.1f}" if analysis.adx is not None else "N/A"
    pdi_str = f"{analysis.plus_di:.1f}" if analysis.plus_di is not None else "N/A"
    mdi_str = f"{analysis.minus_di:.1f}" if analysis.minus_di is not None else "N/A"
    t_ind.add_row("ADX (14)", f"{adx_str} (+DI: {pdi_str}, -DI: {mdi_str})", analysis.adx_condition, "Trend Strength")
    bb_m_str = f"₹{analysis.bb_mid:,.1f}" if analysis.bb_mid is not None else "N/A"
    t_ind.add_row("Bollinger Bands (20, 2)", f"Mid: {bb_m_str} (BW: {analysis.bb_bandwidth:.2f})", analysis.bb_condition, "Volatility Envelope")
    t_ind.add_row("MA Trend Alignment", f"SMA 20/50: {analysis.ma_trend}", analysis.ma_slope_condition, "Trend Baseline")

    console.print(t_ind)

    # 3. Quantitative Risk & Performance Metrics Table
    t_q = Table(title="Quantitative Risk & Performance Analytics", border_style="dim")
    t_q.add_column("Metric", style="bold")
    t_q.add_column("Value", justify="right")
    t_q.add_column("Benchmark / Horizon", justify="center")
    t_q.add_column("Assessment")

    t_q.add_row("Annualized Return", f"{metrics.mean_return * 100.0:+.2f}%", "Annual (252d)", "Profitable" if metrics.mean_return > 0 else "Negative")
    t_q.add_row("Annualized Volatility", f"{metrics.annual_volatility * 100.0:.2f}%", "Annual (252d)", "Moderate" if metrics.annual_volatility < 0.30 else "High")
    t_q.add_row("Sharpe Ratio", f"{metrics.sharpe_ratio:.2f}", "Rf = 5.0%", "Institutional Quality" if metrics.sharpe_ratio >= 1.0 else "Sub-optimal")
    t_q.add_row("Sortino Ratio", f"{metrics.sortino_ratio:.2f}", "Downside Deviation", "Strong" if metrics.sortino_ratio >= 1.5 else "Moderate")
    t_q.add_row("Maximum Drawdown", f"{metrics.max_drawdown * 100.0:.2f}%", f"{metrics.drawdown_duration} bars underwater", "Controlled" if abs(metrics.max_drawdown) < 0.20 else "High Risk")
    t_q.add_row("Value-at-Risk (95% 1-day)", f"{metrics.var_95 * 100.0:.2f}%", "Historical Percentile", "Normal Tail Risk")
    t_q.add_row("Value-at-Risk (99% 1-day)", f"{metrics.var_99 * 100.0:.2f}%", "Historical Percentile", "Extreme Loss Ceiling")
    t_q.add_row("Conditional VaR (CVaR 95%)", f"{metrics.cvar_95 * 100.0:.2f}%", "Expected Shortfall", "Tail Severity")
    t_q.add_row("Beta (vs Nifty 50)", f"{metrics.beta:.2f}", "Market Benchmark", "Aggressive" if metrics.beta > 1.0 else "Defensive")
    t_q.add_row("Alpha (Jensen's)", f"{metrics.alpha * 100.0:+.2f}%", "Annual Excess", "Outperforming" if metrics.alpha > 0 else "Underperforming")
    t_q.add_row("R-Squared (R²)", f"{metrics.r_squared:.2f}", "Market Correlation", "High Fit" if metrics.r_squared > 0.6 else "Idiosyncratic")

    console.print(t_q)

    # 4. Optional Comparison Sub-table
    if compare_arg:
        compare_syms = [s.strip().upper() for s in compare_arg.split(",") if s.strip()]
        if compare_syms:
            all_syms = [clean_sym] + [s for s in compare_syms if s != clean_sym]
            ranked = analyzer.compare(all_syms, rank_by="sharpe", period=period)
            _print_comparison_table(console, ranked, rank_by="sharpe")

    if logger:
        logger.info("Executed CLI analyze for %s (period=%s)", clean_sym, period)
    return 0


def handle_compare(args: argparse.Namespace, logger: Any = None) -> int:
    """Execute headless multi-stock comparison ranking."""
    import sys
    from rich.console import Console
    from sktui.services.stock_analyzer import StockAnalyzer

    raw_symbols = getattr(args, "symbols", [])
    symbols: list[str] = []
    if isinstance(raw_symbols, str):
        symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
    elif isinstance(raw_symbols, (list, tuple)):
        for item in raw_symbols:
            for s in str(item).split(","):
                if s.strip():
                    symbols.append(s.strip().upper())

    if not symbols:
        print("[!] Error: At least one symbol must be provided for comparison.", file=sys.stderr)
        return 1

    rank_by = getattr(args, "rank_by", "sharpe") or "sharpe"
    period = getattr(args, "period", "1y") or "1y"

    analyzer = StockAnalyzer()
    ranked = analyzer.compare(symbols, rank_by=rank_by, period=period)

    console = Console(width=160)
    _print_comparison_table(console, ranked, rank_by=rank_by)

    if logger:
        logger.info("Executed CLI compare for %d symbols (rank_by=%s)", len(symbols), rank_by)
    return 0


def handle_pairs(args: argparse.Namespace, logger: Any = None) -> int:
    """Execute headless cointegrated pair trading screening."""
    import json
    import sys
    from rich.console import Console
    from rich.table import Table
    from sktui.config import SECTOR_MAP
    from sktui.services.pair_screener import screen_pairs
    from sktui.services.stock_analyzer import StockAnalyzer

    sector = getattr(args, "sector", None)
    min_corr = getattr(args, "min_corr", 0.70)
    raw_symbols = getattr(args, "symbols", None)
    output_path = getattr(args, "output", None)
    output_json = getattr(args, "json", False)

    if not (0.0 <= min_corr <= 1.0):
        print(f"[!] Error: min-corr must be between 0.0 and 1.0 (got {min_corr}).", file=sys.stderr)
        return 1

    # 1. Resolve Universe Symbols
    target_symbols: list[str] = []
    if raw_symbols:
        if isinstance(raw_symbols, str):
            target_symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
        elif isinstance(raw_symbols, (list, tuple)):
            for item in raw_symbols:
                for s in str(item).split(","):
                    if s.strip():
                        target_symbols.append(s.strip().upper())
    elif sector:
        sec_clean = sector.strip().lower()
        target_symbols = [s for s, sec in SECTOR_MAP.items() if sec.lower() == sec_clean]
    else:
        target_symbols = list(SECTOR_MAP.keys())[:15]

    if len(target_symbols) < 2:
        print("[!] Error: At least 2 symbols required for pair screening.", file=sys.stderr)
        return 1

    # 2. Fetch Historical Closes
    analyzer = StockAnalyzer()
    universe_prices: dict[str, list[float]] = {}
    for sym in target_symbols:
        bars = analyzer._fetch_bars(sym, period="1y")
        if bars and "close" in bars and len(bars["close"]) >= 30:
            universe_prices[sym] = bars["close"]

    # 3. Run Pair Screener
    results = screen_pairs(universe_prices, min_correlation=min_corr)

    # 4. JSON Export or Console Table
    if output_json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return 0

    console = Console(width=160)
    t = Table(
        title=f"Statistical Arbitrage Pair Screening (Sector: {sector or 'ALL'}, Min Corr: {min_corr:.2f})",
        border_style="cyan",
    )
    t.add_column("Pair", style="bold", no_wrap=True)
    t.add_column("Sector", style="dim")
    t.add_column("Corr (ρ)", justify="right")
    t.add_column("Stab (Δρ)", justify="right")
    t.add_column("Hedge (β)", justify="right")
    t.add_column("ADF Stat", justify="right")
    t.add_column("p-value", justify="right")
    t.add_column("Cointegrated", justify="center")
    t.add_column("Half-Life", justify="right")
    t.add_column("Z-Score", justify="right")
    t.add_column("Signal", justify="center")

    for r in results:
        pair_name = f"{r.stock_a} / {r.stock_b}"
        sec = r.sector or SECTOR_MAP.get(r.stock_a, SECTOR_MAP.get(r.stock_b, "Equities"))
        coint_badge = "[bold green]✓ YES[/]" if r.is_cointegrated else "[dim]✗ NO[/]"
        z_style = "bold red" if r.current_zscore >= 2.0 else ("bold green" if r.current_zscore <= -2.0 else "white")
        sig_style = (
            "bold green" if "LONG" in r.signal
            else ("bold red" if "SHORT" in r.signal
            else ("yellow" if "EXIT" in r.signal else "dim"))
        )
        t.add_row(
            pair_name,
            sec,
            f"{r.correlation:.3f}",
            f"{r.correlation_stability:.3f}",
            f"{r.beta:.3f}",
            f"{r.adf_statistic:.2f}",
            f"{r.p_value:.4f}",
            coint_badge,
            f"{r.half_life_days:.1f}d",
            f"[{z_style}]{r.current_zscore:+.2f}[/]",
            f"[{sig_style}]{r.signal}[/]",
        )

    console.print(t)
    if not results:
        console.print("[dim]  No pairs passed correlation, cointegration, and half-life filters.[/dim]")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            if output_path.endswith(".json"):
                json.dump([r.to_dict() for r in results], f, indent=2)
            else:
                f.write(str(t))
        console.print(f"[dim]Results saved to {output_path}[/dim]")

    if logger:
        logger.info("Executed CLI pairs (found %d pairs)", len(results))
    return 0


def handle_spread(args: argparse.Namespace, logger: Any = None) -> int:
    """Execute headless pair spread and Z-score analysis."""
    import json
    import statistics
    import sys
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from sktui.services.pair_screener import (
        adf_test,
        calculate_position_sizing,
        calculate_zscore_signal,
        compute_half_life,
        compute_ols_hedge_ratio,
    )
    from sktui.services.stock_analyzer import StockAnalyzer

    stock_a = (getattr(args, "stock_a", "") or "").strip().upper()
    stock_b = (getattr(args, "stock_b", "") or "").strip().upper()
    lookback = getattr(args, "lookback", 90) or 90
    capital = getattr(args, "capital", 100000.0) or 100000.0
    output_path = getattr(args, "output", None)
    output_json = getattr(args, "json", False)

    if not stock_a or not stock_b:
        print("[!] Error: Both --stock-a and --stock-b are required.", file=sys.stderr)
        return 1
    if stock_a == stock_b:
        print("[!] Error: Stock A and Stock B must be distinct tickers.", file=sys.stderr)
        return 1

    # Fetch Prices
    analyzer = StockAnalyzer()
    bars_a = analyzer._fetch_bars(stock_a, period="1y")
    bars_b = analyzer._fetch_bars(stock_b, period="1y")
    if not bars_a or not bars_b or len(bars_a.get("close", [])) < 30 or len(bars_b.get("close", [])) < 30:
        print(f"[!] Error: Insufficient historical data for {stock_a} and {stock_b}.", file=sys.stderr)
        return 1

    p_a = bars_a["close"][-lookback:]
    p_b = bars_b["close"][-lookback:]
    min_len = min(len(p_a), len(p_b))
    p_a, p_b = p_a[-min_len:], p_b[-min_len:]

    # Compute Statistics
    beta, alpha = compute_ols_hedge_ratio(p_a, p_b)
    spread = [a - beta * b for a, b in zip(p_a, p_b)]
    adf_stat, p_val, is_coint = adf_test(spread)
    half_life = compute_half_life(spread)

    mean_spread = statistics.mean(spread)
    std_spread = statistics.stdev(spread) if len(spread) > 1 else 1.0
    cur_spread = spread[-1]
    cur_z = (cur_spread - mean_spread) / std_spread if std_spread > 1e-12 else 0.0
    signal = calculate_zscore_signal(cur_z)
    sizing = calculate_position_sizing(capital, p_a[-1], p_b[-1], beta)

    payload = {
        "stock_a": stock_a,
        "stock_b": stock_b,
        "pair": f"{stock_a}/{stock_b}",
        "price_a": p_a[-1],
        "price_b": p_b[-1],
        "beta": round(beta, 4),
        "alpha": round(alpha, 4),
        "adf_statistic": round(adf_stat, 4),
        "p_value": round(p_val, 4),
        "is_cointegrated": is_coint,
        "half_life_days": round(half_life, 1),
        "current_spread": round(cur_spread, 2),
        "spread_mean": round(mean_spread, 2),
        "spread_std": round(std_spread, 2),
        "current_zscore": round(cur_z, 2),
        "signal": signal,
        "allocation": sizing,
    }

    if output_json:
        print(json.dumps(payload, indent=2))
        return 0

    console = Console(width=160)
    sig_badge = (
        "[bold white on green] LONG_PAIR [/]" if "LONG" in signal
        else ("[bold white on red] SHORT_PAIR [/]" if "SHORT" in signal
        else ("[bold black on yellow] EXIT [/]" if "EXIT" in signal else "[dim] NONE [/]"))
    )
    hdr = Text()
    hdr.append(f"  Pair: {stock_a} (₹{p_a[-1]:,.2f})  /  {stock_b} (₹{p_b[-1]:,.2f})\n", style="bold white")
    hdr.append(f"  Signal State      : {sig_badge}\n")
    hdr.append(f"  Current Z-Score   : {cur_z:+.2f}  (Mean: {mean_spread:.2f}, Std: {std_spread:.2f})\n", style="bold cyan")
    hdr.append(f"  Hedge Ratio (β)   : {beta:.4f}   Alpha (α): {alpha:.2f}\n", style="yellow")
    hdr.append(f"  Cointegration     : {'✓ Cointegrated (p < 0.05)' if is_coint else '✗ Non-cointegrated'} (ADF: {adf_stat:.2f}, p: {p_val:.4f})\n", style="bold green" if is_coint else "dim red")
    hdr.append(f"  OU Half-Life      : {half_life:.1f} days", style="magenta")

    console.print(Panel(hdr, title=f"[bold]SKTUI Spread Analysis — {stock_a} vs {stock_b}[/bold]", border_style="cyan"))

    t_sz = Table(title=f"Market-Neutral Capital Allocation (₹{capital:,.0f} Portfolio)", border_style="dim")
    t_sz.add_column("Leg", style="bold")
    t_sz.add_column("Symbol", style="bold")
    t_sz.add_column("Action")
    t_sz.add_column("Shares", justify="right")
    t_sz.add_column("Value (₹)", justify="right")
    t_sz.add_column("Weight %", justify="right")

    action_a = "BUY" if "LONG" in signal else ("SELL" if "SHORT" in signal else "FLAT")
    action_b = "SELL" if "LONG" in signal else ("BUY" if "SHORT" in signal else "FLAT")
    dollar_a = sizing.get("dollar_a", sizing.get("capital_a", 0.0))
    dollar_b = sizing.get("dollar_b", sizing.get("capital_b", 0.0))
    weight_a = sizing.get("weight_a", (dollar_a / capital) if capital > 0 else 0.0)
    weight_b = sizing.get("weight_b", (dollar_b / capital) if capital > 0 else 0.0)

    t_sz.add_row("Leg A", stock_a, action_a, str(sizing.get("shares_a", 0)), f"₹{dollar_a:,.2f}", f"{weight_a * 100:.1f}%")
    t_sz.add_row("Leg B", stock_b, action_b, str(sizing.get("shares_b", 0)), f"₹{dollar_b:,.2f}", f"{weight_b * 100:.1f}%")
    console.print(t_sz)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        console.print(f"[dim]Results saved to {output_path}[/dim]")

    if logger:
        logger.info("Executed CLI spread for %s vs %s (Z=%.2f)", stock_a, stock_b, cur_z)
    return 0


def handle_signals(args: argparse.Namespace, logger: Any = None) -> int:
    """Execute headless multi-indicator signal scanning."""
    import json
    from rich.console import Console
    from rich.table import Table
    from sktui.config import SECTOR_MAP
    from sktui.services.signal_engine import scan_watchlist
    from sktui.services.stock_analyzer import StockAnalyzer

    raw_symbols = getattr(args, "symbols", None)
    watchlist = getattr(args, "watchlist", None)
    filter_type = (getattr(args, "filter", "ALL") or "ALL").strip().upper()
    min_conf = getattr(args, "min_conf", getattr(args, "min_confidence", 60.0))
    output_path = getattr(args, "output", None)
    output_json = getattr(args, "json", False)

    # 1. Resolve Symbols
    target_symbols: list[str] = []
    if raw_symbols:
        if isinstance(raw_symbols, str):
            target_symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
        elif isinstance(raw_symbols, (list, tuple)):
            for item in raw_symbols:
                for s in str(item).split(","):
                    if s.strip():
                        target_symbols.append(s.strip().upper())
    elif watchlist:
        wl_clean = watchlist.strip().lower()
        target_symbols = [s for s, sec in SECTOR_MAP.items() if sec.lower() == wl_clean]
        if not target_symbols:
            target_symbols = list(SECTOR_MAP.keys())[:10]
    else:
        target_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "TATAMOTORS", "ITC", "LT"]

    # 2. Fetch Bars Map
    analyzer = StockAnalyzer()
    ohlcv_map: dict[str, dict[str, list[float]]] = {}
    for sym in target_symbols:
        bars = analyzer._fetch_bars(sym, period="1y")
        if bars and len(bars.get("close", [])) >= 30:
            ohlcv_map[sym] = bars

    # 3. Scan Signals
    signals = scan_watchlist(target_symbols, ohlcv_map, direction=filter_type, min_confidence=min_conf)

    if output_json:
        print(json.dumps([s.to_dict() for s in signals], indent=2))
        return 0

    console = Console(width=160)
    t = Table(
        title=f"Multi-Indicator Composite Signal Scanner (Filter: {filter_type}, Min Conf: {min_conf:.1f}%)",
        border_style="cyan",
    )
    t.add_column("Symbol", style="bold", no_wrap=True)
    t.add_column("LTP (₹)", justify="right")
    t.add_column("Signal Tier", justify="center")
    t.add_column("Score", justify="right")
    t.add_column("Confidence", justify="right")
    t.add_column("Votes (RSI / MACD / BB / SMA / VOL / STOCH / ADX)")
    t.add_column("Stop Loss (₹)", justify="right")
    t.add_column("Take Profit (₹)", justify="right")
    t.add_column("R:R", justify="center")

    for s in signals:
        badge_style = (
            "bold white on green" if s.signal_type == "STRONG_BUY"
            else ("bold green" if s.signal_type == "BUY"
            else ("bold black on yellow" if s.signal_type == "NEUTRAL"
            else ("bold red" if s.signal_type == "SELL" else "bold white on red")))
        )
        votes = s.indicator_votes
        vote_str = (
            f"RSI:{votes.get('rsi', 0):+d}  MACD:{votes.get('macd', 0):+d}  BB:{votes.get('bollinger', 0):+d}  "
            f"SMA:{votes.get('trend', 0):+d}  VOL:{votes.get('volume', 0):+d}  STOCH:{votes.get('stochastic', 0):+d}  "
            f"ADX:{votes.get('adx', 0):+d}"
        )
        conf_meter = f"{s.confidence_pct:.1f}%"
        t.add_row(
            s.symbol,
            f"₹{s.price:,.2f}",
            f"[{badge_style}] {s.signal_type} [/]",
            f"{s.score:+.2f}",
            conf_meter,
            vote_str,
            f"₹{s.stop_loss:,.2f}",
            f"₹{s.take_profit:,.2f}",
            f"{s.risk_reward_ratio:.1f}x",
        )

    console.print(t)
    if not signals:
        console.print("[dim]  No symbols matched the direction filter or minimum confidence threshold.[/dim]")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            if output_path.endswith(".json"):
                json.dump([s.to_dict() for s in signals], f, indent=2)
            else:
                f.write(str(t))
        console.print(f"[dim]Results saved to {output_path}[/dim]")

    if logger:
        logger.info("Executed CLI signals (found %d signals)", len(signals))
    return 0


def handle_backtest(args: argparse.Namespace, logger: Any = None) -> int:
    """Execute headless strategy backtesting simulation."""
    import json
    import sys
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from sktui.api.paper_trading import generate_paper_history
    from sktui.screens.modals import sparkline
    from sktui.services.backtesting import (
        DEFAULT_PARAM_GRIDS,
        BacktestConfig,
        optimize_grid,
        run_backtest,
        walk_forward_analysis,
    )
    from sktui.services.stock_analyzer import StockAnalyzer

    strategy = getattr(args, "strategy", "") or ""
    symbol = getattr(args, "symbol", "") or ""
    capital = getattr(args, "capital", 100000.0)
    period = getattr(args, "period", "1y") or "1y"
    commission = getattr(args, "commission", 0.0003)
    slippage = getattr(args, "slippage", 0.0002)
    mode = getattr(args, "mode", "vectorized") or "vectorized"
    optimize = getattr(args, "optimize", False)
    walk_forward = getattr(args, "walk_forward", False)
    output_path = getattr(args, "output", None)
    output_json = getattr(args, "json", False)

    if not strategy.strip():
        print("[!] Error: Strategy name is required.", file=sys.stderr)
        return 1
    if not symbol.strip():
        print("[!] Error: Symbol is required.", file=sys.stderr)
        return 1
    if capital <= 0:
        print(f"[!] Error: Capital must be positive (got {capital}).", file=sys.stderr)
        return 1
    if commission < 0 or slippage < 0:
        print(f"[!] Error: Commission and slippage rates cannot be negative.", file=sys.stderr)
        return 1

    clean_strat = strategy.strip().lower()
    clean_sym = symbol.strip().upper()

    # 1. Fetch Historical Bars
    analyzer = StockAnalyzer()
    bars = analyzer._fetch_bars(clean_sym, period=period)
    if not bars or len(bars.get("close", [])) < 5:
        rows = generate_paper_history("NC", clean_sym, "1d", bars_count=120)
        bars = {
            "open": [float(r.get("open") or 0.0) for r in rows],
            "high": [float(r.get("high") or 0.0) for r in rows],
            "low": [float(r.get("low") or 0.0) for r in rows],
            "close": [float(r.get("close") or 0.0) for r in rows],
            "volume": [float(r.get("volume") or 1000.0) for r in rows],
        }

    cfg = BacktestConfig(
        initial_capital=float(capital),
        commission_rate=float(commission),
        slippage_rate=float(slippage),
        strategy_name=clean_strat,
        mode=mode,
    )

    console = Console(width=160)

    # 2. Branch: Grid Optimization
    if optimize:
        grid = DEFAULT_PARAM_GRIDS.get(clean_strat, {"fast_period": [5, 10, 15], "slow_period": [20, 30, 50]})
        opt_results = optimize_grid(bars, clean_strat, grid, metric="sharpe_ratio", base_config=cfg)

        if output_json:
            json_data = [
                {
                    "rank": i + 1,
                    "parameters": params,
                    "sharpe_ratio": res.sharpe_ratio,
                    "total_return_pct": round(res.total_return * 100.0, 2),
                    "annualized_volatility_pct": round(res.annualized_volatility * 100.0, 2),
                    "max_drawdown_pct": round(res.max_drawdown * 100.0, 2),
                    "total_trades": res.total_trades,
                    "win_rate_pct": round(res.win_rate * 100.0, 2),
                }
                for i, (params, res) in enumerate(opt_results)
            ]
            dump_str = json.dumps(json_data, indent=2)
            print(dump_str)
            if output_path:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(dump_str)
            return 0

        t = Table(title=f"Multi-Parameter Grid Search Optimization — {clean_sym} ({clean_strat.upper()})", border_style="cyan")
        t.add_column("Rank", justify="right", style="bold")
        t.add_column("Parameters")
        t.add_column("Sharpe", justify="right", style="bold yellow")
        t.add_column("Return %", justify="right")
        t.add_column("Vol %", justify="right")
        t.add_column("MaxDD %", justify="right")
        t.add_column("Trades", justify="right")
        t.add_column("Win Rate %", justify="right")

        for i, (p, r) in enumerate(opt_results[:10]):
            param_str = ", ".join(f"{k}={v}" for k, v in p.items())
            ret_style = "bold green" if r.total_return >= 0 else "bold red"
            t.add_row(
                str(i + 1),
                param_str,
                f"{r.sharpe_ratio:.2f}",
                f"[{ret_style}]{r.total_return * 100.0:+.2f}%[/{ret_style}]",
                f"{r.annualized_volatility * 100.0:.2f}%",
                f"{r.max_drawdown * 100.0:.2f}%",
                str(r.total_trades),
                f"{r.win_rate * 100.0:.1f}%",
            )
        console.print(t)
        if logger:
            logger.info("Executed CLI backtest grid optimization for %s (%s)", clean_sym, clean_strat)
        return 0

    # 3. Branch: Walk-Forward Validation
    if walk_forward:
        grid = DEFAULT_PARAM_GRIDS.get(clean_strat, {"fast_period": [5, 10, 15], "slow_period": [20, 30, 50]})
        wf_results = walk_forward_analysis(bars, clean_strat, grid, n_windows=5, train_ratio=0.7, metric="sharpe_ratio", base_config=cfg)

        if output_json:
            json_data = [
                {
                    "window": r["window"],
                    "train_range": list(r["train_range"]),
                    "test_range": list(r["test_range"]),
                    "best_parameters": r["best_parameters"],
                    "in_sample_sharpe": round(r["in_sample_metric"], 4),
                    "out_sample_return_pct": round(r["out_sample_return"] * 100.0, 2),
                    "out_sample_sharpe": round(r["out_sample_sharpe"], 4),
                    "out_sample_max_dd_pct": round(r["out_sample_max_dd"] * 100.0, 2),
                    "out_sample_trades": r["out_sample_trades"],
                    "out_sample_win_rate_pct": round(r["out_sample_win_rate"] * 100.0, 2),
                }
                for r in wf_results
            ]
            dump_str = json.dumps(json_data, indent=2)
            print(dump_str)
            if output_path:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(dump_str)
            return 0

        t = Table(title=f"Walk-Forward Rolling-Window Validation — {clean_sym} ({clean_strat.upper()})", border_style="cyan")
        t.add_column("Window", justify="center", style="bold")
        t.add_column("Train Range", justify="center")
        t.add_column("Test Range", justify="center")
        t.add_column("Best Params")
        t.add_column("In-Sample Sharpe", justify="right")
        t.add_column("Out-Sample Return %", justify="right")
        t.add_column("Out-Sample Sharpe", justify="right", style="bold yellow")
        t.add_column("Out-Sample MaxDD %", justify="right")
        t.add_column("Trades", justify="right")
        t.add_column("Win Rate %", justify="right")

        for r in wf_results:
            param_str = ", ".join(f"{k}={v}" for k, v in r["best_parameters"].items())
            ret_style = "bold green" if r["out_sample_return"] >= 0 else "bold red"
            t.add_row(
                f"W{r['window'] + 1}",
                f"{r['train_range'][0]}..{r['train_range'][1]} ({r['train_bars']}b)",
                f"{r['test_range'][0]}..{r['test_range'][1]} ({r['test_bars']}b)",
                param_str,
                f"{r['in_sample_metric']:.2f}",
                f"[{ret_style}]{r['out_sample_return'] * 100.0:+.2f}%[/{ret_style}]",
                f"{r['out_sample_sharpe']:.2f}",
                f"{r['out_sample_max_dd'] * 100.0:.2f}%",
                str(r["out_sample_trades"]),
                f"{r['out_sample_win_rate'] * 100.0:.1f}%",
            )
        console.print(t)
        if logger:
            logger.info("Executed CLI walk-forward analysis for %s (%s)", clean_sym, clean_strat)
        return 0

    # 4. Branch: Standard Single Backtest Execution
    result = run_backtest(bars, clean_strat, cfg, mode=mode)

    if output_json:
        dump_str = json.dumps(result.to_dict(), indent=2)
        print(dump_str)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(dump_str)
        return 0

    # Formatted Rich Output
    ret_pct = result.total_return * 100.0
    ret_style = "bold green" if ret_pct >= 0 else "bold red"
    net_pnl = result.final_equity - result.initial_capital
    pnl_style = "bold green" if net_pnl >= 0 else "bold red"
    spk = sparkline(result.equity_curve, width=40) if len(result.equity_curve) > 1 else "―"

    hdr_text = Text()
    hdr_text.append(f"  {clean_sym}  ", style="bold white")
    hdr_text.append(f"Strategy: {clean_strat.upper()}  ", style="bold cyan")
    hdr_text.append(f"Mode: {mode.upper()}  ", style="dim")
    hdr_text.append(f"Initial: ₹{result.initial_capital:,.2f}  ", style="white")
    hdr_text.append(f"Final: ₹{result.final_equity:,.2f}  ", style="bold white")
    hdr_text.append(f"Return: {ret_pct:+.2f}%  ", style=ret_style)
    hdr_text.append(f"Net P&L: ₹{net_pnl:+,.2f}\n", style=pnl_style)
    hdr_text.append(f"  Equity Curve : {spk}  ", style="cyan")
    hdr_text.append(f"(Points: {len(result.equity_curve)}, Trades: {result.total_trades}, Sharpe: {result.sharpe_ratio:.2f})", style="dim")

    console.print(Panel(hdr_text, title=f"[bold]SKTUI Strategy Backtest Simulation — {clean_sym}[/bold]", border_style="cyan"))

    # Performance & Risk Metrics Table
    t_perf = Table(title="Performance & Risk Ratios", border_style="dim")
    t_perf.add_column("Metric", style="bold")
    t_perf.add_column("Value", justify="right")
    t_perf.add_column("Target / Horizon")
    t_perf.add_column("Evaluation")

    t_perf.add_row("Total Return", f"[{ret_style}]{ret_pct:+.2f}%[/{ret_style}]", "Benchmark", "Positive Alpha" if ret_pct > 0 else "Negative Alpha")
    t_perf.add_row("CAGR", f"{result.cagr * 100.0:+.2f}%", "Annualized", "Strong" if result.cagr > 0.15 else "Moderate")
    t_perf.add_row("Annualized Volatility", f"{result.annualized_volatility * 100.0:.2f}%", "< 25.0%", "Acceptable" if result.annualized_volatility < 0.25 else "High Volatility")
    sharpe_eval = "Institutional Grade" if result.sharpe_ratio >= 1.5 else ("Acceptable" if result.sharpe_ratio >= 1.0 else "Sub-optimal")
    t_perf.add_row("Sharpe Ratio (Rf=5%)", f"{result.sharpe_ratio:.2f}", "> 1.00", sharpe_eval)
    t_perf.add_row("Sortino Ratio", f"{result.sortino_ratio:.2f}", "> 1.50", "High Downside Protection" if result.sortino_ratio >= 1.5 else "Standard")
    t_perf.add_row("Calmar Ratio", f"{result.calmar_ratio:.2f}", "> 1.00", "Favorable" if result.calmar_ratio >= 1.0 else "Weak")
    t_perf.add_row("Maximum Drawdown", f"{result.max_drawdown * 100.0:.2f}%", "< 15.0%", "Controlled" if result.max_drawdown <= 0.15 else "Elevated Risk")
    console.print(t_perf)

    # Trade Analytics Table
    t_trades = Table(title="Trade Execution Analytics", border_style="dim")
    t_trades.add_column("Metric", style="bold")
    t_trades.add_column("Value", justify="right")
    t_trades.add_column("Benchmark")
    t_trades.add_column("Assessment")

    t_trades.add_row("Total Trades", str(result.total_trades), ">= 5", "Statistically Valid" if result.total_trades >= 5 else "Low Sample Size")
    wr_pct = result.win_rate * 100.0
    t_trades.add_row("Win Rate", f"{wr_pct:.1f}%", "> 50.0%", "Edge Confirmed" if wr_pct >= 50.0 else "Trend Dependent")
    pf_str = f"{result.profit_factor:.2f}" if result.profit_factor < 900.0 else "Inf"
    t_trades.add_row("Profit Factor", pf_str, "> 1.50", "Profitable" if result.profit_factor >= 1.5 else ("Marginal" if result.profit_factor >= 1.0 else "Loss Making"))
    t_trades.add_row("Total Executions Log", str(len(result.trades_log)), "Look-Ahead Guard", "exec_bar > signal_bar strictly enforced")
    console.print(t_trades)

    # Recent Executed Trades Log Table
    if result.trades_log:
        t_log = Table(title="Recent Executed Trades Log (Sample)", border_style="dim")
        t_log.add_column("#", justify="right", style="bold")
        t_log.add_column("Action", justify="center")
        t_log.add_column("Signal Bar", justify="right")
        t_log.add_column("Exec Bar", justify="right")
        t_log.add_column("Exec Price (₹)", justify="right")
        t_log.add_column("Shares", justify="right")
        t_log.add_column("Cost (₹)", justify="right")
        t_log.add_column("Realized P&L (₹)", justify="right")
        t_log.add_column("Equity (₹)", justify="right")

        for tr in result.trades_log[-8:]:
            action_style = "bold green" if tr.get("action") in ("BUY", "COVER") else "bold red"
            pnl_val = tr.get("realized_pnl", 0.0)
            pnl_col = "green" if pnl_val > 0 else ("red" if pnl_val < 0 else "dim")
            pnl_str = f"₹{pnl_val:+,.2f}" if tr.get("action") in ("SELL", "COVER") else "―"
            t_log.add_row(
                str(tr.get("trade_id", 1)),
                f"[{action_style}]{tr.get('action', 'BUY')}[/{action_style}]",
                str(tr.get("signal_bar", 0)),
                str(tr.get("exec_bar", 1)),
                f"₹{tr.get('exec_price', 0.0):,.2f}",
                str(tr.get("qty", 0)),
                f"₹{tr.get('commission', 0.0):,.2f}",
                f"[{pnl_col}]{pnl_str}[/{pnl_col}]",
                f"₹{tr.get('equity', result.initial_capital):,.2f}",
            )
        console.print(t_log)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"SKTUI Strategy Backtest: {clean_sym} ({clean_strat})\n")
            f.write(f"Total Return: {result.total_return * 100.0:+.2f}%\n")
            f.write(f"Sharpe Ratio: {result.sharpe_ratio:.2f}\n")
            f.write(f"Max Drawdown: {result.max_drawdown * 100.0:.2f}%\n")
            f.write(f"Total Trades: {result.total_trades}\n")
            f.write(f"Win Rate: {result.win_rate * 100.0:.1f}%\n")

    if logger:
        logger.info("Executed CLI backtest for %s (%s, return=%.2f%%)", clean_sym, clean_strat, ret_pct)
    return 0


def handle_bot(args: argparse.Namespace, logger: Any = None) -> int:
    """Execute headless automated trading bot orchestration."""
    import json
    import os
    import sys
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from sktui.services.bot_engine import BotInstance, BotManager, BotState

    strategy = (getattr(args, "strategy", "") or "").strip().lower()
    symbol = (getattr(args, "symbol", "") or "").strip().upper()
    action = (getattr(args, "action", "start") or "start").strip().lower()
    capital = float(getattr(args, "capital", 100000.0) or 100000.0)
    config_file = getattr(args, "config", None)
    output_path = getattr(args, "output", None)
    output_json = getattr(args, "json", False)

    # 1. Input Validation
    if not strategy:
        print("[!] Error: Bot strategy name is required.", file=sys.stderr)
        return 1
    if not symbol:
        print("[!] Error: Symbol is required.", file=sys.stderr)
        return 1
    if capital <= 0:
        print(f"[!] Error: Capital must be positive (got {capital}).", file=sys.stderr)
        return 1

    # 2. Execution Mode Resolution
    paper = getattr(args, "paper", False) or os.environ.get("SKTUI_PAPER") == "1"
    mode_str = "PAPER (SANDBOX)" if paper else "LIVE"

    # 3. Parameters from config if supplied
    params: dict[str, Any] = {"capital": capital}
    if config_file:
        try:
            with open(config_file, "r", encoding="utf-8") as cf:
                loaded = json.load(cf)
                if isinstance(loaded, dict):
                    params.update(loaded)
        except Exception as e:
            if logger:
                logger.warning("Failed to load bot config %s: %s", config_file, e)

    # 4. Bot Instance Resolution via BotManager
    bot_mgr = BotManager.get_instance()
    bot_id = f"bot_{strategy}_{symbol.replace(',', '_').replace('/', '_')}"
    bot = bot_mgr.get_bot(bot_id)

    if bot is None:
        bot = BotInstance(
            strategy=strategy,
            symbol=symbol,
            paper=paper,
            capital=capital,
            parameters=params,
            bot_id=bot_id,
        )
        bot_mgr.register_bot(bot, bot_id=bot_id)

    # 5. Lifecycle Action Dispatch
    action_res: dict[str, Any] = {}
    if action == "start":
        bot.start()
        action_res = {"action": "start", "success": True, "state": bot.state.value}
    elif action == "pause":
        paused = bot.pause()
        action_res = {"action": "pause", "success": paused, "state": bot.state.value}
    elif action == "resume":
        resumed = bot.resume()
        action_res = {"action": "resume", "success": resumed, "state": bot.state.value}
    elif action == "stop":
        stopped = bot.stop()
        action_res = {"action": "stop", "success": stopped, "state": bot.state.value}
    elif action == "panic":
        action_res = bot.emergency_panic(mode="CANCEL_ALL")
    elif action == "status":
        action_res = {"action": "status", "success": True, "state": bot.state.value}
    else:
        print(f"[!] Error: Unknown bot action '{action}'.", file=sys.stderr)
        return 1

    telem = bot.get_telemetry()
    payload = {
        "bot_id": bot_id,
        "strategy": strategy,
        "symbol": symbol,
        "mode": mode_str,
        "action": action,
        "state": bot.state.value,
        "action_result": action_res,
        "telemetry": telem,
    }

    # 6. JSON Export Mode
    if output_json:
        dump_str = json.dumps(payload, indent=2, default=str)
        print(dump_str)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(dump_str)
        if logger:
            logger.info("Executed CLI bot %s on %s (json=True)", strategy, symbol)
        return 0

    # 7. Formatted Console & Rich Telemetry Output
    # CRITICAL: Preserve exact spaces and strings for tests/test_remediation.py:
    # "  Strategy        : ..."
    # "  Symbol          : ..."
    # "  Mode            : LIVE" or "  Mode            : PAPER (SANDBOX)"
    print("[SKTUI CLI] Automated Trading Bot Orchestrator")
    print(f"  Strategy        : {strategy}")
    print(f"  Symbol          : {symbol}")
    print(f"  Mode            : {mode_str}")
    if config_file:
        print(f"  Config File     : {config_file}")
    print(f"  Action          : {action.upper()}")
    print(f"  Current State   : {payload['state']}")

    console = Console(width=140)
    state_style = "bold green" if payload["state"] == "RUNNING" else ("bold yellow" if payload["state"] == "PAUSED" else "bold red")
    pnl_val = float(telem.get("pnl", 0.0))
    pnl_style = "bold green" if pnl_val >= 0 else "bold red"

    hdr = Text()
    hdr.append(f"  Instance: {bot_id}  ·  ", style="bold white")
    hdr.append(f"Strategy: {strategy.upper()}  ·  ", style="bold cyan")
    hdr.append(f"Symbol: {symbol}  ·  ", style="bold white")
    hdr.append(f"State: [{state_style}]{payload['state']}[/{state_style}]  ·  ")
    hdr.append(f"Action: {action.upper()}  ·  ", style="bold yellow")
    hdr.append(f"Mode: {mode_str}\n", style="magenta")
    hdr.append(f"  Telemetry: Uptime: {telem.get('uptime_seconds', 0.0):.1f}s  |  Orders: {telem.get('total_orders', 0)}  |  Filled: {telem.get('filled_orders', 0)}  |  PnL: [{pnl_style}]₹{pnl_val:+,.2f}[/{pnl_style}]")
    console.print(Panel(hdr, title=f"[bold]SKTUI Bot Orchestrator Telemetry — {bot_id}[/bold]", border_style="cyan"))

    # Rich Telemetry Table
    t_telem = Table(title="Real-Time Bot Telemetry & Circuit Breakers", border_style="dim")
    t_telem.add_column("Parameter / Indicator", style="bold")
    t_telem.add_column("Current Metric", justify="right")
    t_telem.add_column("Safety Threshold", justify="center")
    t_telem.add_column("Operational Status")

    t_telem.add_row("Execution State", f"[{state_style}]{payload['state']}[/{state_style}]", "RUNNING / PAUSED", "Active" if payload["state"] == "RUNNING" else "Idle/Safe")
    t_telem.add_row("Uptime", f"{telem.get('uptime_seconds', 0.0):.1f} sec", "Continuous Loop", "Healthy")
    t_telem.add_row("Total Submitted Orders", str(telem.get("total_orders", 0)), "Rate Limited", "Normal")
    t_telem.add_row("Filled Orders", str(telem.get("filled_orders", 0)), "Execution Queue", "Synchronized")
    t_telem.add_row("Realized Daily PnL", f"[{pnl_style}]₹{pnl_val:+,.2f}[/{pnl_style}]", f"Max Loss: -₹{telem.get('daily_loss_limit', 5000.0):,.2f}", "Within Risk Envelope" if pnl_val > -telem.get('daily_loss_limit', 5000.0) else "[bold red]CIRCUIT BREAKER TRIPPED[/]")
    t_telem.add_row("Max Order Value Limit", f"₹{telem.get('max_order_val', 50000.0):,.2f}", "Pre-Trade Gate", "Enforced")
    console.print(t_telem)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            if output_path.endswith(".json"):
                f.write(json.dumps(payload, indent=2, default=str))
            else:
                f.write(f"SKTUI Bot {bot_id} [{payload['state']}]\nAction: {action}\nPnL: ₹{pnl_val:+,.2f}\n")
        console.print(f"[dim]Telemetry output saved to {output_path}[/dim]")

    if logger:
        logger.info("Executed CLI bot %s on %s (action=%s, state=%s)", strategy, symbol, action, payload["state"])
    return 0


def handle_verify(args: argparse.Namespace, logger: Any = None) -> int:
    """Execute headless broker connectivity and sandbox verification."""
    import json
    import time
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from sktui.api.client import Client
    from sktui.services.broker_verifier import BrokerVerifier, VerificationSummary

    sandbox = getattr(args, "sandbox", True)
    run_live = getattr(args, "live", False)
    if run_live:
        sandbox = False
    endpoint = getattr(args, "endpoint", None)
    verbose = getattr(args, "verbose", False)
    run_auth = getattr(args, "auth", False)
    run_paper = getattr(args, "paper", False)
    output_path = getattr(args, "output", None)
    output_json = getattr(args, "json", False)

    console = Console()

    if endpoint and not sandbox:
        import sktui.api.client as api_client
        api_client.BASE = endpoint

    # Target client setup
    if sandbox:
        client = Client(
            api_key="SANDBOX",
            access_token="SANDBOX",
            customer_id="123456",
            paper=True,
        )
    else:
        # Live broker client setup
        import sktui.config as cfg
        client = Client(
            api_key=getattr(cfg, "API_KEY", "") or "LIVE_PROBE",
            access_token=getattr(cfg, "ACCESS_TOKEN", "") or "LIVE_PROBE",
            customer_id=getattr(cfg, "CUSTOMER_ID", "") or "0",
            paper=False,
        )

    verifier = BrokerVerifier(client=client, paper=sandbox)

    start_time = time.monotonic()
    if run_auth:
        results = verifier.verify_crypto()
        report = VerificationSummary(results=results, duration_ms=round((time.monotonic() - start_time) * 1000.0, 2))
    elif run_paper:
        results = verifier.verify_paper_sandbox()
        report = VerificationSummary(results=results, duration_ms=round((time.monotonic() - start_time) * 1000.0, 2))
    elif run_live:
        results = verifier.verify_endpoints(client=client)
        report = VerificationSummary(results=results, duration_ms=round((time.monotonic() - start_time) * 1000.0, 2))
    else:
        report = verifier.run_all_checks(client=client, sandbox_only=sandbox)

    # Output JSON branch
    if output_json:
        payload = report.to_dict()
        dump_str = json.dumps(payload, indent=2, default=str)
        print(dump_str)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(dump_str)
        if logger:
            logger.info("Executed CLI verify (json=True, sandbox=%s, passed=%s)", sandbox, report.passed)
        return 0 if report.passed else 1

    # Rich formatted output branch
    target_mode = "Paper Sandbox Simulation" if sandbox else "Live Broker Endpoints"
    hdr = f"""[bold cyan]Target Mode[/]     : [bold white]{target_mode}[/]
[bold cyan]Endpoint Override[/]: [yellow]{endpoint or 'Default Sharekhan API'}[/]
[bold cyan]Checks Executed[/]  : [bold white]{report.total_count}[/]
[bold cyan]Total Latency[/]    : [bold]{report.total_latency_ms:.2f} ms[/] (avg {report.avg_latency_ms:.2f} ms/check)
[bold cyan]Result Status[/]    : {'[bold green]ALL CHECKS PASSED[/]' if report.passed else '[bold red]VERIFICATION FAILED[/]'}"""

    console.print(Panel(hdr, title="[bold]SKTUI Broker Connectivity & Sandbox Verification[/bold]", border_style="cyan"))

    t = Table(title="Diagnostic Verification Results Matrix", border_style="dim", expand=True)
    t.add_column("Status", justify="center", style="bold", no_wrap=True, width=8)
    t.add_column("Domain", style="cyan", no_wrap=True, width=12)
    t.add_column("Verification Test", style="bold", no_wrap=True, width=36)
    t.add_column("Latency", justify="right", no_wrap=True, width=12)
    t.add_column("Message / Diagnostic Trace")

    for r in report.results:
        if r.status == "PASS":
            badge = "[bold green]PASS[/]"
        elif r.status == "FAIL":
            badge = "[bold red]FAIL[/]"
        else:
            badge = "[bold yellow]SKIP[/]"

        if r.latency_ms < 20.0:
            lat_str = f"[green]{r.latency_ms:.2f} ms[/]"
        elif r.latency_ms < 100.0:
            lat_str = f"[yellow]{r.latency_ms:.2f} ms[/]"
        else:
            lat_str = f"[red]{r.latency_ms:.2f} ms[/]"

        msg = r.message
        if verbose and r.details:
            msg += f" [dim]| details={r.details}[/dim]"

        t.add_row(badge, r.domain, r.name, lat_str, msg)

    console.print(t)

    summary_color = "green" if report.passed else "red"
    console.print(
        f"[{summary_color}]Summary: {report.passed_count}/{report.total_count} checks passed, "
        f"{report.failed_count} failed, {report.skipped_count} skipped in {report.total_latency_ms:.2f} ms.[/{summary_color}]"
    )

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            if output_path.endswith(".json"):
                f.write(json.dumps(report.to_dict(), indent=2, default=str))
            else:
                f.write(
                    f"SKTUI Broker Connectivity & Sandbox Verification Report\n"
                    f"Target Mode: {target_mode}\n"
                    f"Status: {'PASS' if report.passed else 'FAIL'}\n"
                    f"Passed: {report.passed_count}/{report.total_count}\n"
                    f"Duration: {report.total_latency_ms:.2f} ms\n"
                )
        console.print(f"[dim]Verification report saved to {output_path}[/dim]")

    if logger:
        logger.info("Executed CLI verify (sandbox=%s, passed=%s)", sandbox, report.passed)
    return 0 if report.passed else 1


SUBCOMMAND_HANDLERS: dict[str, Any] = {
    "analyze": handle_analyze,
    "compare": handle_compare,
    "pairs": handle_pairs,
    "spread": handle_spread,
    "signals": handle_signals,
    "backtest": handle_backtest,
    "bot": handle_bot,
    "verify": handle_verify,
}


def build_parser() -> argparse.ArgumentParser:
    """Build and configure the SKTUI top-level argument parser with subparsers."""
    ap = argparse.ArgumentParser(
        prog="sktui",
        description="SKTUI — Professional Terminal Trading CLI for Mirae Asset Sharekhan",
    )
    ap.set_defaults(command=None, subcommand=None)
    # Root interactive TUI options
    ap.add_argument("--paper", action="store_true", default=False,
                    help="dry-run: simulate orders, never execute live")
    ap.add_argument("--profile", default=os.environ.get("SKTUI_PROFILE", "default"),
                    help="configuration profile (e.g. default, live, paper)")
    ap.add_argument("--theme", default=None,
                    help="UI color theme (e.g. sktui-obsidian, sktui-bloomberg, sktui-daylight, nord)")
    ap.add_argument("--debug", action="store_true", default=False,
                    help="enable verbose debug logging and Textual devtools")
    ap.add_argument("--log-level", default=None,
                    help="logging level override (DEBUG, INFO, WARNING, ERROR)")
    ap.add_argument("--symbol", default=None,
                    help="initial active symbol to focus in TUI workstation")

    # Subparsers for headless CLI subsystem
    subparsers = ap.add_subparsers(
        dest="subcommand",
        title="subcommands",
        description="Headless trading, analysis, backtesting, and verification commands",
        help="Run 'sktui <subcommand> --help' for subcommand options",
    )

    # 1. analyze
    p_analyze = subparsers.add_parser(
        "analyze",
        help="Run technical and quantitative analysis for a symbol",
        description="Calculate technical indicators, quant performance metrics, and composite score.",
    )
    p_analyze.set_defaults(command="analyze", subcommand="analyze")
    p_analyze.add_argument("symbol", help="Stock ticker symbol (e.g. RELIANCE, TCS, INFY)")
    p_analyze.add_argument("--period", "-p", default="1y", help="Historical period lookback (default: 1y)")
    p_analyze.add_argument("--indicators", "-i", default=None, help="Comma-separated indicators to compute")
    p_analyze.add_argument("--compare", default=None, help="Comma-separated symbols to compare against")

    # 2. compare
    p_compare = subparsers.add_parser(
        "compare",
        help="Compare multiple stocks and rank by metric",
        description="Compare and rank multiple stocks by Sharpe ratio, return, volatility, or momentum.",
    )
    p_compare.set_defaults(command="compare", subcommand="compare")
    p_compare.add_argument("symbols", nargs="+", help="Stock ticker symbols to compare (e.g. RELIANCE TCS INFY)")
    p_compare.add_argument(
        "--rank-by", "-r",
        choices=["sharpe", "return", "volatility", "momentum", "sortino", "drawdown"],
        default="sharpe",
        help="Metric to rank stocks by (default: sharpe)",
    )
    p_compare.add_argument("--period", "-p", default="1y", help="Historical period lookback (default: 1y)")

    # 2. pairs
    p_pairs = subparsers.add_parser(
        "pairs",
        help="Screen cointegrated pair trading candidates",
        description="Run cointegration, correlation, and hedge ratio screening across universe.",
    )
    p_pairs.set_defaults(command="pairs", subcommand="pairs")
    p_pairs.add_argument("--sector", "-s", default=None, help="Sector filter (e.g. Banking, IT, Auto, Energy)")
    p_pairs.add_argument("--min-corr", "-c", type=float, default=0.70, help="Minimum Pearson correlation threshold (default: 0.70)")
    p_pairs.add_argument("--symbols", nargs="+", default=None, help="Symbols to restrict universe")
    p_pairs.add_argument("--output", "-o", default=None, help="Output file path for screening results")
    p_pairs.add_argument("--json", action="store_true", default=False, help="Output pure JSON to stdout")

    # 3. spread
    p_spread = subparsers.add_parser(
        "spread",
        help="Analyze cointegrated spread between two stocks",
        description="Calculate OLS hedge ratio, ADF unit-root test, OU half-life, Z-score, and position sizing.",
    )
    p_spread.set_defaults(command="spread", subcommand="spread")
    p_spread.add_argument("--stock-a", "-a", required=True, help="First stock ticker (Stock A / Dependent Y)")
    p_spread.add_argument("--stock-b", "-b", required=True, help="Second stock ticker (Stock B / Independent X)")
    p_spread.add_argument("--lookback", "-l", type=int, default=90, help="Historical lookback window in days (default: 90)")
    p_spread.add_argument("--capital", type=float, default=100000.0, help="Capital allocation in INR for position sizing (default: 100000.0)")
    p_spread.add_argument("--output", "-o", default=None, help="Output file path for analysis results")
    p_spread.add_argument("--json", action="store_true", default=False, help="Output pure JSON to stdout")

    # 4. signals
    p_signals = subparsers.add_parser(
        "signals",
        help="Generate composite trading signals",
        description="Scan symbols and output multi-indicator composite signals with confidence levels.",
    )
    p_signals.set_defaults(command="signals", subcommand="signals", min_conf=60.0, min_confidence=60.0)
    p_signals.add_argument("--symbols", "-s", nargs="+", default=None, help="Symbols to scan (comma or space separated)")
    p_signals.add_argument("--watchlist", "-w", default=None, help="Watchlist identifier (e.g. default, banking, it)")
    p_signals.add_argument(
        "--filter", "-f",
        choices=["ALL", "all", "BUY", "buy", "SELL", "sell", "STRONG_BUY", "strong_buy", "STRONG_SELL", "strong_sell"],
        default="ALL",
        help="Filter by signal type (ALL, BUY, SELL, STRONG_BUY, STRONG_SELL)",
    )
    p_signals.add_argument("--min-conf", "--min-confidence", type=float, default=60.0, action=MinConfAction, help="Minimum confidence threshold percentage (default: 60.0)")
    p_signals.add_argument("--output", "-o", default=None, help="Output file path for scanned signals")
    p_signals.add_argument("--json", action="store_true", default=False, help="Output pure JSON to stdout")

    # 4. backtest
    p_backtest = subparsers.add_parser(
        "backtest",
        help="Simulate trading strategy against historical data",
        description="Run dual-mode backtesting with bias prevention and transaction cost modeling.",
    )
    p_backtest.set_defaults(command="backtest", subcommand="backtest")
    p_backtest.add_argument("--strategy", "-s", required=True, help="Strategy identifier (e.g. sma, ema, rsi, macd, bollinger, breakout, mean_reversion, momentum)")
    p_backtest.add_argument("--symbol", required=True, help="Stock ticker symbol to backtest against")
    p_backtest.add_argument("--capital", "-c", type=float, default=100000.0, help="Initial simulation capital in INR (default: 100000.0)")
    p_backtest.add_argument("--period", "-p", default="1y", help="Historical backtest period (default: 1y)")
    p_backtest.add_argument("--commission", type=float, default=0.0003, help="Commission rate per trade (default: 0.0003)")
    p_backtest.add_argument("--slippage", type=float, default=0.0002, help="Slippage rate per trade (default: 0.0002)")
    p_backtest.add_argument("--mode", "-m", choices=["vectorized", "event_driven"], default="vectorized", help="Simulation engine mode (default: vectorized)")
    p_backtest.add_argument("--optimize", action="store_true", default=False, help="Run parameter grid search optimization")
    p_backtest.add_argument("--walk-forward", action="store_true", default=False, help="Run rolling-window walk-forward validation")
    p_backtest.add_argument("--output", "-o", default=None, help="Output file path (.json or text)")
    p_backtest.add_argument("--json", action="store_true", default=False, help="Output scriptable JSON format to stdout")

    # 5. bot
    p_bot = subparsers.add_parser(
        "bot",
        help="Launch and orchestrate automated trading bot",
        description="Execute automated bot strategies (PMM, arbitrage, momentum, predictor).",
    )
    p_bot.set_defaults(command="bot", subcommand="bot")
    p_bot.add_argument("--strategy", "-s", required=True, help="Bot strategy name (e.g. pmm, arbitrage, momentum)")
    p_bot.add_argument("--symbol", required=True, help="Trading symbol / scrip code")
    p_bot.add_argument("--action", "-a",
                       choices=["start", "stop", "pause", "resume", "status", "panic"],
                       default="start",
                       help="Bot lifecycle action (start, stop, pause, resume, status, panic) [default: start]")
    p_bot.add_argument("--paper", action="store_true", default=argparse.SUPPRESS, help="Run bot in paper sandbox mode")
    p_bot.add_argument("--capital", "-c", type=float, default=100000.0,
                       help="Capital allocation in INR for the bot instance (default: 100000.0)")
    p_bot.add_argument("--config", default=None, help="Bot JSON/YAML configuration file path")
    p_bot.add_argument("--output", "-o", default=None, help="Output file path (.json or text)")
    p_bot.add_argument("--json", action="store_true", default=False, help="Output scriptable JSON format to stdout")

    # 6. verify
    p_verify = subparsers.add_parser(
        "verify",
        help="Verify broker connectivity and sandbox environment",
        description="Execute broker authentication and paper sandbox verification suite.",
    )
    p_verify.set_defaults(command="verify", subcommand="verify")
    p_verify.add_argument("--sandbox", action="store_true", default=True, help="Verify against paper sandbox environment (default: True)")
    p_verify.add_argument("--no-sandbox", action="store_false", dest="sandbox", help="Verify against live broker endpoints")
    p_verify.add_argument("--live", action="store_true", default=False, help="Run only live broker connectivity and endpoint probes")
    p_verify.add_argument("--auth", action="store_true", default=False, help="Run only authentication and AES-GCM crypto verification")
    p_verify.add_argument("--paper", action="store_true", default=False, help="Run only paper trading sandbox simulation verification")
    p_verify.add_argument("--endpoint", default=None, help="Broker endpoint URL override")
    p_verify.add_argument("--output", "-o", default=None, help="Output file path (.json or text)")
    p_verify.add_argument("--json", action="store_true", default=False, help="Output scriptable JSON format to stdout")
    p_verify.add_argument("--verbose", "-v", action="store_true", default=False, help="Enable verbose verification output")

    return ap


def main(argv: list[str] | None = None) -> int:
    import sys
    import traceback
    from datetime import datetime
    from sktui.services.logger import setup_logger
    from sktui.config_manager import config_manager

    logger = setup_logger()
    logger.info("Starting SKTUI workstation session")

    ap = build_parser()
    args = ap.parse_args(argv)

    cmd = getattr(args, "subcommand", None) or getattr(args, "command", None)
    if cmd in SUBCOMMAND_HANDLERS:
        return SUBCOMMAND_HANDLERS[cmd](args, logger=logger)

    profile, validation_warnings = config_manager.startup_validation_report(args.profile)
    for warn in validation_warnings:
        logger.warning("Config validation: %s", warn)

    is_paper = args.paper or profile.paper or args.profile == "paper" or os.environ.get("SKTUI_PAPER") == "1"
    os.environ["SKTUI_PROFILE"] = args.profile

    if args.debug:
        os.environ["TEXTUAL_DEBUG"] = "1"
        logger.setLevel("DEBUG")
    elif getattr(args, "log_level", None):
        logger.setLevel(args.log_level.upper())

    logger.info("Profile: %s  Paper: %s  Debug: %s", args.profile, is_paper, args.debug)
    if validation_warnings:
        logger.warning("Startup config issues: %d warning(s)", len(validation_warnings))

    cfg_data = read_json(CONFIG_FILE, {})
    has_saved_theme = isinstance(cfg_data, dict) and bool(str(cfg_data.get("theme", "")).strip())
    resolved_theme: str | None = args.theme
    if not resolved_theme and not os.environ.get("SKTUI_THEME") and not has_saved_theme:
        if profile.theme and profile.theme != DEFAULT_THEME:
            resolved_theme = profile.theme

    app = SKApp(paper=is_paper, initial_theme=resolved_theme, auto_paper=is_paper)
    try:
        app.run()
        return 0
    except Exception as e:
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_file = DATA / f"crash_{now_str}.log"
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            with open(crash_file, "w", encoding="utf-8") as f:
                f.write(f"SKTUI CRASH REPORT — {datetime.now().isoformat()}\n")
                f.write(f"Python: {sys.version}\n")
                f.write(f"Profile: {args.profile} (Paper: {is_paper}, Debug: {args.debug})\n\n")
                traceback.print_exc(file=f)
            logger.error("Uncaught exception in SKTUI runtime. Crash dump written to %s", crash_file, exc_info=True)
            print(f"\n[!] SKTUI encountered an unexpected error: {e}", file=sys.stderr)
            print(f"[!] Crash report written to: {crash_file}\n", file=sys.stderr)
        except Exception:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

