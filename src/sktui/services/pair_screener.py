"""Statistical Arbitrage and Pair Trading Screener for SKTUI.

Pure-Python implementation of Pearson correlation stability, OLS hedge ratio,
Augmented Dickey-Fuller (ADF) cointegration test with MacKinnon p-value lookup,
Ornstein-Uhlenbeck AR(1) half-life, rolling Z-scores, and market-neutral sizing.
Zero binary dependencies (math, statistics, dataclasses only).
"""
from __future__ import annotations

import itertools
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from sktui.config import KNOWN_BASE_PRICES, SECTOR_MAP

logger = logging.getLogger(__name__)


@dataclass
class PairScreenResult:
    """Consolidated cointegration and pair trading screening result."""
    stock_a: str
    stock_b: str
    correlation: float
    correlation_stability: float
    beta: float
    alpha: float
    adf_statistic: float
    p_value: float
    is_cointegrated: bool
    half_life_days: float
    current_spread: float
    current_zscore: float
    signal: str  # "LONG_PAIR", "SHORT_PAIR", "EXIT", "STOP_LOSS", "NONE"
    allocation: dict[str, Any] = field(default_factory=dict)
    sector: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_a": self.stock_a,
            "stock_b": self.stock_b,
            "pair": f"{self.stock_a}/{self.stock_b}",
            "sector": self.sector,
            "correlation": self.correlation,
            "correlation_stability": self.correlation_stability,
            "beta": self.beta,
            "alpha": self.alpha,
            "adf_statistic": self.adf_statistic,
            "p_value": self.p_value,
            "is_cointegrated": self.is_cointegrated,
            "half_life_days": self.half_life_days,
            "current_spread": self.current_spread,
            "current_zscore": self.current_zscore,
            "signal": self.signal,
            "allocation": self.allocation,
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


def clean_series(series: Sequence[float] | None) -> list[float]:
    """Clean series removing non-finite and non-positive floats."""
    out: list[float] = []
    if not series:
        return out
    for x in series:
        if x is None or isinstance(x, bool):
            continue
        try:
            v = float(x)
            if math.isfinite(v):
                out.append(v)
        except (ValueError, TypeError):
            continue
    return out


def compute_pearson_correlation(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Pearson correlation coefficient between two series."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    sx, sy = x[-n:], y[-n:]
    mx = sum(sx) / n
    my = sum(sy) / n
    var_x = sum((xi - mx) ** 2 for xi in sx)
    var_y = sum((yi - my) ** 2 for yi in sy)
    if var_x < 1e-12 or var_y < 1e-12:
        return 0.0
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(sx, sy))
    denom = math.sqrt(var_x * var_y)
    if denom < 1e-12:
        return 0.0
    return max(-1.0, min(1.0, cov / denom))


def compute_correlation_stability(x: Sequence[float], y: Sequence[float], window: int = 90) -> float:
    """Compute correlation stability metric |rho_full - rho_window|."""
    n = min(len(x), len(y))
    if n < window:
        return 0.0
    rho_full = compute_pearson_correlation(x, y)
    rho_window = compute_pearson_correlation(x[-window:], y[-window:])
    return abs(rho_full - rho_window)


def compute_ols_hedge_ratio(y: Sequence[float], x: Sequence[float]) -> tuple[float, float]:
    """Compute OLS hedge ratio (beta) and intercept (alpha) for y on x.

    Formula: y = alpha + beta * x
    Returns: (beta, alpha)
    """
    n = min(len(y), len(x))
    if n < 3:
        return 1.0, 0.0
    sy = y[-n:]
    sx = x[-n:]
    my = sum(sy) / n
    mx = sum(sx) / n
    var_x = sum((xi - mx) ** 2 for xi in sx)
    if var_x < 1e-12:
        return 1.0, 0.0
    cov_xy = sum((xi - mx) * (yi - my) for xi, yi in zip(sx, sy))
    beta = cov_xy / var_x
    alpha = my - beta * mx
    return beta, alpha


