# ⚡ SKTUI — Professional Terminal Trading Workstation & Algorithmic Engine

> **A fast, keyboard-first terminal trading workstation and institutional algorithmic engine built for active Indian equity and derivative traders (NSE · BSE · NFO · MCX).**  
> *Real-time tick monitoring · institutional pre-trade risk guardrails · pure-Python quantitative analytics · statistical arbitrage pair screening · multi-indicator signal consensus · dual-mode backtesting · autonomous bot fleet orchestration — without ever leaving the terminal.*

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](#installation)
[![Version: 0.4.0](https://img.shields.io/badge/version-0.4.0-informational.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Framework: Textual](https://img.shields.io/badge/TUI-Textual%201.0+-00e5ff.svg)](https://textual.textualize.io/)
[![Pure Python Math](https://img.shields.io/badge/Math-Pure--Python%20(Zero--Dep)-brightgreen.svg)](#pure-python-mathematical-foundation--architecture)
[![Tests: 454 Passed](https://img.shields.io/badge/tests-454%20passed-10b981.svg)](#testing--reliability)
[![Market: NSE / BSE / NFO](https://img.shields.io/badge/Exchange-NSE%20%7C%20BSE%20%7C%20NFO-10b981.svg)](#supported-exchanges)

---

## 🎯 Why SKTUI?

Web dashboards and GUI trading portals are cluttered with status spam, decorative charts, and mouse-dependent click flows. Under volatile market stress, every second spent reaching for a mouse costs edge.

**SKTUI** bridges the gap between high-frequency quantitative computing and human trader workflows. It delivers a unified architecture operating in two synergistic modes:

1. **Interactive TUI Workstation**: A high-density Textual terminal interface featuring 3-pane reactive layouts, live Level-2 market depth, candlestick charting with Braille overlays, and keyboard-driven order entry.
2. **Headless CLI Subsystem**: A POSIX-compliant, scriptable command-line interface allowing algorithmic traders to run technical analysis, sector pair screening, signal scanning, strategy backtesting, bot orchestration, and broker verification directly inside automated shell scripts and CI/CD pipelines.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│  ⚠ PAPER   ● LIVE 18ms  ·  TRADER_01  ·  CID: 987654  ·  IP: 103.21.54.12  ·  NC BC NF  · Risk: NORMAL
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  ◉ OPEN 09:15-15:30  NIFTY 25,142.30 (+0.42%)  ·  BANKNIFTY 52,180.10 (-0.15%)  ·  A/D: 32/18   │
├──────────────────────┬───────────────────────────────────────────────────────────────────────────┤
│ ❖ MARKET RADAR       │  [OHLC CANDLE]  EMA(9/21)  RSI(14)  ·  TCS  [5m]                          │
│                      │   3,640.00 │          │                                                    │
│ ── Active Sessions ──│   3,620.00 │       ┌──┴──┐                                                │
│ NSE Equity    OPEN   │   3,600.00 │       │  █  │  • EMA9                                        │
│ NSE Futures   OPEN   │   3,580.00 │  • ───┼─────┼────── • EMA21                                  │
│                      │   3,560.00 │       └──┬──┘                                                │
│ ── Sector Breadth ── │   3,540.00 │          │                                                    │
│ IT          +1.8% ▲  │   ─────────┴──────────────────────────────────────────────────────        │
│ Banking     -0.4% ▼  │        Vol │ █  ▅  █  ▂  ▇  █  (Directional Bull/Bear Volume)             │
│ Auto        +0.9% ▲  │    RSI(14) │ ▲  ▲  ▲  ─  ▼  [62.4]                                        │
├──────────────────────┴───────────────────────────────────────────────────────────────────────────┤
│  / = command palette   F1 = help   K = Panic Flatten   f = Focus Mode   c = Chart   b/s = Buy/Sell   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🌐 Supported Exchanges & Asset Classes <a id="supported-exchanges"></a>

SKTUI natively normalizes market data feeds, scrip identification, tick sizes, and order routing across all major Indian exchange segments via the Mirae Asset Sharekhan API:

| Exchange Segment | Segment Code | Asset Classes & Instruments | Trading Hours (IST) | Settlement & Routing |
|---|:---:|---|:---:|---|
| **NSE Capital Market** | `NC` | Equities, ETFs, Sovereign Gold Bonds (SGB), REITs/InvITs | 09:15 – 15:30 | T+1 Rolling Settlement, Demat Delivery & Intraday MIS |
| **BSE Capital Market** | `BC` | Equities, Mutual Funds, SME Board Listings | 09:15 – 15:30 | T+1 Rolling Settlement, Demat Delivery & Intraday MIS |
| **NSE Futures & Options** | `NF` | Index Derivatives (NIFTY, BANKNIFTY) & Single-Stock F&O | 09:15 – 15:30 | Cash-settled Indices, Physical Delivery on Stock Expiry |
| **NSE Currency Derivatives** | `RN` | Currency Pairs (USDINR, EURINR, GBPINR, JPYINR) & Crosses | 09:00 – 17:00 | Cash-settled in INR on RBI reference rate |
| **MCX Commodity Market** | `MX` | Energy (Crude Oil, Natural Gas), Bullion (Gold, Silver), Metals | 09:00 – 23:30 / 23:55 | Daily MTM, Cash-settled & Tender Period Deliveries |

---

## 🛡️ Core Institutional Systems

### 1. Pre-Trade Risk Engine (`/risk`, `/whatif`)
A professional trading terminal is first and foremost a **control system designed to prevent catastrophic decisions**:
- **Hard Guardrails**: Per-order maximum quantity (`max_order_qty`), per-order maximum value (`max_order_value`), maximum symbol exposure (`max_position`), and total aggregate portfolio exposure (`max_portfolio_exposure`).
- **Daily Loss Drawdown Lockout**: Continuous real-time tracking of realized and mark-to-market daily drawdown. Order placement is immediately locked out when daily losses hit configured thresholds (`max_daily_loss`).
- **Rate-Limiter Protection**: Token-bucket algorithm enforcing a strict submission rate cap (30 orders/minute) to protect against accidental algorithmic runaway loops.
- **Mandatory Stop-Loss for Derivatives**: Pre-trade validation rejects unhedged or bracketless F&O orders before execution.
- **Pre-Trade Risk Audit & Simulation**: Order impacts can be simulated via `/whatif` without risking capital, while all validation decisions are timestamped and logged.

### 2. Interactive Analytical Candlestick Charting (`c`)
Charts are precision diagnostic tools, not decorative widgets:
- **True Terminal OHLC Candlesticks**: Rendered with unicode wicks, directional body fills (green/red), and volume-scaled sub-histograms.
- **Real-Time Analytical Indicators**: Dual Exponential Moving Averages (`EMA 9` / `EMA 21`), Volume Weighted Average Price (`VWAP`), and Relative Strength Index (`RSI 14`) momentum sub-panels.
- **Interactive Hotkey Toggles**:
  - `k`: Toggle between **OHLC Candlestick** and high-density **Braille Line** rendering.
  - `e`: Toggle **EMA(9/21)** trend overlays.
  - `i`: Toggle **RSI(14)** momentum oscillator sub-panel.
  - `v`: Toggle directional **Volume** histogram strip.
  - Instant timeframe switching: `1m`, `3m`, `5m`, `10m`, `15m`, `30m`, `1h`, `1D`, `1W`, `1M`.

### 3. Deterministic Order Lifecycle & Emergency Panic Flatten (`Shift+K` / `K`)
- **Typed Lifecycle State Machine**: State progression enforced via strict transitions: `NEW` → `PENDING_SUBMIT` → `OPEN` → `TRIGGER_PENDING` → `PARTIALLY_FILLED` → `FILLED` / `CANCELLED` / `REJECTED`.
- **Structured RMS Reason Codes**: Categorizes rejections (`RMS_INSUFFICIENT_MARGIN`, `RMS_CIRCUIT_LIMIT`, `RMS_MAX_QTY_EXCEEDED`, `RMS_DRAWDOWN_LOCKOUT`, `RMS_DERIVATIVE_NO_SL`, `MARKET_CLOSED`).
- **Emergency Panic Flatten (`K` or `/flatten`)**: Instant single-key confirmation cancels all pending orders and fires market orders to square off all open intraday positions.
- **Tamper-Evident Audit Trail**: Every submission, rejection, fill, and cancel is written with sub-millisecond timestamps to `~/.local/share/sktui/audit.jsonl`.

### 4. Feed Telemetry & Staleness Badging
- **High-Visibility Connection Badge**: Real-time header telemetry displays link health:
  - `● LIVE 18ms` (Vibrant emerald `#00ff87`)
  - `▲ STALE 3.2s` (Amber `#f59e0b` when tick age exceeds 2.5s)
  - `■ RECONNECTING` / `✕ OFFLINE` (Crimson `#ff4757`)
- **Watchlist Staleness Dimming**: Active symbols stream with `● SYMBOL`, while quiet or disconnected ticks dim to `▲ SYMBOL ~ PRICE`.

### 5. Persistent Alert Engine (`/alert`, `/alerts`)
- **Trader-Defined Triggers**:
  - Price: `/alert RELIANCE > 3000` or `/alert INFY < 1400`
  - Technical: `/alert TCS RSI > 70` or `/alert TCS RSI < 30`
  - Volume: `/alert ONGC VOL > 2.5`
- **JSON Persistence**: Saved securely to `~/.config/sktui/alerts.json` (`0o600` permissions) across workstation restarts.
- **Live Notifications**: Fires instant toast alerts and records breach events in the audit log.

### 6. Portfolio Analytics & CSV Export (`/analytics`, `/export`)
- Realized vs. Unrealized P&L decomposition, win/loss ratio, and profit factor.
- Symbol concentration and sector attribution heatmap.
- `/export` dumps complete session analytics, position records, and order audits to `~/.local/share/sktui/session_YYYYMMDD_HHMMSS.csv`.

---

## 📐 Pure-Python Mathematical Foundation & Architecture <a id="pure-python-mathematical-foundation--architecture"></a>

SKTUI is engineered for **absolute runtime portability, deterministic execution, and zero binary lock-in**. In institutional trading environments, proprietary server farms, and restricted runtime containers (including modern **Python 3.14+** platforms where C-extension binary wheels like `numpy`, `scipy`, or `statsmodels` may be unavailable or prohibited), SKTUI executes **100% pure-Python implementations** of all advanced quantitative mathematics, statistical tests, and simulation algorithms.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            SKTUI WORKSTATION CORE                           │
├──────────────────────────────────────┬──────────────────────────────────────┤
│    INTERACTIVE TUI WORKSTATION       │        HEADLESS CLI ENGINE           │
│  • Textual 3-Pane Reactive Layout    │  • 8 Subparsers (analyze, backtest)  │
│  • 21+ Diagnostic & Analysis Modals  │  • Machine-Readable JSON Export      │
│  • Real-Time Braille Curve Graphics  │  • Automated Batch Pipelines         │
├──────────────────────────────────────┴──────────────────────────────────────┤
│               PURE-PYTHON ALGORITHMIC & ANALYTICAL SERVICES                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Quant Risk Engine: Sharpe, Sortino, Historical/Parametric VaR/CVaR, Beta │
│  • Statistical Arbitrage: OLS Hedge Ratio, Pure-Python ADF Test, Half-Life  │
│  • Composite Signal Engine: 7-Indicator Weighted Voting, ATR Risk R:R = 2.0 │
│  • Backtest Engine: Vectorized & Event-Driven, Bias Prevention, 8 Strats   │
│  • Autonomous Bot Orchestrator: PMM Inventory Skew, Arbitrage, Panic Kill   │
│  • Broker Sandbox Verifier: AES-GCM 256 Crypto, Paper REST/WebSocket Parity │
├─────────────────────────────────────────────────────────────────────────────┤
│                     ZERO-DEPENDENCY RUNTIME ENVIRONMENT                     │
│               Python Standard Library: math · statistics · dataclasses       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Mathematical Algorithms Implemented in Pure Python:

#### 1. Augmented Dickey-Fuller (ADF) Unit-Root Cointegration Test
- Formulates the Dickey-Fuller autoregression on the spread residuals:
  $$\Delta S_t = \alpha + \beta t + \gamma S_{t-1} + \sum_{i=1}^p \delta_i \Delta S_{t-i} + \epsilon_t$$
- Solves the linear system $(X^T X) \beta = X^T Y$ using **Gaussian elimination with partial row pivoting** and Gauss-Jordan matrix inversion, ensuring numerical stability without NumPy.
- Evaluates statistical significance via **MacKinnon (1994) response-surface polynomial approximations** to compute exact finite-sample p-values for testing the null hypothesis of a unit root ($p < 0.05$ confirms cointegration).

#### 2. Ornstein-Uhlenbeck Mean-Reversion Half-Life
- Models the spread as a continuous-time Ornstein-Uhlenbeck stochastic differential equation:
  $$dS_t = \lambda (\mu - S_t) dt + \sigma dW_t$$
- Discretizes the process via an AR(1) first-order autoregressive regression:
  $$\Delta S_t = S_t - S_{t-1} = \alpha + \beta S_{t-1} + \epsilon_t$$
- Extracts the mean-reversion speed $\lambda = -\ln(1 + \beta)$ and calculates the exact trading-day half-life:
  $$t_{1/2} = \frac{\ln(2)}{\lambda}$$

#### 3. Parametric & Historical Value-at-Risk (VaR & CVaR / Expected Shortfall)
- **Historical VaR**: Evaluates the non-parametric empirical quantile of return distributions via linear interpolation between order statistics at 95% and 99% confidence levels.
- **Parametric VaR**: Evaluates analytical tail losses under Gaussian assumptions:
  $$\text{VaR}_\alpha = -(\mu - Z_\alpha \cdot \sigma)$$
- **Conditional Value-at-Risk (CVaR / Expected Shortfall)**: Measures the expected loss conditional on the loss exceeding the VaR threshold:
  $$\text{CVaR}_{0.95} = -\mathbb{E}[R \mid R \le q_{0.05}]$$

#### 4. Point-in-Time Data Guard & Bias Prevention
- **1-Bar Execution Lag**: Signals generated at Bar $t$ Close execute strictly at Bar $t+1$ Open.
- Completely prevents look-ahead bias, predictive data leakage, and survivorship distortions across backtesting and real-time execution engines.

---

## 🤖 8 Algorithmic Trading Skills & Services

SKTUI integrates eight institutional trading disciplines and quantitative engineering engines directly into the application core. Each service is fully accessible via both **headless CLI commands** and **interactive TUI modal screens**:

---

### 1. Quantitative Risk & Performance Engine (`quant_analyst.py`)
Computes comprehensive quantitative performance, volatility, and benchmark regression metrics for any security or portfolio.
- **Risk & Return Metrics**: Annualized return (252-day basis), annualized volatility ($\sigma \sqrt{252}$), Sharpe ratio (risk-free benchmark $R_f = 5.0\%$), Sortino ratio (downside semivariance penalizing only negative volatility), Calmar ratio, maximum drawdown, and underwater duration.
- **Tail Risk Analytics**: 1-day Parametric VaR (95%, 99%), Historical VaR (95%, 99%), and Conditional VaR (CVaR 95% Expected Shortfall).
- **Benchmark Regression**: Regresses asset returns against the benchmark index (Nifty 50) to compute systematic Beta ($\beta$), Jensen's Alpha ($\alpha$), and the Coefficient of Determination ($R^2$).

```bash
# Headless quantitative analysis
sktui analyze RELIANCE --period 1y

# Cross-sectional ranking by Sharpe ratio
sktui compare RELIANCE TCS INFY HDFCBANK --rank-by sharpe
```

---

### 2. Multi-Indicator Stock Analyzer (`stock_analyzer.py`)
Synthesizes multiple technical indicators into a unified market assessment with directional scoring, trend classification, and multi-stock ranking.
- **Indicator Synthesis**: Consolidates RSI (14), MACD (12, 26, 9), Bollinger Bands (20, 2 with bandwidth), Stochastic %K/%D (14, 3), Average Directional Index (ADX 14 with +DI/-DI Wilder smoothing), SMA (20), SMA (50), EMA (21), and moving average slopes.
- **Directional Classification**: Produces unified ratings (`STRONG_BUY`, `BUY`, `NEUTRAL`, `SELL`, `STRONG_SELL`) with confidence scoring and detailed technical rationale.
- **Multi-Factor Ranking**: Ranks candidate stocks across user-selected factors (`sharpe`, `return`, `volatility`, `momentum`, `sortino`, `drawdown`).

```bash
# Analyze stock with comparison group
sktui analyze TCS --period 1y --compare INFY,WIPRO,HCLTECH

# Cross-stock ranking by price momentum
sktui compare TATAMOTORS MARUTI M&M BAJAJ-AUTO --rank-by momentum
```

---

### 3. Statistical Arbitrage & Cointegration Pair Screener (`pair_screener.py`)
Identifies mean-reverting equity pairs within sectors, evaluates cointegration integrity, calculates dynamic hedge ratios, and determines market-neutral position allocations.
- **Sector Universe Filtering**: Scans candidate pairs across predefined sector maps (`Banking`, `IT`, `Auto`, `Energy`, `Pharma`, `FMCG`, `Metals`).
- **Statistical Criteria**: Pearson correlation ($\rho \ge 0.70$), 90-day correlation stability ($|\rho_{full} - \rho_{90d}| \le 0.15$), Ordinary Least Squares (OLS) regression hedge ratio ($\beta$), pure-Python Augmented Dickey-Fuller test ($p < 0.05$), and Ornstein-Uhlenbeck half-life ($0.1 \le t_{1/2} \le 90$ days).
- **Z-Score Execution Triggers**:
  - $Z \le -2.0 \implies$ `LONG_PAIR` (Buy Stock A, Short $\beta \times$ Stock B)
  - $Z \ge +2.0 \implies$ `SHORT_PAIR` (Short Stock A, Buy $\beta \times$ Stock B)
  - $|Z| \le 0.5 \implies$ `EXIT` (Mean reversion target reached)
  - $|Z| \ge 3.0 \implies$ `STOP_LOSS` (Divergence protection)
- **Market-Neutral Sizing**: Calculates exact dollar and share allocations for both legs based on available capital and scrip prices.

```bash
# Screen sector for cointegrated pairs
sktui pairs --sector Banking --min-corr 0.75

# Analyze spread between two specific stocks with position sizing
sktui spread --stock-a ICICIBANK --stock-b HDFCBANK --lookback 90 --capital 200000
```

---

### 4. Multi-Indicator Composite Signal Engine (`signal_engine.py`)
Evaluates an ensemble of 7 independent technical indicators to generate directional consensus signals with calibrated confidence levels and dynamic risk brackets.
- **7-Indicator Ensemble Voting**:
  1. *RSI (14)*: Oversold bounce vs. overbought exhaustion vs. momentum continuation.
  2. *MACD (12, 26, 9)*: Signal line crossovers and histogram expansion.
  3. *Bollinger Bands (20, 2)*: %B band penetration and volatility envelopes.
  4. *SMA Trend Alignment*: Price $> SMA_{20} > SMA_{50} > SMA_{200}$ hierarchical trend checks.
  5. *Volume Surge Confirmation*: $1.5\times$ volume spike relative to 20-bar moving average.
  6. *Stochastic Oscillator (14, 3)*: %K and %D momentum boundaries.
  7. *ADX (14) with +DI/-DI*: Trend strength filter (ADX $> 25$) with directional bias.
- **Scoring & Classification**: Normalized composite score $[-2.0, +2.0]$ categorized into 5 tiers:
  - `STRONG_BUY` ($\text{Score} \ge +1.2$)
  - `BUY` ($+0.4 \le \text{Score} < +1.2$)
  - `NEUTRAL` ($-0.4 < \text{Score} < +0.4$)
  - `SELL` ($-1.2 < \text{Score} \le -0.4$)
  - `STRONG_SELL` ($\text{Score} \le -1.2$)
- **Dynamic ATR Risk Brackets**: Automatically calculates Average True Range (ATR) based Stop Loss ($1.5 \times ATR$) and Take Profit ($3.0 \times ATR$), maintaining an institutional **2.0 Risk-to-Reward ratio**.

```bash
# Scan default high-liquidity watchlist
sktui signals

# Scan specific symbols with BUY filter and 70% confidence cutoff
sktui signals --symbols RELIANCE,TCS,INFY,HDFCBANK,TATAMOTORS --filter BUY --min-conf 70.0
```

---

### 5. Dual-Mode Backtesting & Strategy Optimization (`backtesting.py`)
Simulates trading strategies across historical time horizons with realistic execution mechanics and friction modeling.
- **Dual Execution Engines**:
  - *Vectorized Engine*: High-speed array simulation optimized for multi-parameter grid search and walk-forward validation.
  - *Event-Driven Engine*: Realistic bar-by-bar and tick replay stepping honoring intra-bar sequence order.
- **Look-Ahead & Survivorship Bias Guards**: Strict point-in-time enforcement ensuring signals computed at Bar $t$ Close execute strictly at Bar $t+1$ Open.
- **Friction & Transaction Costs**: Percentage broker commissions (default 0.03%), price slippage (default 0.02%), and fixed ticket fees.
- **Catalog of 8 Standard Strategies**:
  1. `sma`: Simple Moving Average crossover (`fast_period`, `slow_period`)
  2. `ema`: Exponential Moving Average crossover (`fast_period`, `slow_period`)
  3. `rsi`: RSI mean-reversion extreme reversal (`period`, `oversold`, `overbought`)
  4. `macd`: MACD signal line crossover (`fast`, `slow`, `signal`)
  5. `bollinger`: Bollinger Bands mean-reversion (`period`, `std_dev`, `exit_at_middle`)
  6. `breakout`: Donchian N-bar channel breakout (`lookback`)
  7. `mean_reversion`: Z-Score moving average mean-reversion (`window`, `entry_z`, `exit_z`)
  8. `momentum`: Time-series Rate of Change (ROC) price momentum (`roc_period`, `threshold`)
- **Optimization & Validation**: Multi-parameter Cartesian grid search optimizer (`--optimize`) and rolling out-of-sample walk-forward validation (`--walk-forward`).

```bash
# Run baseline SMA crossover backtest
sktui backtest --strategy sma --symbol RELIANCE --capital 100000 --period 1y

# Run parameter grid search optimization
sktui backtest --strategy rsi --symbol TCS --optimize

# Run rolling walk-forward validation
sktui backtest --strategy bollinger --symbol HDFCBANK --walk-forward
```

---

### 6. Autonomous Trading Bot Orchestrator & Fleet Engine (`bot_engine.py`)
A deterministic execution engine and multi-bot fleet manager built for autonomous strategy operation with strict risk governance.
- **Deterministic 6-State Lifecycle Machine**:
  $$\text{INIT} \longrightarrow \text{CONFIGURED} \longrightarrow \text{RUNNING} \underset{\text{resume}}{\overset{\text{pause}}{\rightleftharpoons}} \text{PAUSED} \longrightarrow \text{STOPPED} \text{ / } \text{ERROR}$$
- **4 Strategy Archetypes**:
  - *Pure Market Making (PMM)*: Continuous dual-sided quoting with Avellaneda-Stoikov inventory reservation price skewing ($r(s, q) = s - q \gamma \sigma^2$).
  - *Pair Statistical Arbitrage*: Synchronized dual-leg order placement on spread Z-score breach.
  - *Trend Following Momentum*: Automatic execution on moving average breakouts.
  - *Predictor-Driven Temporal*: Machine learning signal execution with risk covariance controls.
- **Pre-Trade Risk & Safety Controls**: Maximum order value caps, quantity bounds, and order rate limiting.
- **Daily Drawdown Circuit Breaker**: Auto-trips and halts the bot when cumulative daily losses breach configured limits (`daily_loss_limit`).
- **Emergency Panic Controls**: Instant `CANCEL_ALL` and `FLATTEN_ALL` killswitch actions.
- **`BotManager` Fleet Registry**: Centralized singleton managing multi-bot deployment, telemetry aggregation, and lifecycle states.

```bash
# Launch Pure Market Making bot in paper sandbox
sktui bot --strategy pmm --symbol RELIANCE --action start --paper --capital 100000

# Query real-time status and telemetry
sktui bot --strategy pmm --symbol RELIANCE --action status --paper

# Emergency panic killswitch: cancel all open orders
sktui bot --strategy pmm --symbol RELIANCE --action panic --paper
```

---

### 7. Broker Sandbox & Authentication Verifier (`broker_verifier.py`)
Automated diagnostic verification suite that validates broker REST and WebSocket endpoints, authentication flows, and paper trading sandbox simulation integrity.
- **Cryptographic Security Audit**:
  - AES-GCM 256 authenticated encryption/decryption roundtrip validation.
  - 32-byte secret key length enforcement.
  - Sharekhan request token halves swapping verification (`swap_request_token`).
  - Corrupted authentication tag detection and rejection (`InvalidTag`).
- **High-Fidelity Paper Trading Sandbox**:
  - In-memory simulation parity with live broker APIs: order placement, modification, cancellation, and execution.
  - Position tracking, MTM calculations, cash clamping, and synthetic 5-level DOM order book synthesis.
- **Endpoint Diagnostics**: Live latency profiling across funds, holdings, positions, orders, and market quotes.

```bash
# Run full verification suite against paper sandbox (all 18 diagnostic checks)
sktui verify --sandbox

# Verify AES-GCM 256 cryptographic security only
sktui verify --auth

# Run live endpoint probes (requires configured credentials)
sktui verify --live --verbose
```

---

### 8. Pure-Python Technical Indicator Library (`indicators.py`)
High-performance mathematical indicator calculation engine operating without external numerical dependencies:
- **Stochastic Oscillator**: Computes %K and %D over arbitrary lookback windows with zero-range boundary protection.
- **Average Directional Index (ADX)**: Full 14-period True Range (TR), directional movement (+DM, -DM), and Wilder exponential smoothing.
- **Trend & Regression Indicators**: Moving average slope, directional trend strength, and linear regression trend slope.

---

## 💻 Headless CLI Workstation Subsystem

In addition to the interactive Textual TUI workstation, **SKTUI** includes an institutional-grade, scriptable headless CLI subsystem. It allows quantitative traders, risk officers, and automated pipelines to perform technical analysis, multi-stock ranking, pair trading screening, multi-indicator signal scanning, strategy backtesting, bot orchestration, and broker sandbox verification directly from terminal scripts, cron jobs, and CI/CD pipelines.

```bash
# Launch interactive TUI workstation (default)
sktui

# Or execute any headless CLI subcommand:
sktui <subcommand> [options]
```

### 📋 Subcommand Quick Reference

| Subcommand | Description | Primary Use Case | Output Formats |
|---|---|---|---|
| [`analyze`](#1-sktui-analyze) | Single-stock technical & quantitative analysis | Indicator calculation, Sharpe/Sortino/VaR metrics, trend sparkline | Rich Panel/Tables, Comparison |
| [`compare`](#2-sktui-compare) | Multi-stock ranking & quantitative comparison | Rank watchlist by Sharpe, return, volatility, momentum, or drawdown | Rich Ranking Table |
| [`pairs`](#3-sktui-pairs) | Cointegrated pair trading screener | Statistical arbitrage screening, ADF unit-root test, OU half-life | Rich Table, JSON, File export |
| [`spread`](#4-sktui-spread) | Two-stock spread & Z-score analysis | OLS hedge ratio ($\beta$), rolling Z-score, market-neutral sizing | Rich Panel & Sizing Table, JSON |
| [`signals`](#5-sktui-signals) | Multi-indicator composite signal scanner | 7-indicator voting engine (`RSI`, `MACD`, `BB`, `SMA`, `VOL`, `STOCH`, `ADX`) | Rich Table, JSON, File export |
| [`backtest`](#6-sktui-backtest) | Dual-mode strategy simulation & optimization | Bias-free backtesting, parameter grid search, walk-forward validation | Rich Panel/Tables, JSON, File export |
| [`bot`](#7-sktui-bot) | Automated trading bot orchestration | Launch, control, pause, resume, and panic-stop bot instances | Plaintext header, Rich Telemetry, JSON |
| [`verify`](#8-sktui-verify) | Broker sandbox & endpoint verification | AES-GCM 256 crypto tests, paper sandbox diagnostics, endpoint latency | Rich Diagnostic Matrix, JSON |

---

### 🌐 Global / Workstation Options

When launching SKTUI without a subcommand, or passing global flags:

| Flag | Argument | Default | Description |
|---|---|---|---|
| `-h`, `--help` | — | — | Display SKTUI help manual and exit |
| `--paper` | — | `False` | Dry-run: simulate orders in paper sandbox mode without risking real capital |
| `--profile` | `PROFILE` | `default` | Configuration profile to load from `~/.config/sktui/config.json` (e.g. `default`, `live`, `paper`) |
| `--theme` | `THEME` | `sktui-obsidian` | UI color theme (`sktui-obsidian`, `sktui-bloomberg`, `sktui-daylight`, `nord`, etc.) |
| `--debug` | — | `False` | Enable verbose diagnostic debug logging and Textual devtools inspection |
| `--log-level`| `LEVEL` | `INFO` | Logging level override (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `--symbol` | `SYMBOL` | `None` | Initial active stock ticker symbol to focus upon workstation mount |

---

### 1. `sktui analyze` <a id="1-sktui-analyze"></a>

Calculates pure-Python technical indicators, quantitative performance metrics (Sharpe, Sortino, VaR, CVaR, Beta, Alpha), and composite signal score for any equity symbol.

```bash
sktui analyze <symbol> [options]
```

#### Options & Flags

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `symbol` | — | `str` | *(Required)* | Stock ticker symbol (e.g. `RELIANCE`, `TCS`, `INFY`) |
| `--period` | `-p` | `str` | `1y` | Historical lookback period (`1m`, `3m`, `6m`, `1y`, `2y`, `5y`) |
| `--indicators` | `-i` | `str` | `None` | Comma-separated indicators to compute |
| `--compare` | — | `str` | `None` | Comma-separated symbols to compare against (appends ranking table) |

#### Copy-Pasteable Usage Examples

```bash
# Analyze single stock with 1-year historical lookback
sktui analyze RELIANCE

# Analyze stock with 6-month lookback
sktui analyze TCS --period 6m

# Analyze stock and append multi-stock comparison ranking table
sktui analyze INFY --compare TCS,WIPRO,HCLTECH
```

#### Terminal Output Overview
- **Header Panel**: LTP, net price change, change percentage, signal chip (`[BUY]`, `[SELL]`, `[NEUTRAL]`), confidence score %, Unicode trend sparkline, and signal rationale.
- **Technical Indicators Table**: RSI (14), MACD (12, 26, 9), Stochastic Oscillator (%K, %D), ADX (14 with +DI/-DI), Bollinger Bands (20, 2 with Bandwidth), SMA 20/50 Trend Alignment.
- **Quantitative Risk & Analytics Table**: Annualized Return, Annualized Volatility, Sharpe Ratio (Rf=5.0%), Sortino Ratio, Maximum Drawdown (and bars underwater), Value-at-Risk (VaR 95% and 99% 1-day), Conditional VaR (CVaR 95% Expected Shortfall), Benchmark Beta (vs Nifty 50), Jensen's Alpha, and R-Squared ($R^2$).

---

### 2. `sktui compare` <a id="2-sktui-compare"></a>

Compares multiple stocks side-by-side and ranks them by quantitative or technical metrics.

```bash
sktui compare <symbols...> [options]
```

#### Options & Flags

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `symbols` | — | `str+` | *(Required)* | Space- or comma-separated stock ticker symbols to compare |
| `--rank-by` | `-r` | `choice` | `sharpe` | Ranking metric: `sharpe`, `return`, `volatility`, `momentum`, `sortino`, `drawdown` |
| `--period` | `-p` | `str` | `1y` | Historical lookback period (`1m`, `3m`, `6m`, `1y`, `2y`) |

#### Copy-Pasteable Usage Examples

```bash
# Rank banking peers by Sharpe ratio
sktui compare HDFCBANK ICICIBANK SBIN KOTAKBANK AXISBANK --rank-by sharpe

# Rank IT stocks by annualized return over 6 months
sktui compare TCS INFY WIPRO HCLTECH TECHM --rank-by return --period 6m

# Rank defensive stocks by lowest maximum drawdown
sktui compare ITC HINDUNILVR NESTLEIND BRITANNIA --rank-by drawdown
```

---

### 3. `sktui pairs` <a id="3-sktui-pairs"></a>

Scans universe candidates to identify cointegrated pairs for statistical arbitrage using pure-Python Pearson correlation, OLS hedge ratios, Augmented Dickey-Fuller (ADF) unit-root testing with MacKinnon p-value lookup, and Ornstein-Uhlenbeck (OU) mean-reversion half-life estimation.

```bash
sktui pairs [options]
```

#### Options & Flags

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `--sector` | `-s` | `str` | `None` | Sector filter (`Banking`, `IT`, `Auto`, `Energy`, `Pharma`, `FMCG`, `Metals`) |
| `--min-corr`| `-c` | `float`| `0.70` | Minimum Pearson correlation coefficient ($0.0 \le \rho \le 1.0$) |
| `--symbols` | — | `str+` | `None` | Custom symbol universe to restrict screening candidates |
| `--output` | `-o` | `str` | `None` | Output file path to save screening results (`.json` or `.txt`) |
| `--json` | — | `bool` | `False` | Output pure JSON to stdout for shell piping and automated parsing |

#### Copy-Pasteable Usage Examples

```bash
# Screen cointegrated pairs in the Banking sector with minimum 0.75 correlation
sktui pairs --sector Banking --min-corr 0.75

# Screen custom candidate list and save formatted results to text file
sktui pairs --symbols RELIANCE ONGC BPCL IOC --min-corr 0.65 --output energy_pairs.txt

# Export cointegrated pairs as scriptable JSON to stdout and filter with jq
sktui pairs --sector IT --min-corr 0.70 --json | jq '.[] | select(.is_cointegrated == true)'
```

---

### 4. `sktui spread` <a id="4-sktui-spread"></a>

Performs deep cointegration, Ornstein-Uhlenbeck mean-reversion, and rolling Z-score spread analysis between two stocks, calculating market-neutral position sizing based on the OLS hedge ratio ($\beta$).

```bash
sktui spread --stock-a <STOCK_A> --stock-b <STOCK_B> [options]
```

#### Options & Flags

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `--stock-a` | `-a` | `str` | *(Required)* | First stock ticker symbol (Stock A / Dependent Variable $Y$) |
| `--stock-b` | `-b` | `str` | *(Required)* | Second stock ticker symbol (Stock B / Independent Variable $X$) |
| `--lookback`| `-l` | `int` | `90` | Historical lookback window in trading days |
| `--capital` | — | `float`| `100000.0` | Portfolio capital allocation in INR (₹) for position sizing |
| `--output` | `-o` | `str` | `None` | Output file path to save analysis results (`.json`) |
| `--json` | — | `bool` | `False` | Output pure JSON payload to stdout |

#### Copy-Pasteable Usage Examples

```bash
# Analyze spread and capital sizing for private bank pair (₹100,000 capital)
sktui spread --stock-a HDFCBANK --stock-b ICICIBANK

# Analyze spread over 120-day lookback with ₹500,000 capital allocation
sktui spread -a ICICIBANK -b KOTAKBANK --lookback 120 --capital 500000

# Export spread telemetry and allocation sizing to JSON file
sktui spread -a TCS -b INFY --capital 250000 --output tcs_infy_spread.json
```

---

### 5. `sktui signals` <a id="5-sktui-signals"></a>

Scans symbols against a 7-indicator multi-voting engine (`RSI`, `MACD`, `Bollinger Bands`, `SMA Trend`, `Volume`, `Stochastic Oscillator`, `ADX`) to produce 5-tier composite trading signals with confidence levels and ATR-based dynamic risk levels.

```bash
sktui signals [options]
```

#### Options & Flags

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `--symbols` | `-s` | `str+` | `None` | Stock symbols to scan (comma or space separated; defaults to large-cap core) |
| `--watchlist`| `-w` | `str` | `None` | Watchlist identifier or sector name (`banking`, `it`, `auto`, etc.) |
| `--filter` | `-f` | `choice`| `ALL` | Filter by signal type: `ALL`, `BUY`, `SELL`, `STRONG_BUY`, `STRONG_SELL` |
| `--min-conf`, `--min-confidence` | — | `float` | `60.0` | Minimum confidence score percentage ($0.0 \text{ to } 100.0\%$) |
| `--output` | `-o` | `str` | `None` | Output file path to save scanned signals (`.json` or text) |
| `--json` | — | `bool` | `False` | Output pure JSON list to stdout |

#### Copy-Pasteable Usage Examples

```bash
# Scan default high-liquidity universe for any signal with confidence >= 60%
sktui signals

# Scan specific symbols for BUY or STRONG_BUY opportunities
sktui signals --symbols RELIANCE,TCS,INFY,TATAMOTORS,SBIN --filter BUY --min-conf 65

# Scan banking watchlist and export structured JSON
sktui signals --watchlist banking --filter ALL --json | jq '.[] | {symbol, signal_type, confidence_pct, score}'
```

---

### 6. `sktui backtest` <a id="6-sktui-backtest"></a>

Simulates trading strategies against historical data using either high-speed vectorized computation or tick/bar event-driven replay. Strictly enforces **point-in-time execution data guards** (signals generated at Bar $t$ Close execute at Bar $t+1$ Open) to eliminate look-ahead and survivorship biases, and incorporates realistic percentage commissions and slippage.

```bash
sktui backtest --strategy <STRATEGY> --symbol <SYMBOL> [options]
```

#### Supported Strategy Identifiers (`--strategy`)
- `sma`: Simple Moving Average crossover (`fast_period`, `slow_period`)
- `ema`: Exponential Moving Average crossover (`fast_period`, `slow_period`)
- `rsi`: Relative Strength Index mean-reversion (`period`, `oversold`, `overbought`)
- `macd`: MACD signal line crossover (`fast_period`, `slow_period`, `signal_period`)
- `bollinger`: Bollinger Bands mean-reversion (`period`, `num_std`)
- `breakout`: Donchian channel breakout strategy (`lookback`)
- `mean_reversion`: Statistical spread mean-reversion with Z-score bands (`lookback`, `entry_z`, `exit_z`)
- `momentum`: Directional rate-of-change momentum strategy (`lookback`, `threshold`)

#### Options & Flags

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `--strategy` | `-s` | `str` | *(Required)* | Strategy identifier (`sma`, `ema`, `rsi`, `macd`, `bollinger`, `breakout`, `mean_reversion`, `momentum`) |
| `--symbol` | — | `str` | *(Required)* | Stock ticker symbol to backtest against (e.g. `RELIANCE`) |
| `--capital` | `-c` | `float`| `100000.0` | Initial simulation capital in INR (₹) |
| `--period` | `-p` | `str` | `1y` | Historical backtest lookback period (`1m`, `3m`, `6m`, `1y`, `2y`) |
| `--commission` | — | `float` | `0.0003` | Percentage broker commission per trade ($0.0003 = 0.03\%$) |
| `--slippage` | — | `float` | `0.0002` | Expected slippage rate per trade ($0.0002 = 0.02\%$) |
| `--mode` | `-m` | `choice`| `vectorized` | Backtesting simulation engine: `vectorized` or `event_driven` |
| `--optimize` | — | `bool` | `False` | Run multi-parameter grid search optimization ranked by Sharpe ratio |
| `--walk-forward` | — | `bool` | `False` | Run 5-window rolling walk-forward out-of-sample validation |
| `--output` | `-o` | `str` | `None` | Output file path for simulation report (`.json` or text) |
| `--json` | — | `bool` | `False` | Output scriptable JSON format to stdout |

#### Copy-Pasteable Usage Examples

```bash
# Run baseline SMA crossover backtest on RELIANCE with ₹100,000 capital
sktui backtest --strategy sma --symbol RELIANCE --capital 100000

# Run event-driven backtest on TCS incorporating custom commission and slippage
sktui backtest --strategy rsi --symbol TCS --mode event_driven --commission 0.0005 --slippage 0.0003

# Run parameter grid search optimization to discover optimal RSI parameters
sktui backtest --strategy rsi --symbol INFY --optimize

# Run rolling-window walk-forward validation (70% train / 30% test across 5 windows)
sktui backtest --strategy sma --symbol RELIANCE --walk-forward

# Export full backtest result with trade execution logs to JSON
sktui backtest --strategy macd --symbol TATAMOTORS --json | jq '{total_return, cagr, sharpe_ratio, max_drawdown, total_trades, win_rate}'
```

---

### 7. `sktui bot` <a id="7-sktui-bot"></a>

Launches, orchestrates, monitors, and controls automated trading bots governed by a formal deterministic lifecycle state machine (`INIT` $\rightarrow$ `CONFIGURED` $\rightarrow$ `RUNNING` $\rightarrow$ `PAUSED` $\rightarrow$ `STOPPED` $\rightarrow$ `ERROR`). Equipped with real-time pre-trade risk validation, order rate limiting, daily drawdown lockouts, and emergency panic killswitches.

```bash
sktui bot --strategy <STRATEGY> --symbol <SYMBOL> [options]
```

#### Bot Lifecycle Actions (`--action`)
- `start`: Instantiate and start the strategy execution loop (`RUNNING`)
- `pause`: Temporarily suspend active order submission without cancelling open state (`PAUSED`)
- `resume`: Resume a paused bot instance back to (`RUNNING`)
- `stop`: Gracefully terminate the bot instance (`STOPPED`)
- `panic`: **EMERGENCY KILLSWITCH**: Instantly cancel all pending orders and set state to `STOPPED`
- `status`: Query live telemetry, order counts, filled quantities, and realized P&L

#### Options & Flags

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `--strategy` | `-s` | `str` | *(Required)* | Strategy name (`pmm`, `arbitrage`, `momentum`, `predictor`) |
| `--symbol` | — | `str` | *(Required)* | Trading symbol / scrip code (e.g. `RELIANCE` or pair `ICICIBANK/KOTAKBANK`) |
| `--action` | `-a` | `choice`| `start` | Bot lifecycle action (`start`, `stop`, `pause`, `resume`, `status`, `panic`) |
| `--paper` | — | `bool` | `False` | Run bot in paper sandbox mode (also activated via `SKTUI_PAPER=1`) |
| `--capital` | `-c` | `float`| `100000.0` | Capital allocation in INR (₹) assigned to this bot instance |
| `--config` | — | `str` | `None` | Path to JSON/YAML configuration file for custom strategy parameters |
| `--output` | `-o` | `str` | `None` | Output file path for bot telemetry (`.json` or text) |
| `--json` | — | `bool` | `False` | Output scriptable telemetry JSON format to stdout |

#### Copy-Pasteable Usage Examples

```bash
# Start Pure Market Making (PMM) bot on RELIANCE in Paper Sandbox mode
sktui bot --strategy pmm --symbol RELIANCE --action start --paper --capital 100000

# Query real-time status and telemetry of an active bot instance
sktui bot --strategy pmm --symbol RELIANCE --action status --paper

# Pause active order quoting during market volatility
sktui bot --strategy pmm --symbol RELIANCE --action pause --paper

# Resume order quoting
sktui bot --strategy pmm --symbol RELIANCE --action resume --paper

# Emergency Panic: Instantly cancel all open orders and halt bot
sktui bot --strategy pmm --symbol RELIANCE --action panic --paper

# Query bot telemetry in JSON format and check daily PnL
sktui bot --strategy momentum --symbol TCS --action status --paper --json | jq .telemetry.daily_pnl
```

---

### 8. `sktui verify` <a id="8-sktui-verify"></a>

Automated diagnostic verification suite that validates broker REST and WebSocket endpoints, authentication flows, and paper trading sandbox simulation integrity. Includes 6 cryptographic AES-GCM 256 checks, 7 paper sandbox execution checks, and live endpoint latency probes.

```bash
sktui verify [options]
```

#### Options & Flags

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `--sandbox` | — | `bool` | `True` | Run verification suite against local paper sandbox environment (default) |
| `--no-sandbox`| — | `bool` | `False` | Target live broker endpoints (requires configured API credentials in profile) |
| `--live` | — | `bool` | `False` | Run only live broker connectivity and endpoint probes |
| `--auth` | — | `bool` | `False` | Run only authentication and AES-GCM 256 crypto tests |
| `--paper` | — | `bool` | `False` | Run only paper trading sandbox simulation checks |
| `--endpoint` | — | `str` | `None` | Broker REST API endpoint URL override |
| `--output` | `-o` | `str` | `None` | Output file path to save verification report (`.json` or text) |
| `--json` | — | `bool` | `False` | Output scriptable JSON verification summary to stdout |
| `--verbose` | `-v` | `bool` | `False` | Display detailed diagnostic traces and payload metadata |

#### Verification Matrix Domains Covered
1. **`crypto` Domain**:
   - `crypto_aes_gcm_versioned_roundtrip`: Base64-URL versioned payload encryption/decryption roundtrip
   - `crypto_aes_gcm_raw_roundtrip`: Standard Base64 AES-GCM 256 roundtrip
   - `crypto_key_length_enforcement`: Validation that non-32-byte keys are rejected
   - `crypto_corrupted_tag_rejection`: Verification that tampered authentication tags raise `InvalidTag`
   - `crypto_request_token_swapping`: Request token halves swapping and formatting integrity
   - `crypto_benchmark_throughput`: High-performance throughput benchmark (> 100,000 ops/sec)
2. **`paper` Domain**:
   - `paper_order_placement`: Deterministic order generation and ID tracking
   - `paper_order_cancellation`: Order state transition to CANCELLED
   - `paper_position_tracking`: Net position quantities and unrealized MTM calculation
   - `paper_delivery_holdings`: Demat holdings retrieval
   - `paper_margin_cash_clamping`: Dynamic margin balance updates
   - `paper_market_depth_synthesis`: 5-level synthetic bid/ask order book generation
   - `paper_synthetic_ohlcv`: Synthetic intraday OHLCV bar generation
3. **`endpoints` Domain**:
   - Funds, Holdings, Positions, Orders, and Quotes API probe latency verification

#### Copy-Pasteable Usage Examples

```bash
# Run full verification suite against paper sandbox (all 18 checks)
sktui verify --sandbox

# Run only authentication and AES-GCM 256 cryptographic tests
sktui verify --auth

# Run only paper sandbox simulation checks with verbose diagnostic traces
sktui verify --paper --verbose

# Run verification in CI/CD and assert pass status via exit code and JSON
sktui verify --sandbox --json | jq .passed
```

---

### 🔄 Shell Scripting & Automated CI/CD Pipelines

All headless commands support `--json` and return deterministic POSIX exit codes (`0` for success, `1` for business rule rejection or verification failure, `2` for syntax/CLI errors). This makes SKTUI ideal for automated shell pipelines:

```bash
#!/usr/bin/env bash
# Example: Daily Morning Quantitative Screening Pipeline

echo "=== 1. Verifying Broker Sandbox Environment ==="
if ! sktui verify --sandbox --json | jq -e '.passed' > /dev/null; then
    echo "Verification failed! Halting pipeline."
    exit 1
fi

echo "=== 2. Screening Cointegrated Banking Pairs ==="
sktui pairs --sector Banking --min-corr 0.75 --output /tmp/banking_pairs.json

echo "=== 3. Scanning High-Confidence Trading Signals ==="
sktui signals --symbols RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK --filter BUY --min-conf 70 --output /tmp/morning_signals.json

echo "=== 4. Backtesting Strategy on Top Candidate ==="
sktui backtest --strategy sma --symbol RELIANCE --capital 200000 --json > /tmp/backtest_reliance.json
RETURN=$(jq '.total_return_pct' /tmp/backtest_reliance.json)
SHARPE=$(jq '.sharpe_ratio' /tmp/backtest_reliance.json)
echo "Backtest Complete: Return=${RETURN}%, Sharpe=${SHARPE}"
```

---

## 🚀 Installation & Deployment <a id="installation"></a><a id="installation--deployment"></a>

### Method 1: Automated Installer (Linux / macOS — Recommended)

The installer sets up an isolated virtual environment and creates an executable symlink in `~/.local/bin`:

```bash
# 1. Clone repository
git clone https://github.com/lamanstore/sktui.git
cd sktui

# 2. Run installer script (installs in editable mode)
chmod +x install.sh
./install.sh

# Or install with developer / test dependencies (pytest, ruff, mypy):
./install.sh --dev

# To cleanly uninstall anytime:
./install.sh --uninstall
```

> **Zero-Maintenance Updates**: The installer configures SKTUI in editable mode (`pip install -e .`). Whenever you update with `git pull`, all new features and patches take effect immediately without needing to re-install!

---

### Method 2: Modern Isolated CLI Installers (`pipx` / `uv`)

If you use `pipx` or `uv` to manage Python CLI workstations:

#### Using `pipx`:
```bash
# From local directory
pipx install .

# Or directly from GitHub
pipx install git+https://github.com/lamanstore/sktui.git
```

#### Using `uv`:
```bash
uv tool install .
```

---

### Method 3: Windows 10/11 PowerShell Installer

```powershell
# Clone and run installer
git clone https://github.com/lamanstore/sktui.git
cd sktui

# Standard installation
powershell -ExecutionPolicy Bypass -File .\install.ps1

# With developer / test dependencies
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Dev
```

---

### Method 4: Manual Virtual Environment

```bash
python3 -m venv ~/.local/share/sktui/venv
source ~/.local/share/sktui/venv/bin/activate
pip install -e ".[dev]"
sktui --paper
```

---

## ⚡ Running SKTUI & Profile Configuration

Launch directly from any terminal window:

```bash
# 1. Paper Trading Mode (Simulated fills & risk guardrails — zero real capital risk)
sktui --paper

# 2. Live Trading Mode (Direct execution against broker API)
sktui

# 3. Environment Profiles (Switch between live, paper, or custom environments)
sktui --profile live
sktui --profile paper

# 4. Custom Theme Selection (Obsidian, Bloomberg, Daylight, Nord, Cyberpunk)
sktui --theme sktui-bloomberg

# 5. Direct Symbol Focus
sktui --symbol RELIANCE

# 6. Diagnostic Debug Mode (Verbose logging to stdout and ~/.local/share/sktui/sktui.log)
sktui --debug
```

### Profile Configuration (`~/.config/sktui/config.json`)

SKTUI supports profile-based configurations stored in `~/.config/sktui/config.json`. You can maintain isolated risk rules and API credentials for paper testing versus live execution:

```json
{
  "active_profile": "default",
  "profiles": {
    "default": {
      "customer_id": "YOUR_CUSTOMER_ID",
      "api_key": "YOUR_API_KEY",
      "secret_key": "YOUR_SECRET_KEY",
      "paper_mode": false,
      "max_order_qty": 500,
      "max_order_value": 200000.0,
      "max_position": 1000,
      "max_portfolio_exposure": 1000000.0,
      "max_daily_loss": 25000.0,
      "require_sl_for_derivatives": true
    },
    "paper": {
      "customer_id": "PAPER_TRADER",
      "paper_mode": true,
      "max_order_qty": 1000,
      "max_order_value": 500000.0,
      "max_daily_loss": 50000.0
    }
  }
}
```

---

## ⌨️ Workstation Keyboard Map & Modal Screens

### 1. Navigation & Workspace Views
| Key | Action | Description |
|:---:|---|---|
| `1` | **Watchlist Tab** | Streaming market watch table with live bid/ask spreads |
| `2` | **Symbol Focus Tab** | Deep focus view: OHLC candle chart, sparklines, and detailed quote |
| `3` | **Orders Tab** | Active pending, filled, and cancelled order management table |
| `4` | **Positions Tab** | Open intraday/delivery positions with real-time MTM and booked P&L |
| `5` | **Holdings Tab** | Demat CNC equity holdings and investment portfolio |
| `6` | **Funds Tab** | Margin limits, cash balance, collateral, and utilization breakdown |
| `7` | **Activity Tab** | Real-time audit log stream, risk alerts, and system telemetry events |
| `f` | **Focus Mode** | **Toggle sidebar & indices bar off/on for distraction-free full-width charting** |
| `/` | **Command Palette** | **Open slash command input with live fuzzy autocomplete** |
| `r` | **Refresh All** | Force immediate synchronization of quotes, positions, and orders |

### 2. Execution & Orders
| Key | Action | Description |
|:---:|---|---|
| `b` | Buy Order | Open dual-panel order ticket pre-filled on BUY side |
| `s` | Sell Order | Open dual-panel order ticket pre-filled on SELL side |
| `m` | Modify Order | Modify selected pending order's price, quantity, or trigger price |
| `x` | Cancel Order | Cancel the currently selected open order |
| `X` | Cancel All | Bulk cancel all pending orders across all instruments |
| `K` | **Panic Flatten** | **Emergency kill switch: cancel all orders & flatten open positions at MKT** |

### 3. Charting & Analytical Overlays
| Key | Action | Description |
|:---:|---|---|
| `c` | Analytical Chart | Open native OHLC candlestick chart for active symbol |
| `k` | Candle / Line | Toggle between **OHLC Candlestick** and **Braille Line** modes |
| `e` | Toggle EMA | Toggle **EMA(9)** and **EMA(21)** moving average trend overlays |
| `i` | Toggle RSI | Toggle **RSI(14)** momentum oscillator sub-panel |
| `v` | Toggle Volume | Toggle directional volume histogram strip |
| `1`-`0`, `f`, `d`, `w` | Timeframe | Instant timeframe switch (`1m`, `3m`, `5m`, `15m`, `1h`, `1D`, `1W`) |

### 4. Algorithmic Trading Modals & Hotkeys

SKTUI equips traders with dedicated modal screens for real-time quantitative inspection and execution:

| Modal Screen | Invocation | Visual Layout & Features | Primary Hotkeys |
|---|---|---|---|
| **`QuantAnalysisModal`** | `/quant [SYM]` | Price sparkline, technical summary, quantitative risk metrics, VaR/CVaR, Beta, Alpha | `b` (Buy), `s` (Sell), `c` (Chart), `r` (Refresh), `Esc` (Close) |
| **`PairScreenerModal`** | `/pair [SEC]` | Sector universe scanner, Pearson correlation ($\rho$), stability, ADF test, p-value, half-life, Z-scores | `Enter`/`s` (Inspect Spread), `r` (Refresh), `Esc` (Close) |
| **`SpreadAnalysisModal`** | `/spread [A/B]` | High-resolution **Braille spread canvas**, rolling Z-score, entry/exit bands, position sizing | `e` (Execute Pair), `c` (Chart A), `r` (Refresh), `Esc` (Close) |
| **`SignalScannerModal`** | `/signal [SYM]` | 7-indicator voting breakdown, confidence meters, dynamic ATR stop loss & take profit | `b` (Buy), `s` (Sell), `c` (Chart), `r` (Rescan), `Esc` (Close) |
| **`BacktestModal`** | `/backtest [STRAT]` | Interactive strategy selector, mode toggle, **Braille equity curve**, risk ratios, trade log | `r` (Run), `o` (Optimize Grid), `t` (Toggle Trades), `Esc` (Close) |
| **`BotManagerModal`** | `/bot`, `/bots` | Fleet telemetry gauges, active bot registry, live order queue, panic stop | `s` (Start), `p` (Pause/Resume), `x` (Stop), `k` (Cancel All), `f` (Flatten All) |
| **`BrokerVerifyModal`** | `/verify` | Diagnostic matrix (Crypto, Paper, Endpoints), latency gauges, trace log | `r` (Rerun All), `c` (Crypto), `p` (Paper), `e` (Endpoints), `Esc` (Close) |

*Core diagnostic modals also available:* `MarketDepthModal` (`/depth`, `D`), `OptionChainModal` (`/chain`, `o`), `ReplayModal` (`/replay`), `ScannerModal` (`/scanner`), `ThemeModal` (`/theme`, `ctrl+t`).

---

## 💬 Slash Commands Reference (`/`)

Press `/` anywhere in the app to open the command palette with live fuzzy autocomplete:

| Command | Category | Syntax / Usage | Description |
|---|---|---|---|
| `/quant` | Quant Analysis | `/quant [SYM]` | Open quantitative risk & performance metrics modal |
| `/analyze` | Quant Analysis | `/analyze [SYM]` | Open technical indicators, RSI+MACD signal, and factor ranking |
| `/pair` | Pair Screener | `/pair [SECTOR]` | Open statistical arbitrage and cointegration pair screener |
| `/spread` | Pair Screener | `/spread [A/B]` | Open rolling Z-score Braille canvas and 1-key pair execution |
| `/signal` / `/signals` | Signals | `/signal [SYM]` | Open 7-indicator composite scanner with dynamic ATR risk levels |
| `/backtest` | Backtesting | `/backtest [STRATEGY]` | Open strategy backtester, Braille equity curve, and grid optimizer |
| `/bot` / `/bots` | Automation | `/bot` | Open autonomous bot fleet manager, live telemetry, and panic switch |
| `/verify` | Diagnostics | `/verify` | Open broker sandbox and cryptographic verification diagnostics |
| `/chart` | Charting | `/chart [SYM]` | Open native analytical candlestick chart |
| `/chain` | Options | `/chain [SYM]` | Interactive options chain matrix with Greeks |
| `/depth` | Market Data | `/depth [SYM]` | Level 2 market depth order book ladder |
| `/quote` | Market Data | `/quote [SYM]` | Live quote and price statistics card |
| `/scanner` | Market Data | `/scanner` | Real-time market movers and volume scanner |
| `/replay` | Simulation | `/replay` | Historical tick-by-tick tape replay simulator |
| `/buy`, `/sell` | Execution | `/buy` / `/sell` | Open dual-panel order ticket pre-filled for selected symbol |
| `/modify` | Execution | `/modify` | Modify price, quantity, or trigger price of selected pending order |
| `/cancel` | Execution | `/cancel` | Cancel currently selected open order |
| `/flatten` | Execution | `/flatten` | Trigger emergency panic flatten confirmation modal |
| `/risk` | Risk & Safety | `/risk` | View pre-trade risk policy limits, daily drawdown, and lockout status |
| `/whatif` | Risk & Safety | `/whatif` | Simulate order margin requirements and portfolio risk impact |
| `/kill` | Risk & Safety | `/kill` | Emergency block on new automated order generation |
| `/alert` | Alerts | `/alert RELIANCE > 3000` | Register persistent price or technical trigger |
| `/alerts` | Alerts | `/alerts` | View, inspect, or clear active price & technical alerts |
| `/analytics` | Portfolio | `/analytics` | View portfolio P&L decomposition and sector attribution |
| `/export` | Portfolio | `/export` | Export session trades, positions, and analytics to CSV |
| `/audit` | Audit Trail | `/audit` | Inspect the local JSONL execution audit log |
| `/status` | System | `/status` | View system health, feed latency, and public IP diagnostics |
| `/theme` | Interface | `/theme` | Switch workstation theme with live visual preview |
| `/focus` | Interface | `/focus` | Toggle single-instrument focus mode |
| `/add`, `/remove` | Watchlist | `/add [SYM]`, `/remove` | Add or remove symbol from active watchlist |
| `/help` | General | `/help` | Display interactive workstation documentation and key reference |

---

## 📂 Storage Architecture & Safe Logging

SKTUI conforms strictly to standard XDG desktop environment directory specifications, ensuring isolated, secure configuration and session persistence:

```
~/.config/sktui/
├── config.json         # Profiles, API keys, customer ID, encrypted token
├── watchlist.json      # Configured watchlists and scrip metadata
└── alerts.json         # Persistent price and technical triggers (0o600 permissions)

~/.local/share/sktui/
├── session.json        # Active authenticated broker session
├── audit.jsonl         # Append-only execution and risk audit trail
├── sktui.log           # Rotating structured operational logs (10 MB × 5)
├── session_*.csv       # Exported session analytics reports
└── crash_*.log         # Automated diagnostic crash reports (on uncaught exception)
```

---

## 🧪 Testing & Reliability <a id="testing--reliability"></a>

The workstation is validated by an automated test suite with **454 passing tests** across **26 modules**, achieving 100% pass rate in ~75 seconds. The suite covers pure-Python mathematical algorithms, risk guardrails, state store transitions, feed health, and an opaque-box 4-tier End-to-End (E2E) testing track:

```
============================= 454 passed in 75.73s =============================
```

### Complete Test Module Breakdown (454 Tests / 26 Modules)

| Test Module Path | Tests | Primary Verification Scope |
|---|:---:|---|
| `tests/test_remediation.py` | 37 | Bug remediation (tape save on unmount, `__main__` import guard, version sync, timer safe scheduling), CLI subparsers, slash routing |
| `tests/test_bot_orchestration.py` | 50 | Deterministic BotState machine lifecycle, PMM inventory skewing, statistical arbitrage, momentum & predictor strategies, risk engine, panic killswitch |
| `tests/test_new_modules.py` | 46 | Quote store, feed health, order service, API parsing, and legacy regression protection |
| `tests/test_backtesting_engine.py` | 45 | Dual-mode backtester (vectorized & event-driven replay), bias prevention, transaction costs, 8 standard strategies catalog, grid optimizer, walk-forward validation |
| `tests/test_pair_trading_and_signals.py` | 33 | Pure-Python OLS, ADF cointegration test, half-life, rolling Z-scores, position sizing, 7-indicator composite signal engine |
| `tests/test_broker_sandbox_verification.py` | 31 | AES-GCM 256 crypto validation, key length enforcement, token halves swapping, corrupted auth tag detection, in-memory paper sandbox parity |
| `tests/test_performance_and_edge_cases.py` | 24 | Performance under high tick rates, memory stability, boundary cases |
| `tests/test_quant_and_stock_analysis.py` | 23 | Pure-Python Stochastic & ADX indicators, QuantAnalyst risk engine (Sharpe, Sortino, VaR/CVaR, Beta, Alpha, $R^2$), StockAnalyzer service |
| `tests/test_realtime_charts.py` | 17 | Terminal OHLC candlestick rendering, Braille charts, indicator overlays (EMA, VWAP, RSI) |
| `tests/test_api.py` | 13 | Sharekhan API payload serialization, feed parsing, header validation |
| `tests/test_risk_and_analytics.py` | 12 | Pre-trade risk controls, drawdown lockout, rate limiting, audit trail logging, quote store staleness, alert engine price/technical triggers |
| `tests/test_qa_audit_regressions.py` | 11 | Quality assurance regression prevention and code sanity |
| `tests/test_shortcuts_and_charts.py` | 9 | Keyboard shortcuts, synthetic history generation, quote priority |
| `tests/test_watchlist_tatamotors.py` | 8 | Watchlist item selection, price fidelity, zero synthetic tape overwrite |
| `tests/test_themes.py` | 6 | Custom and builtin color palettes, theme persistence, live preview switching |
| `tests/test_services.py` | 5 | Service layer data propagation and dashboard card updates |
| `tests/test_ui.py` | 5 | Textual app lifecycle, widget rendering, market data services |
| `tests/test_enhanced_data_pipeline.py` | 4 | Real-time tick aggregation and streaming pipeline |
| `tests/test_redesign_workspace.py` | 4 | Workspace layout transitions and component mount safety |
| **`tests/e2e/test_e2e_r1_cli_and_workstation.py`** | **10** | **E2E Tier 1 & 2**: CLI help, argument parsing, unknown subcommand errors, workstation mount/unmount |
| **`tests/e2e/test_e2e_r2_quant_stock_analysis.py`** | **10** | **E2E Tier 1 & 2**: Quant risk metrics, ADX/Stochastic calculations, flat/zero-volatility resilience |
| **`tests/e2e/test_e2e_r3_pair_trading_signals.py`** | **10** | **E2E Tier 1 & 2**: ADF cointegration, OLS hedge ratios, composite signal engine, boundary resilience |
| **`tests/e2e/test_e2e_r4_backtesting_engine.py`** | **10** | **E2E Tier 1 & 2**: 8 strategy catalog, look-ahead bias prevention, cost modeling, catastrophic loss halts |
| **`tests/e2e/test_e2e_r5_bot_orchestration.py`** | **10** | **E2E Tier 1 & 2**: Bot lifecycle state machine, PMM quotes, arbitrage triggers, daily loss lockout, panic halt |
| **`tests/e2e/test_e2e_r6_broker_sandbox_verify.py`** | **10** | **E2E Tier 1 & 2**: AES-GCM crypto roundtrips, tampered tag rejection, paper sandbox fills, latency probes |
| **`tests/e2e/test_e2e_cross_feature_scenarios.py`** | **11** | **E2E Tier 3 & 4**: Cross-service data handoff pipelines and 5 full-session real-world trading scenarios |
| **Total Test Suite** | **454** | **100% Passing (0 failures, 0 errors, 0 regressions)** |

---

### 4-Tier End-to-End (E2E) Acceptance Hierarchy

The 71 end-to-end tests under `tests/e2e/` follow an institutional 4-tier acceptance hierarchy:

- **Tier 1 (T1) — Happy Path Functional Verification**: Validates expected operations across CLI subcommands, indicator calculations, screener runs, backtests, and bot lifecycle transitions under standard conditions.
- **Tier 2 (T2) — Edge Case, Boundary & Resilience Verification**: Validates behavior under zero-division conditions, flat price series, extreme volatility, corrupted authentication tags, empty datasets, and invalid user inputs with zero unhandled exceptions.
- **Tier 3 (T3) — Cross-Feature Integration Chains**: Validates inter-service data handoffs (CLI arguments $\to$ Quant Metrics $\to$ Signal Engine $\to$ Pair Screener $\to$ Backtest Simulation $\to$ Bot Deployment $\to$ Broker Sandbox Execution).
- **Tier 4 (T4) — Comprehensive Real-World Scenarios**: Full multi-step simulation of active trading days:
  - *Scenario 1*: Statistical arbitrage pair screening $\to$ cointegration validation $\to$ paired order execution.
  - *Scenario 2*: Quant ranking $\to$ composite signal evaluation $\to$ automated momentum bot deployment.
  - *Scenario 3*: Quantitative research $\to$ multi-parameter grid search $\to$ walk-forward out-of-sample validation.
  - *Scenario 4*: Interactive terminal workstation trading session with real-time charting and order modifications.
  - *Scenario 5*: Broker sandbox resilience under high network latency and daily loss circuit breaker trip.

---

### Running the Test Suite

```bash
# Activate virtual environment
source .venv/bin/activate

# 1. Run complete test suite (all 454 tests)
pytest

# 2. Run Algorithmic & Quantitative test suites (290 tests in ~10s)
pytest -v \
  tests/test_remediation.py \
  tests/test_quant_and_stock_analysis.py \
  tests/test_pair_trading_and_signals.py \
  tests/test_backtesting_engine.py \
  tests/test_bot_orchestration.py \
  tests/test_broker_sandbox_verification.py \
  tests/e2e/

# 3. Run only the 4-Tier E2E acceptance test suite (71 tests)
pytest -v tests/e2e/

# 4. Run automated broker sandbox verification diagnostic directly from CLI
sktui verify --sandbox
```

---

## ⚖️ License & Disclaimer

- **License**: MIT License. See [LICENSE](LICENSE) for details.
- **Risk Notice**: Financial trading involves substantial risk of capital loss. Automated algorithms, backtesting simulations, and trading bots carry inherent execution risks. Past performance and backtested results do not guarantee future returns. Always test your configuration in **Paper Mode** (`sktui --paper`) before deploying live capital.
