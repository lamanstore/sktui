"""Multi-Indicator Composite Signal Generation Engine for SKTUI.

Pure-Python implementation of a 7-indicator ensemble voting engine
(RSI, MACD, Bollinger Bands, SMA Trend Alignment, Volume Spike,
Stochastic Oscillator %K/%D, and ADX with +DI/-DI), normalized composite score
in [-2.0, 2.0], 5-tier classification, confidence percentage, dynamic ATR-based
risk management (Stop Loss / Take Profit with 2.0 R:R), and watchlist scanner.
Zero binary dependencies (math, statistics, dataclasses only).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from sktui.services.indicators import (
    adx,
    atr,
    bollinger_bands,
    macd,
    rsi,
    sma,
    stochastic,
)

logger = logging.getLogger(__name__)


@dataclass
class CompositeSignal:
    """Consolidated 7-indicator composite trading signal with dynamic risk management."""
    symbol: str
    price: float
    signal_type: str            # "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG_SELL"
    score: float                # Normalized composite score in [-2.0, 2.0]
    confidence_pct: float       # Directional agreement confidence in [0.0, 100.0]
    indicator_votes: dict[str, int]
    stop_loss: float            # Dynamic ATR-based Stop Loss price
    take_profit: float          # Dynamic ATR-based Take Profit price
    risk_reward_ratio: float    # Take Profit distance / Stop Loss distance
    atr: float = 0.0            # 14-period ATR
    indicator_details: dict[str, Any] = field(default_factory=dict)
    reasoning: list[str] = field(default_factory=list)

    # UI/CLI Ergonomic Properties & Dict-like access
    @property
    def action(self) -> str:
        return self.signal_type

    @property
    def confidence(self) -> float:
        return self.confidence_pct

    @property
    def ltp(self) -> float:
        return self.price

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "ltp": self.price,
            "signal_type": self.signal_type,
            "action": self.signal_type,
            "score": self.score,
            "confidence_pct": self.confidence_pct,
            "confidence": self.confidence_pct,
            "indicator_votes": self.indicator_votes,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward_ratio": self.risk_reward_ratio,
            "atr": self.atr,
            "indicator_details": self.indicator_details,
            "reasoning": self.reasoning,
        }

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            return default


def _clean_series(values: Sequence[Any] | None) -> list[float]:
    """Clean series removing non-finite and None elements."""
    if not values:
        return []
    res: list[float] = []
    for v in values:
        if v is None or isinstance(v, bool):
            continue
        try:
            fv = float(v)
            if math.isfinite(fv):
                res.append(fv)
        except (ValueError, TypeError):
            continue
    return res


def evaluate_signals(
    symbol: str,
    ohlcv: dict[str, Sequence[Any]],
    weights: dict[str, float] | None = None,
) -> CompositeSignal:
    """Evaluate 7 technical indicators and generate composite signal.

    Indicators:
    1. RSI (14-period)
    2. MACD (12, 26, 9)
    3. Bollinger Bands (20, 2.0 std dev)
    4. SMA Trend Alignment (20, 50, 200)
    5. Volume Spike (20-period avg confirmation)
    6. Stochastic Oscillator (14, 3 %K/%D)
    7. ADX (14-period with +DI/-DI)
    """
    clean_sym = symbol.strip().upper() if symbol else "UNKNOWN"
    closes = _clean_series(ohlcv.get("close") or ohlcv.get("closes"))
    highs = _clean_series(ohlcv.get("high") or ohlcv.get("highs"))
    lows = _clean_series(ohlcv.get("low") or ohlcv.get("lows"))
    opens = _clean_series(ohlcv.get("open") or ohlcv.get("opens"))
    volumes = _clean_series(ohlcv.get("volume") or ohlcv.get("volumes"))

    n_bars = len(closes)
    if n_bars == 0:
        return CompositeSignal(
            symbol=clean_sym,
            price=0.0,
            signal_type="NEUTRAL",
            score=0.0,
            confidence_pct=0.0,
            indicator_votes={},
            stop_loss=0.0,
            take_profit=0.0,
            risk_reward_ratio=0.0,
            atr=0.0,
            reasoning=["Empty OHLCV dataset"],
        )

    current_price = closes[-1]
    if len(highs) < n_bars:
        highs = closes[:]
    if len(lows) < n_bars:
        lows = closes[:]
    if len(opens) < n_bars:
        opens = closes[:]
    if len(volumes) < n_bars:
        volumes = [0.0] * n_bars

    default_weights = {
        "rsi": 1.0,
        "macd": 1.0,
        "bollinger": 1.0,
        "trend": 1.0,
        "volume": 1.0,
        "stochastic": 1.0,
        "adx": 1.0,
    }
    w_map = dict(default_weights)
    if weights:
        w_map.update(weights)

    float_votes: dict[str, float] = {}
    int_votes: dict[str, int] = {}
    details: dict[str, Any] = {}
    reasons: list[str] = []

    # Pre-evaluate ADX and SMA Trend direction for regime awareness
    adx_vals, plus_di, minus_di = adx(highs, lows, closes, period=14)
    cur_adx = adx_vals[-1] if adx_vals and adx_vals[-1] is not None else 0.0
    p_di = plus_di[-1] if plus_di and plus_di[-1] is not None else 0.0
    m_di = minus_di[-1] if minus_di and minus_di[-1] is not None else 0.0

    s20 = sma(closes, 20)[-1] if n_bars >= 20 else None
    s50 = sma(closes, 50)[-1] if n_bars >= 50 else None
    s200 = sma(closes, 200)[-1] if n_bars >= 200 else None

    is_strong_uptrend = (cur_adx > 20.0 and p_di > m_di) or (s20 is not None and current_price > s20)
    is_strong_downtrend = (cur_adx > 20.0 and m_di > p_di) or (s20 is not None and current_price < s20)

    # 1. RSI (14)
    r_series = rsi(closes, period=14)
    r_val = r_series[-1] if r_series and r_series[-1] is not None else None
    if r_val is not None:
        if r_val < 30.0:
            if is_strong_downtrend and cur_adx > 25.0:
                v_rsi = -0.75
                cond = "Oversold Breakdown"
                reasons.append(f"RSI oversold breakdown ({r_val:.1f} < 30)")
            else:
                v_rsi = 1.0
                cond = "Oversold"
                reasons.append(f"RSI oversold ({r_val:.1f} < 30)")
        elif r_val > 70.0:
            if is_strong_uptrend and cur_adx > 25.0:
                v_rsi = 0.75
                cond = "Bullish Momentum"
                reasons.append(f"RSI bullish momentum ({r_val:.1f} > 70)")
            else:
                v_rsi = -1.0
                cond = "Overbought"
                reasons.append(f"RSI overbought ({r_val:.1f} > 70)")
        elif 50.0 <= r_val <= 70.0:
            v_rsi = 0.50
            cond = "Bullish Momentum"
            reasons.append(f"RSI bullish momentum ({r_val:.1f})")
        elif 30.0 <= r_val < 50.0:
            v_rsi = -0.50
            cond = "Bearish Momentum"
            reasons.append(f"RSI bearish momentum ({r_val:.1f})")
        else:
            v_rsi = 0.0
            cond = "Neutral"
        float_votes["rsi"] = v_rsi
        int_votes["rsi"] = 1 if v_rsi >= 0.5 else (-1 if v_rsi <= -0.5 else 0)
        details["rsi"] = {"value": round(r_val, 2), "condition": cond}
    else:
        float_votes["rsi"] = 0.0
        int_votes["rsi"] = 0
        details["rsi"] = {"value": None, "condition": "Insufficient Data"}

    # 2. MACD (12, 26, 9)
    macd_l, macd_s, macd_h = macd(closes, 12, 26, 9)
    if macd_l and macd_s and macd_l[-1] is not None and macd_s[-1] is not None:
        m_cur, s_cur = macd_l[-1], macd_s[-1]
        h_cur = macd_h[-1] if macd_h and macd_h[-1] is not None else 0.0
        m_prev = macd_l[-2] if len(macd_l) >= 2 and macd_l[-2] is not None else m_cur
        s_prev = macd_s[-2] if len(macd_s) >= 2 and macd_s[-2] is not None else s_cur
        h_prev = macd_h[-2] if len(macd_h) >= 2 and macd_h[-2] is not None else h_cur

        crossover_bull = (m_prev <= s_prev) and (m_cur > s_cur)
        crossover_bear = (m_prev >= s_prev) and (m_cur < s_cur)

        if crossover_bull:
            v_macd = 1.0
            cond = "Bullish Crossover"
            reasons.append(f"MACD bullish crossover ({m_cur:.2f} > {s_cur:.2f})")
        elif crossover_bear:
            v_macd = -1.0
            cond = "Bearish Crossover"
            reasons.append(f"MACD bearish crossover ({m_cur:.2f} < {s_cur:.2f})")
        elif m_cur > s_cur or (m_cur > 0 and is_strong_uptrend):
            v_macd = 0.75 if h_cur >= h_prev else 0.50
            cond = "Bullish Alignment"
            reasons.append(f"MACD above signal ({m_cur:.2f} > {s_cur:.2f})")
        elif m_cur < s_cur or (m_cur < 0 and is_strong_downtrend):
            v_macd = -0.75 if h_cur <= h_prev else -0.50
            cond = "Bearish Alignment"
            reasons.append(f"MACD below signal ({m_cur:.2f} < {s_cur:.2f})")
        else:
            v_macd = 0.0
            cond = "Neutral"

        float_votes["macd"] = v_macd
        int_votes["macd"] = 1 if v_macd >= 0.5 else (-1 if v_macd <= -0.5 else 0)
        details["macd"] = {"macd": round(m_cur, 2), "signal": round(s_cur, 2), "condition": cond}
    else:
        float_votes["macd"] = 0.0
        int_votes["macd"] = 0
        details["macd"] = {"macd": None, "signal": None, "condition": "Insufficient Data"}

    # 3. Bollinger Bands (20, 2.0 std dev)
    bb_u, bb_m, bb_l = bollinger_bands(closes, period=20, std_dev=2.0)
    if bb_u and bb_u[-1] is not None and bb_l[-1] is not None:
        u_val, m_val, l_val = bb_u[-1], bb_m[-1], bb_l[-1]
        width = u_val - l_val
        pct_b = (current_price - l_val) / width if width > 1e-6 else 0.5
        if pct_b < 0.0:
            if is_strong_downtrend and cur_adx > 25.0:
                v_bb = -0.75
                cond = "Lower Band Breakdown"
                reasons.append(f"Bollinger lower band breakdown (%B={pct_b:.2f})")
            else:
                v_bb = 1.0
                cond = "Lower Band Touch"
                reasons.append(f"Bollinger lower band breach (%B={pct_b:.2f})")
        elif pct_b > 1.0:
            if is_strong_uptrend and cur_adx > 25.0:
                v_bb = 0.75
                cond = "Upper Band Walking"
                reasons.append(f"Bollinger upper band walking (%B={pct_b:.2f})")
            else:
                v_bb = -1.0
                cond = "Upper Band Touch"
                reasons.append(f"Bollinger upper band breach (%B={pct_b:.2f})")
        elif 0.70 <= pct_b <= 1.0:
            v_bb = 0.50 if is_strong_uptrend else 0.0
            cond = "Upper Band Zone"
        elif 0.0 <= pct_b <= 0.30:
            v_bb = -0.50 if is_strong_downtrend else 0.0
            cond = "Lower Band Zone"
        else:
            v_bb = 0.0
            cond = "Within Bands"

        float_votes["bollinger"] = v_bb
        int_votes["bollinger"] = 1 if v_bb >= 0.5 else (-1 if v_bb <= -0.5 else 0)
        details["bollinger"] = {"pct_b": round(pct_b, 2), "upper": round(u_val, 2), "lower": round(l_val, 2), "condition": cond}
    else:
        float_votes["bollinger"] = 0.0
        int_votes["bollinger"] = 0
        details["bollinger"] = {"condition": "Insufficient Data"}

    # 4. SMA Trend Alignment (20, 50, 200)
    if s200 is not None and s50 is not None and s20 is not None:
        if current_price > s20 > s50 > s200:
            v_trend = 1.0
            cond = "Strong Bullish Trend"
            reasons.append("Price > SMA20 > SMA50 > SMA200")
        elif current_price < s20 < s50 < s200:
            v_trend = -1.0
            cond = "Strong Bearish Trend"
            reasons.append("Price < SMA20 < SMA50 < SMA200")
        elif current_price > s20 > s50:
            v_trend = 0.50
            cond = "Bullish Trend"
        elif current_price < s20 < s50:
            v_trend = -0.50
            cond = "Bearish Trend"
        else:
            v_trend = 0.0
            cond = "Mixed Trend"
    elif s50 is not None and s20 is not None:
        if current_price > s20 > s50:
            v_trend = 1.0
            cond = "Bullish Trend"
            reasons.append("Price > SMA20 > SMA50")
        elif current_price < s20 < s50:
            v_trend = -1.0
            cond = "Bearish Trend"
            reasons.append("Price < SMA20 < SMA50")
        else:
            v_trend = 0.0
            cond = "Mixed Trend"
    elif s20 is not None:
        if current_price > s20:
            v_trend = 0.50
            cond = "Price > SMA20"
        elif current_price < s20:
            v_trend = -0.50
            cond = "Price < SMA20"
        else:
            v_trend = 0.0
            cond = "Neutral"
    else:
        v_trend = 0.0
        cond = "Insufficient Data"

    float_votes["trend"] = v_trend
    int_votes["trend"] = 1 if v_trend >= 0.5 else (-1 if v_trend <= -0.5 else 0)
    details["trend"] = {"condition": cond}

    # 5. Volume Spike (20-period avg confirmation)
    if len(volumes) >= 20 and sum(volumes[-20:]) > 0:
        vol_cur = volumes[-1]
        v_avg = sum(volumes[-20:]) / 20.0
        r_vol = vol_cur / v_avg if v_avg > 0 else 1.0
        delta_p = closes[-1] - closes[-2] if n_bars >= 2 else 0.0

        if r_vol >= 1.5:
            if delta_p > 0:
                v_vol = 1.0
                cond = "Bullish Volume Spike"
                reasons.append(f"Volume surge ({r_vol:.1f}x) confirms price rise")
            elif delta_p < 0:
                v_vol = -1.0
                cond = "Bearish Volume Spike"
                reasons.append(f"Volume surge ({r_vol:.1f}x) confirms price drop")
            else:
                v_vol = 0.0
                cond = "Neutral Volume Spike"
        else:
            v_vol = 0.0
            cond = "Normal Volume"
        details["volume"] = {"ratio": round(r_vol, 2), "condition": cond}
    else:
        v_vol = 0.0
        cond = "No Volume"
        details["volume"] = {"ratio": 0.0, "condition": cond}

    float_votes["volume"] = v_vol
    int_votes["volume"] = 1 if v_vol >= 0.5 else (-1 if v_vol <= -0.5 else 0)

    # 6. Stochastic Oscillator (14, 3 %K/%D)
    stoch_k, stoch_d = stochastic(highs, lows, closes, k_period=14, d_period=3)
    if stoch_k and stoch_d and stoch_k[-1] is not None and stoch_d[-1] is not None:
        k_cur, d_cur = stoch_k[-1], stoch_d[-1]
        k_prev = stoch_k[-2] if len(stoch_k) >= 2 and stoch_k[-2] is not None else k_cur
        d_prev = stoch_d[-2] if len(stoch_d) >= 2 and stoch_d[-2] is not None else d_cur

        if k_cur < 20.0:
            if is_strong_downtrend and cur_adx > 25.0:
                v_stoch = -0.75
                cond = "Oversold Trend"
                reasons.append(f"Stochastic trend breakdown (%K={k_cur:.1f})")
            else:
                v_stoch = 1.0
                cond = "Oversold"
                reasons.append(f"Stochastic oversold (%K={k_cur:.1f} < 20)")
        elif k_cur > 80.0:
            if is_strong_uptrend and cur_adx > 25.0:
                v_stoch = 0.75
                cond = "Overbought Trend"
                reasons.append(f"Stochastic trend breakout (%K={k_cur:.1f})")
            else:
                v_stoch = -1.0
                cond = "Overbought"
                reasons.append(f"Stochastic overbought (%K={k_cur:.1f} > 80)")
        elif k_cur >= 50.0:
            v_stoch = 0.50 if k_cur >= d_cur else 0.0
            cond = "Bullish Momentum"
        elif k_cur < 50.0:
            v_stoch = -0.50 if k_cur <= d_cur else 0.0
            cond = "Bearish Momentum"
        else:
            v_stoch = 0.0
            cond = "Neutral"

        float_votes["stochastic"] = v_stoch
        int_votes["stochastic"] = 1 if v_stoch >= 0.5 else (-1 if v_stoch <= -0.5 else 0)
        details["stochastic"] = {"k": round(k_cur, 2), "d": round(d_cur, 2), "condition": cond}
    else:
        float_votes["stochastic"] = 0.0
        int_votes["stochastic"] = 0
        details["stochastic"] = {"condition": "Insufficient Data"}

    # 7. ADX (14-period with +DI/-DI)
    if adx_vals and plus_di and minus_di and adx_vals[-1] is not None:
        if cur_adx > 25.0:
            if p_di > m_di:
                v_adx = 1.0
                cond = "Strong Bullish Trend"
                reasons.append(f"ADX strong bullish trend ({cur_adx:.1f}, +DI > -DI)")
            elif m_di > p_di:
                v_adx = -1.0
                cond = "Strong Bearish Trend"
                reasons.append(f"ADX strong bearish trend ({cur_adx:.1f}, -DI > +DI)")
            else:
                v_adx = 0.0
                cond = "Strong Trend Neutral"
        else:
            if p_di > m_di:
                v_adx = 0.25
                cond = "Weak Bullish Bias"
            elif m_di > p_di:
                v_adx = -0.25
                cond = "Weak Bearish Bias"
            else:
                v_adx = 0.0
                cond = "Ranging / Neutral"

        float_votes["adx"] = v_adx
        int_votes["adx"] = 1 if v_adx >= 0.5 else (-1 if v_adx <= -0.5 else 0)
        details["adx"] = {"adx": round(cur_adx, 2), "+di": round(p_di, 2), "-di": round(m_di, 2), "condition": cond}
    else:
        float_votes["adx"] = 0.0
        int_votes["adx"] = 0
        details["adx"] = {"condition": "Insufficient Data"}

    # Calculate Composite Score [-2.0, 2.0]
    total_w = sum(w_map.get(k, 1.0) for k in float_votes)
    if total_w > 0:
        raw_score = sum(w_map.get(k, 1.0) * float_votes[k] for k in float_votes) / total_w
        composite_score = round(max(-2.0, min(2.0, raw_score * 2.0)), 2)
    else:
        composite_score = 0.0

    # 5-Tier Classification
    if composite_score >= 1.2:
        sig_tier = "STRONG_BUY"
    elif composite_score >= 0.4:
        sig_tier = "BUY"
    elif composite_score <= -1.2:
        sig_tier = "STRONG_SELL"
    elif composite_score <= -0.4:
        sig_tier = "SELL"
    else:
        sig_tier = "NEUTRAL"

    # Confidence Calculation [0.0, 100.0]
    pos_conv = sum(w_map.get(k, 1.0) * v for k, v in float_votes.items() if v > 0)
    neg_conv = sum(w_map.get(k, 1.0) * abs(v) for k, v in float_votes.items() if v < 0)

    if composite_score > 0:
        agreement = pos_conv / (pos_conv + neg_conv + 1e-6)
        conf = 50.0 + (composite_score / 2.0) * 50.0 * agreement
    elif composite_score < 0:
        agreement = neg_conv / (pos_conv + neg_conv + 1e-6)
        conf = 50.0 + (abs(composite_score) / 2.0) * 50.0 * agreement
    else:
        if pos_conv == 0 and neg_conv == 0:
            conf = 50.0
        else:
            conflict_ratio = min(pos_conv, neg_conv) / max(1e-6, total_w / 2.0)
            conf = max(10.0, 50.0 - 40.0 * conflict_ratio)

    confidence_pct = round(max(0.0, min(100.0, conf)), 1)

    # Dynamic ATR Risk Management
    atr_series = atr(highs, lows, closes, period=14)
    atr_val = atr_series[-1] if atr_series and atr_series[-1] is not None else None
    if atr_val is None or atr_val <= 0.0 or not math.isfinite(atr_val):
        atr_val = max(0.01, current_price * 0.02)
    # Ensure minimum floor of 0.5% price
    min_atr = max(0.01, current_price * 0.005)
    effective_atr = max(atr_val, min_atr)

    if current_price <= 0.0:
        stop_loss = 0.0
        take_profit = 0.0
        risk_reward = 0.0
    elif sig_tier in ("STRONG_BUY", "BUY", "NEUTRAL"):
        stop_loss = max(0.01, round(current_price - 1.5 * effective_atr, 2))
        take_profit = round(current_price + 3.0 * effective_atr, 2)
        sl_dist = max(0.01, current_price - stop_loss)
        risk_reward = round((take_profit - current_price) / sl_dist, 2)
    else:  # STRONG_SELL, SELL
        stop_loss = round(current_price + 1.5 * effective_atr, 2)
        take_profit = max(0.01, round(current_price - 3.0 * effective_atr, 2))
        sl_dist = max(0.01, stop_loss - current_price)
        risk_reward = round((current_price - take_profit) / sl_dist, 2)

    return CompositeSignal(
        symbol=clean_sym,
        price=round(current_price, 2),
        signal_type=sig_tier,
        score=composite_score,
        confidence_pct=confidence_pct,
        indicator_votes=int_votes,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward_ratio=risk_reward,
        atr=round(effective_atr, 2),
        indicator_details=details,
        reasoning=reasons,
    )


def scan_watchlist(
    symbols: Sequence[str],
    ohlcv_map: dict[str, dict[str, Sequence[Any]]] | None = None,
    direction: str | None = None,
    min_confidence: float = 0.0,
    weights: dict[str, float] | None = None,
) -> list[CompositeSignal]:
    """Scan multi-symbol universe, filter by direction and confidence, and rank results."""
    from sktui.api.paper_trading import generate_paper_history
    from sktui.config import KNOWN_BASE_PRICES
    from sktui.utils import resolve_code

    results: list[CompositeSignal] = []
    seen: set[str] = set()

    for raw_sym in symbols:
        sym = raw_sym.strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)

        ohlcv = (ohlcv_map or {}).get(sym)
        if not ohlcv or not ohlcv.get("close"):
            base_p = KNOWN_BASE_PRICES.get(sym, 100.0)
            code = resolve_code(sym, "NC") or 2475
            bars = generate_paper_history("NC", code, "daily", bars_count=120, base_price=base_p)
            ohlcv = {
                "open": [float(b["open"]) for b in bars],
                "high": [float(b["high"]) for b in bars],
                "low": [float(b["low"]) for b in bars],
                "close": [float(b["close"]) for b in bars],
                "volume": [float(b["volume"]) for b in bars],
            }

        sig = evaluate_signals(sym, ohlcv, weights=weights)

        # Filter by minimum confidence
        if sig.confidence_pct < min_confidence:
            continue

        # Filter by direction
        if direction:
            d_norm = direction.strip().upper()
            if d_norm not in ("ALL", ""):
                if d_norm in ("BUY", "LONG") and sig.signal_type not in ("BUY", "STRONG_BUY"):
                    continue
                elif d_norm in ("SELL", "SHORT") and sig.signal_type not in ("SELL", "STRONG_SELL"):
                    continue
                elif d_norm in ("STRONG_BUY", "STRONG_SELL", "NEUTRAL") and sig.signal_type != d_norm:
                    continue

        results.append(sig)

    # Rank: highest confidence first, then strongest absolute score
    results.sort(key=lambda s: (s.confidence_pct, abs(s.score)), reverse=True)
    return results


class SignalEngine:
    """Stateful Service for Signal Scanning and Analysis."""

    def __init__(self, client: Any = None) -> None:
        self.client = client

    def evaluate(self, symbol: str, ohlcv: dict[str, Sequence[Any]]) -> CompositeSignal:
        return evaluate_signals(symbol, ohlcv)

    def scan(
        self,
        symbols: Sequence[str],
        ohlcv_map: dict[str, dict[str, Sequence[Any]]] | None = None,
        direction: str | None = None,
        min_confidence: float = 0.0,
    ) -> list[CompositeSignal]:
        return scan_watchlist(symbols, ohlcv_map, direction=direction, min_confidence=min_confidence)