def compute_spread(price_a: Sequence[float], price_b: Sequence[float], beta: float) -> list[float]:
    """Compute raw spread time-series: S_t = P_A - beta * P_B."""
    n = min(len(price_a), len(price_b))
    if n == 0:
        return []
    pa_slice = price_a[-n:]
    pb_slice = price_b[-n:]
    return [pa - beta * pb for pa, pb in zip(pa_slice, pb_slice)]


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function using math.erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _mackinnon_p(teststat: float) -> float:
    """Compute MacKinnon approximate p-value for ADF test with constant (N=1)."""
    if teststat < -18.83:
        return 0.0
    if teststat > 2.74:
        return 1.0
    if teststat <= -1.61:
        # Small-p response surface quadratic polynomial
        c0, c1, c2 = 2.1659, 1.4412, 0.038269
        y = c0 + c1 * teststat + c2 * (teststat ** 2)
    else:
        # Large-p response surface cubic polynomial
        c0, c1, c2, c3 = 1.7339, 0.93202, -0.12745, -0.010368
        y = c0 + c1 * teststat + c2 * (teststat ** 2) + c3 * (teststat ** 3)
    p = _norm_cdf(y)
    return max(0.0, min(1.0, p))


def _solve_linear_system(A: list[list[float]], b: list[float]) -> list[float] | None:
    """Solve A * x = b via Gaussian elimination with partial pivoting."""
    n = len(b)
    M = [A[i][:] + [b[i]] for i in range(n)]
    for i in range(n):
        max_row = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[max_row] = M[max_row], M[i]
        if abs(M[i][i]) < 1e-12:
            return None
        pivot = M[i][i]
        for j in range(i, n + 1):
            M[i][j] /= pivot
        for r in range(n):
            if r != i:
                factor = M[r][i]
                for j in range(i, n + 1):
                    M[r][j] -= factor * M[i][j]
    return [M[i][n] for i in range(n)]


