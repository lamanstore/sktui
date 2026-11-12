"""Stock Analyzer and Multi-Stock Ranking Service for SKTUI.

Combines technical indicator consolidation, combined RSI+MACD signal generation,
quant risk performance analytics, and multi-symbol watchlist ranking.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

from sktui.config import KNOWN_BASE_PRICES
from sktui.services.indicators import (
    adx,
    bollinger_bands,
    ema,
    ma_slope,
    macd,
    rsi,
    sma,
    stochastic,
)
from sktui.services.quant_analyst import QuantMetrics, compute_metrics

logger = logging.getLogger(__name__)


class SignalResult(dict):
    """Signal generation result supporting attribute and key-based access."""

    def __init__(
        self,
        action: str,
        confidence: float,
        score: float,
        reasoning: list[str],
        rsi: float,
        macd: float,
        macd_signal: float,
        macd_hist: float,
    ) -> None:
        super().__init__(
            action=action,
            signal_type=action,
            confidence=confidence,
            confidence_pct=confidence,
            score=score,
            reasoning=reasoning,
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            macd_hist=macd_hist,
        )

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'SignalResult' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class StockAnalysisResult(dict):
    """Analysis result dictionary supporting both key access and attribute access."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(data)

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'StockAnalysisResult' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class StockAnalyzer:
    """Orchestrator for technical and quantitative analysis of Indian equities."""

    def __init__(self, client: Any = None, risk_free_rate: float = 0.05) -> None:
        self.client = client
        self.risk_free_rate = risk_free_rate

    def _fetch_bars(self, symbol: str, period: str = "1y") -> dict[str, list[float]]:
        """Fetch authentic or synthetic OHLCV bar series."""
        clean_sym = symbol.strip().upper()
        if self.client and hasattr(self.client, "historical"):
            from sktui.utils import resolve_code
            code = resolve_code(clean_sym, "NC")
            try:
                rows = self.client.historical("NC", code, "daily")
                if rows:
                    return {
                        "open": [float(r.get("open", 0.0)) for r in rows],
                        "high": [float(r.get("high", 0.0)) for r in rows],
                        "low": [float(r.get("low", 0.0)) for r in rows],
                        "close": [float(r.get("close", 0.0)) for r in rows],
                        "volume": [float(r.get("volume", 0.0)) for r in rows],
                    }
            except Exception as exc:
                logger.debug("Live fetch failed for %s: %s", clean_sym, exc)

        # Fallback to high-fidelity synthetic paper history
        from sktui.api.paper_trading import generate_paper_history
        base_p = KNOWN_BASE_PRICES.get(clean_sym, 100.0)
        from sktui.utils import resolve_code
        code = resolve_code(clean_sym, "NC") or 2475
        bars = generate_paper_history("NC", code, "daily", bars_count=120, base_price=base_p)
        return {
            "open": [float(b["open"]) for b in bars],
            "high": [float(b["high"]) for b in bars],
            "low": [float(b["low"]) for b in bars],
            "close": [float(b["close"]) for b in bars],
            "volume": [float(b["volume"]) for b in bars],
        }

    def generate_signal(
        self,
        rsi_vals: Sequence[float | None],
        macd_lines: tuple[Sequence[float | None], Sequence[float | None], Sequence[float | None]],
    ) -> SignalResult:
        """Generate combined RSI + MACD trading signal with confidence and reasoning."""
        macd_line, sig_line, hist = macd_lines

        # Extract last valid values
        cur_rsi = next((x for x in reversed(rsi_vals) if x is not None), 50.0)
        cur_m = next((x for x in reversed(macd_line) if x is not None), 0.0)
        cur_s = next((x for x in reversed(sig_line) if x is not None), 0.0)
        cur_h = next((x for x in reversed(hist) if x is not None), 0.0)

        # Crossover check
        v_m = [x for x in macd_line if x is not None]
        v_s = [x for x in sig_line if x is not None]
        prev_m = v_m[-2] if len(v_m) >= 2 else cur_m
        prev_s = v_s[-2] if len(v_s) >= 2 else cur_s

        bull_cross = (prev_m <= prev_s) and (cur_m > cur_s)
        bear_cross = (prev_m >= prev_s) and (cur_m < cur_s)

        action = "NEUTRAL"
        confidence = 50.0
        score = 0.0
        reasoning: list[str] = []

        if cur_rsi < 35.0 and bull_cross:
            action = "STRONG_BUY"
            confidence = 90.0
            score = 2.0
            reasoning.append(f"RSI oversold ({cur_rsi:.1f} < 35)")
            reasoning.append("MACD bullish crossover confirmed")
        elif bull_cross or (cur_rsi < 45.0 and cur_m > cur_s):
            action = "BUY"
            confidence = 75.0
            score = 1.0
            if bull_cross:
                reasoning.append("MACD bullish crossover")
            if cur_rsi < 45.0:
                reasoning.append(f"RSI favorable ({cur_rsi:.1f})")
            if cur_m > cur_s:
                reasoning.append("MACD line above signal line")
        elif cur_rsi > 65.0 and bear_cross:
            action = "STRONG_SELL"
            confidence = 90.0
            score = -2.0
            reasoning.append(f"RSI overbought ({cur_rsi:.1f} > 65)")
            reasoning.append("MACD bearish crossover confirmed")
        elif bear_cross or (cur_rsi > 55.0 and cur_m < cur_s):
            action = "SELL"
            confidence = 75.0
            score = -1.0
            if bear_cross:
                reasoning.append("MACD bearish crossover")
            if cur_rsi > 55.0:
                reasoning.append(f"RSI elevated ({cur_rsi:.1f})")
            if cur_m < cur_s:
                reasoning.append("MACD line below signal line")
        else:
            action = "NEUTRAL"
            confidence = 50.0
            score = 0.0
            reasoning.append(f"RSI neutral ({cur_rsi:.1f})")
            reasoning.append("No definitive MACD crossover")

        return SignalResult(
            action=action,
            confidence=confidence,
            score=score,
            reasoning=reasoning,
            rsi=cur_rsi,
            macd=cur_m,
            macd_signal=cur_s,
            macd_hist=cur_h,
        )

    def analyze_stock(
        self,
        symbol: str,
        ohlcv: dict[str, Sequence[float]] | None = None,
        period: str = "1y",
        benchmark_ohlcv: dict[str, Sequence[float]] | None = None,
    ) -> StockAnalysisResult:
        """Perform full technical and quantitative analysis for a symbol."""
        clean_sym = symbol.strip().upper()
        data = ohlcv or self._fetch_bars(clean_sym, period)

        high = list(data.get("high", []))
        low = list(data.get("low", []))
        close = list(data.get("close", []))
        vol = list(data.get("volume", []))

        # 1. Technical Indicators
        rsi_series = rsi(close, 14)
        macd_series = macd(close, 12, 26, 9)
        bb_upper, bb_mid, bb_lower = bollinger_bands(close, 20, 2.0)
        stoch_k, stoch_d = stochastic(high, low, close, 14, 3)
        adx_vals, plus_di, minus_di = adx(high, low, close, 14)
        sma_20 = sma(close, 20)
        sma_50 = sma(close, 50)
        ema_21 = ema(close, 21)
        slope_ma = ma_slope(close, 20, 5)

        # 2. Benchmark data (NIFTY50)
        bench_close: list[float] | None = None
        if benchmark_ohlcv and "close" in benchmark_ohlcv:
            bench_close = list(benchmark_ohlcv["close"])
        else:
            bench_bars = self._fetch_bars("NIFTY50", period)
            bench_close = list(bench_bars.get("close", []))

        # 3. Quant Risk Metrics
        metrics = compute_metrics(close, benchmark_prices=bench_close, risk_free_rate=self.risk_free_rate)

        # 4. Signal Generation
        sig_result = self.generate_signal(rsi_series, macd_series)

        cur_price = close[-1] if close else 0.0
        prev_price = close[-2] if len(close) >= 2 else cur_price
        chg = cur_price - prev_price
        chg_pct = (chg / prev_price * 100.0) if prev_price > 0.0 else 0.0

        # Latest scalar indicator values
        cur_bb_u = bb_upper[-1] if bb_upper else None
        cur_bb_m = bb_mid[-1] if bb_mid else None
        cur_bb_l = bb_lower[-1] if bb_lower else None
        bb_bw = ((cur_bb_u - cur_bb_l) / cur_bb_m) if (cur_bb_u and cur_bb_l and cur_bb_m and cur_bb_m > 0) else 0.0

        cur_stoch_k = stoch_k[-1] if stoch_k else None
        cur_stoch_d = stoch_d[-1] if stoch_d else None
        cur_adx = adx_vals[-1] if adx_vals else None
        cur_pdi = plus_di[-1] if plus_di else None
        cur_mdi = minus_di[-1] if minus_di else None
        cur_sma_20 = sma_20[-1] if sma_20 else None
        cur_sma_50 = sma_50[-1] if sma_50 else None
        cur_ema_21 = ema_21[-1] if ema_21 else None
        cur_slope = slope_ma[-1] if slope_ma else None

        # Indicator conditions / interpretations
        rsi_cond = "Oversold" if sig_result.rsi < 35 else ("Overbought" if sig_result.rsi > 65 else "Neutral")
        macd_cond = "Bullish Momentum" if sig_result.macd > sig_result.macd_signal else "Bearish Momentum"
        stoch_cond = "Oversold" if (cur_stoch_k is not None and cur_stoch_k < 20) else ("Overbought" if (cur_stoch_k is not None and cur_stoch_k > 80) else "Neutral")
        adx_cond = "Strong Trend" if (cur_adx is not None and cur_adx > 25) else "Weak / Ranging"
        bb_cond = "Upper Band Touch" if (cur_bb_u and cur_price >= cur_bb_u) else ("Lower Band Touch" if (cur_bb_l and cur_price <= cur_bb_l) else "Within Bands")
        ma_trend_str = "Bullish (SMA20 > SMA50)" if (cur_sma_20 and cur_sma_50 and cur_sma_20 > cur_sma_50) else "Bearish / Neutral"
        ma_slope_cond = "Upward Slope" if (cur_slope and cur_slope > 0) else "Downward / Flat"

        result_dict = {
            "symbol": clean_sym,
            "current_price": cur_price,
            "ltp": cur_price,
            "price": cur_price,
            "change": chg,
            "change_pct": chg_pct,
            "return_pct": chg_pct,
            "indicators": {
                "rsi": sig_result.rsi,
                "macd": sig_result.macd,
                "macd_signal": sig_result.macd_signal,
                "macd_hist": sig_result.macd_hist,
                "bb_upper": cur_bb_u,
                "bb_mid": cur_bb_m,
                "bb_lower": cur_bb_l,
                "bb_bandwidth": bb_bw,
                "stoch_k": cur_stoch_k,
                "stoch_d": cur_stoch_d,
                "adx": cur_adx,
                "plus_di": cur_pdi,
                "minus_di": cur_mdi,
                "sma_20": cur_sma_20,
                "sma_50": cur_sma_50,
                "ema_21": cur_ema_21,
                "ma_slope": cur_slope,
            },
            "rsi": sig_result.rsi,
            "macd_line": sig_result.macd,
            "macd_signal": sig_result.macd_signal,
            "macd_hist": sig_result.macd_hist,
            "bb_upper": cur_bb_u,
            "bb_mid": cur_bb_m,
            "bb_lower": cur_bb_l,
            "bb_bandwidth": bb_bw,
            "stoch_k": cur_stoch_k,
            "stoch_d": cur_stoch_d,
            "adx": cur_adx,
            "plus_di": cur_pdi,
            "minus_di": cur_mdi,
            "sma_20": cur_sma_20,
            "sma_50": cur_sma_50,
            "ema_21": cur_ema_21,
            "ma_trend": ma_trend_str,
            "rsi_condition": rsi_cond,
            "macd_condition": macd_cond,
            "stoch_condition": stoch_cond,
            "adx_condition": adx_cond,
            "bb_condition": bb_cond,
            "ma_slope_condition": ma_slope_cond,
            "metrics": metrics,
            "signal": sig_result,
            "score": sig_result.score,
        }

        return StockAnalysisResult(result_dict)

    def analyze(self, symbol: str, indicators: list[str] | None = None, period: str = "1y") -> StockAnalysisResult:
        """Convenience alias for analyze_stock."""
        return self.analyze_stock(symbol, period=period)

    def compare(self, symbols: list[str], rank_by: str = "sharpe", period: str = "1y") -> list[dict[str, Any]]:
        """Compare multiple symbols and rank by requested quantitative or technical factor."""
        results: list[dict[str, Any]] = []
        for sym in symbols:
            report = self.analyze_stock(sym, period=period)
            m: QuantMetrics = report.metrics
            score = 0.0
            if rank_by == "sharpe":
                score = m.sharpe_ratio
            elif rank_by == "return":
                score = m.mean_return
            elif rank_by == "momentum":
                score = report.rsi or 50.0
            elif rank_by == "volatility":
                score = -m.annual_volatility  # Lower volatility gets higher rank
            elif rank_by == "sortino":
                score = m.sortino_ratio
            elif rank_by == "drawdown":
                score = -m.max_drawdown  # Lower drawdown gets higher rank
            elif rank_by == "score":
                score = report.score
            else:
                score = m.sharpe_ratio

            results.append({
                "symbol": report.symbol,
                "price": report.current_price,
                "ltp": report.current_price,
                "change_pct": report.change_pct,
                "return_pct": report.change_pct,
                "sharpe": m.sharpe_ratio,
                "sharpe_ratio": m.sharpe_ratio,
                "volatility": m.annual_volatility,
                "volatility_pct": m.annual_volatility * 100.0,
                "annual_volatility": m.annual_volatility,
                "mean_return": m.mean_return,
                "sortino": m.sortino_ratio,
                "sortino_ratio": m.sortino_ratio,
                "max_drawdown": m.max_drawdown,
                "max_drawdown_pct": m.max_drawdown * 100.0,
                "var_95": m.var_95,
                "rsi": report.rsi,
                "signal": report.signal.action,
                "action": report.signal.action,
                "confidence": report.signal.confidence,
                "rank_score": score,
            })

        results.sort(key=lambda x: x["rank_score"], reverse=True)
        for idx, item in enumerate(results, start=1):
            item["rank"] = idx

        return results