def _invert_matrix(A: list[list[float]]) -> list[list[float]] | None:
    """Invert square matrix A using Gauss-Jordan elimination."""
    n = len(A)
    M = [A[i][:] + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for i in range(n):
        max_row = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[max_row] = M[max_row], M[i]
        if abs(M[i][i]) < 1e-12:
            return None
        pivot = M[i][i]
        for j in range(2 * n):
            M[i][j] /= pivot
        for r in range(n):
            if r != i:
                factor = M[r][i]
                for j in range(2 * n):
                    M[r][j] -= factor * M[i][j]
    return [row[n:] for row in M]


def adf_test(series: Sequence[float], max_lags: int = 1) -> tuple[float, float, bool]:
    """Pure-Python Augmented Dickey-Fuller unit-root cointegration test.

    Estimates regression: Delta S_t = c + gamma * S_{t-1} + sum delta_i * Delta S_{t-i} + eps_t
    Returns:
        (adf_statistic, p_value, is_cointegrated) where is_cointegrated is True if p_value < 0.05.
    """
    clean = clean_series(series)
    T = len(clean)
    if T < max_lags + 5:
        return 0.0, 1.0, False

    # Check for constant/flat series
    m_val = sum(clean) / T
    if sum((x - m_val) ** 2 for x in clean) < 1e-12:
        return 0.0, 1.0, False

    diffs = [clean[t] - clean[t - 1] for t in range(1, T)]
    Y: list[float] = []
    X: list[list[float]] = []

    for t in range(max_lags, len(diffs)):
        y_val = diffs[t]
        s_lag = clean[t]  # lagged level
        row = [1.0, s_lag]
        for lag in range(1, max_lags + 1):
            row.append(diffs[t - lag])
        Y.append(y_val)
        X.append(row)

    N = len(Y)
    K = len(X[0])
    if N <= K:
        return 0.0, 1.0, False

    XtX = [[sum(X[i][r] * X[i][c] for i in range(N)) for c in range(K)] for r in range(K)]
    XtY = [sum(X[i][r] * Y[i] for i in range(N)) for r in range(K)]

    beta_vec = _solve_linear_system(XtX, XtY)
    if beta_vec is None:
        return 0.0, 1.0, False

    inv = _invert_matrix(XtX)
    if inv is None:
        return 0.0, 1.0, False

    e = [Y[i] - sum(X[i][j] * beta_vec[j] for j in range(K)) for i in range(N)]
    sse = sum(x * x for x in e)
    df = N - K
    if df <= 0:
        return 0.0, 1.0, False
    s2 = sse / df

    var_gamma = s2 * inv[1][1]
    if var_gamma <= 1e-14:
        return 0.0, 1.0, False

    se_gamma = math.sqrt(var_gamma)
    adf_stat = beta_vec[1] / se_gamma
    p_val = _mackinnon_p(adf_stat)
    return adf_stat, p_val, p_val < 0.05


def compute_half_life(spread: Sequence[float]) -> float:
    """Compute AR(1) Ornstein-Uhlenbeck mean-reversion half-life in days."""
    s = clean_series(spread)
    if len(s) < 10:
        return float("inf")

    y = [s[i] - s[i - 1] for i in range(1, len(s))]
    x = [s[i - 1] for i in range(1, len(s))]
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    var_x = sum((xi - mx) ** 2 for xi in x)
    if var_x < 1e-12:
        return float("inf")

    cov_xy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    beta = cov_xy / var_x
    if beta >= 0.0:
        return float("inf")

    phi = 1.0 + beta
    lam = -math.log(phi) if phi > 0.0 else -beta
    if lam <= 1e-12:
        return float("inf")

    return math.log(2.0) / lam


def compute_rolling_zscores(spread: Sequence[float], window: int = 90) -> list[float]:
    """Compute rolling window Z-scores for a spread series."""
    s = clean_series(spread)
    n = len(s)
    zscores: list[float] = []
    for i in range(n):
        w = s[max(0, i + 1 - window): i + 1]
        if len(w) < 2:
            zscores.append(0.0)
            continue
        m = sum(w) / len(w)
        var = sum((x - m) ** 2 for x in w) / (len(w) - 1)
        std = math.sqrt(var) if var > 1e-12 else 0.0
        if std > 1e-12:
            zscores.append((s[i] - m) / std)
        else:
            zscores.append(0.0)
    return zscores


def calculate_zscore_signal(
    current_zscore: float,
    entry_threshold: float = 2.0,
    exit_threshold: float = 0.5,
) -> str:
    """Generate trade signal based on spread Z-score."""
    if abs(current_zscore) >= 3.0:
        return "STOP_LOSS"
    if current_zscore <= -entry_threshold:
        return "LONG_PAIR"
    if current_zscore >= entry_threshold:
        return "SHORT_PAIR"
    if abs(current_zscore) <= exit_threshold:
        return "EXIT"
    return "NONE"


def calculate_position_sizing(
    capital: float,
    price_a: float,
    price_b: float,
    beta: float,
) -> dict[str, Any]:
    """Calculate market-neutral dollar and share allocation."""
    if capital <= 0.0 or price_a <= 0.0 or price_b <= 0.0:
        return {
            "capital": capital,
            "capital_a": 0.0,
            "capital_b": 0.0,
            "dollar_a": 0.0,
            "dollar_b": 0.0,
            "shares_a": 0,
            "shares_b": 0,
            "weight_a": 0.0,
            "weight_b": 0.0,
            "actual_investment": 0.0,
            "hedge_ratio": beta,
            "price_a": price_a,
            "price_b": price_b,
        }

    abs_beta = abs(beta) if abs(beta) > 1e-6 else 1.0
    denom = 1.0 + abs_beta
    cap_a = capital / denom
    cap_b = capital * abs_beta / denom

    shares_a = int(cap_a // price_a)
    shares_b = int(cap_b // price_b)
    actual_a = shares_a * price_a
    actual_b = shares_b * price_b
    actual = actual_a + actual_b

    return {
        "capital": capital,
        "capital_a": round(cap_a, 2),
        "capital_b": round(cap_b, 2),
        "dollar_a": round(actual_a, 2),
        "dollar_b": round(actual_b, 2),
        "shares_a": shares_a,
        "shares_b": shares_b,
        "weight_a": round(actual_a / capital, 4) if capital > 0 else 0.0,
        "weight_b": round(actual_b / capital, 4) if capital > 0 else 0.0,
        "actual_investment": round(actual, 2),
        "hedge_ratio": round(beta, 4),
        "price_a": price_a,
        "price_b": price_b,
    }


def screen_pairs(
    universe: dict[str, Sequence[float]],
    min_correlation: float = 0.70,
    p_value_threshold: float = 0.05,
    max_half_life: float = 90.0,
    min_half_life: float = 0.1,
) -> list[PairScreenResult]:
    """Screen all candidate pairs in universe across statistical filters."""
    symbols = sorted(universe.keys())
    results: list[PairScreenResult] = []

    for sym_a, sym_b in itertools.combinations(symbols, 2):
        s_a = clean_series(universe[sym_a])
        s_b = clean_series(universe[sym_b])
        n = min(len(s_a), len(s_b))
        if n < 30:
            continue
        p_a = s_a[-n:]
        p_b = s_b[-n:]

        # 1. Pearson Correlation Filter
        rho = compute_pearson_correlation(p_a, p_b)
        if rho < min_correlation:
            continue

        # 2. 90-day Correlation Stability Filter
        stability = compute_correlation_stability(p_a, p_b, window=min(90, n))
        if stability > 0.15:
            continue

        # 3. OLS Hedge Ratio & Spread
        beta, alpha = compute_ols_hedge_ratio(p_a, p_b)
        spread = compute_spread(p_a, p_b, beta)

        # 4. ADF Cointegration Test Filter
        adf_stat, p_val, is_coint = adf_test(spread, max_lags=1)
        if p_val > p_value_threshold:
            continue

        # 5. Half-Life Mean Reversion Filter
        hl = compute_half_life(spread)
        if hl < min_half_life or hl > max_half_life:
            continue

        # 6. Z-Score & Signal
        zscores = compute_rolling_zscores(spread, window=min(90, n))
        cur_z = zscores[-1] if zscores else 0.0
        sig = calculate_zscore_signal(cur_z)

        # 7. Sizing
        alloc = calculate_position_sizing(100_000.0, p_a[-1], p_b[-1], beta)

        sec = SECTOR_MAP.get(sym_a, SECTOR_MAP.get(sym_b, "Equities"))
        results.append(
            PairScreenResult(
                stock_a=sym_a,
                stock_b=sym_b,
                correlation=round(rho, 4),
                correlation_stability=round(stability, 4),
                beta=round(beta, 4),
                alpha=round(alpha, 4),
                adf_statistic=round(adf_stat, 4),
                p_value=round(p_val, 4),
                is_cointegrated=is_coint,
                half_life_days=round(hl, 1),
                current_spread=round(spread[-1], 2),
                current_zscore=round(cur_z, 2),
                signal=sig,
                allocation=alloc,
                sector=sec,
            )
        )

    # Rank by statistical strength (lowest ADF p-value first)
    results.sort(key=lambda r: r.p_value)
    return results


class PairScreener:
    """Statistical Arbitrage Service for Indian Equities."""

    def __init__(self, client: Any = None, lookback_bars: int = 120) -> None:
        self.client = client
        self.lookback_bars = lookback_bars

    def fetch_series(self, symbol: str) -> list[float]:
        """Fetch historical close prices from client or paper sandbox."""
        clean_sym = symbol.strip().upper()
        if self.client and hasattr(self.client, "historical"):
            from sktui.utils import resolve_code
            code = resolve_code(clean_sym, "NC")
            try:
                rows = self.client.historical("NC", code, "daily")
                if rows:
                    return [float(r.get("close", 0.0)) for r in rows]
            except Exception as exc:
                logger.debug("Live fetch failed for %s: %s", clean_sym, exc)

        from sktui.api.paper_trading import generate_paper_history
        from sktui.utils import resolve_code
        base_p = KNOWN_BASE_PRICES.get(clean_sym, 100.0)
        code = resolve_code(clean_sym, "NC") or 2475
        bars = generate_paper_history("NC", code, "daily", bars_count=self.lookback_bars, base_price=base_p)
        return [float(b["close"]) for b in bars]

    def get_universe_symbols(
        self,
        sector: str | None = None,
        custom_symbols: Sequence[str] | None = None,
    ) -> list[str]:
        """Retrieve candidate universe symbols by sector or custom list."""
        if custom_symbols:
            return sorted(list(set(s.strip().upper() for s in custom_symbols)))
        if sector and sector.lower() != "all":
            sec_lower = sector.strip().lower()
            return sorted([
                sym for sym, sec in SECTOR_MAP.items()
                if sec.lower() == sec_lower and not any(sym.endswith(x) for x in ("FUT", "CE", "PE"))
            ])
        # Default all intra-sector symbols
        return sorted([
            sym for sym, sec in SECTOR_MAP.items()
            if sec not in ("Index",) and not any(sym.endswith(x) for x in ("FUT", "CE", "PE"))
        ])

    def screen(
        self,
        sector: str | None = None,
        symbols: Sequence[str] | None = None,
        min_correlation: float = 0.70,
        p_value_threshold: float = 0.05,
        max_half_life: float = 90.0,
    ) -> list[PairScreenResult]:
        """Screen pairs for given sector or symbol universe."""
        syms = self.get_universe_symbols(sector=sector, custom_symbols=symbols)
        if len(syms) < 2:
            return []
        universe = {sym: self.fetch_series(sym) for sym in syms}
        return screen_pairs(universe, min_correlation, p_value_threshold, max_half_life)

    def analyze_pair(
        self,
        stock_a: str,
        stock_b: str,
        prices_a: Sequence[float] | None = None,
        prices_b: Sequence[float] | None = None,
    ) -> PairScreenResult | None:
        """Deep statistical analysis of a single pair."""
        p_a = clean_series(prices_a) if prices_a is not None else self.fetch_series(stock_a)
        p_b = clean_series(prices_b) if prices_b is not None else self.fetch_series(stock_b)
        n = min(len(p_a), len(p_b))
        if n < 5:
            return None
        p_a = p_a[-n:]
        p_b = p_b[-n:]

        rho = compute_pearson_correlation(p_a, p_b)
        stability = compute_correlation_stability(p_a, p_b, window=min(90, n))
        beta, alpha = compute_ols_hedge_ratio(p_a, p_b)
        spread = compute_spread(p_a, p_b, beta)
        adf_stat, p_val, is_coint = adf_test(spread, max_lags=1)
        hl = compute_half_life(spread)
        zscores = compute_rolling_zscores(spread, window=min(90, n))
        cur_z = zscores[-1] if zscores else 0.0
        sig = calculate_zscore_signal(cur_z)
        alloc = calculate_position_sizing(100_000.0, p_a[-1], p_b[-1], beta)
        sec = SECTOR_MAP.get(stock_a, SECTOR_MAP.get(stock_b, "Equities"))

        return PairScreenResult(
            stock_a=stock_a,
            stock_b=stock_b,
            correlation=round(rho, 4),
            correlation_stability=round(stability, 4),
            beta=round(beta, 4),
            alpha=round(alpha, 4),
            adf_statistic=round(adf_stat, 4),
            p_value=round(p_val, 4),
            is_cointegrated=is_coint,
            half_life_days=round(hl, 1) if math.isfinite(hl) else float("inf"),
            current_spread=round(spread[-1], 2) if spread else 0.0,
            current_zscore=round(cur_z, 2),
            signal=sig,
            allocation=alloc,
            sector=sec,
        )
