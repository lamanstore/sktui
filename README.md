# ⚡ SKTUI — Professional Terminal Trading Workstation

> **A fast, keyboard-first terminal trading workstation built for active Indian equity and derivative traders (NSE · BSE · NFO).**  
> *Real-time tick monitoring · institutional pre-trade risk guardrails · native OHLC candlestick analysis · deterministic order lifecycle execution — without ever leaving the terminal.*

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](#installation)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Framework: Textual](https://img.shields.io/badge/TUI-Textual-00e5ff.svg)](https://textual.textualize.io/)
[![Market: NSE / BSE](https://img.shields.io/badge/Exchange-NSE%20%7C%20BSE%20%7C%20NFO-10b981.svg)](#supported-exchanges)

---

## 🎯 Why SKTUI?

Web dashboards and GUI trading portals are cluttered with status spam, decorative charts, and mouse-dependent click flows. Under volatile market stress, every second spent reaching for a mouse costs edge.

**SKTUI** turns your terminal into a professional trading workstation:

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

## 🛡️ Core Institutional Systems

### 1. Pre-Trade Risk Engine (`/risk`, `/whatif`)
A professional trading CLI is a **control system that prevents bad decisions**.
- **Hard Guardrails**: Max order size, max total symbol exposure, and max portfolio exposure.
- **Daily Loss Drawdown Lockout**: Auto-locks order entry when daily realized drawdown hits limits.
- **Rate-Limiter Protection**: Prevents burst submission errors (hard cap at 30 orders/minute).
- **Mandatory Stop-Loss for Derivatives**: Rejects unhedged/bracketless F&O orders before execution.
- **Pre-Trade Risk Audit**: Every order validation check is scored and recorded in the audit trail.

### 2. Interactive Analytical Candlestick Charting (`c`)
Charts are trading tools, not decorations.
- **True Terminal OHLC Candlesticks**: Rendered with wicks, directional solid bodies, and volume bars.
- **Real-Time Indicators**: Dual moving averages (`EMA 9` / `EMA 21`), `VWAP`, and `RSI 14` momentum sub-panel.
- **Interactive Hotkey Toggles**:
  - `k`: Toggle between **OHLC Candlestick** and **Braille Line** modes.
  - `e`: Toggle **EMA(9/21)** moving average overlays.
  - `i`: Toggle **RSI(14)** oscillator sub-panel.
  - `v`: Toggle directional **Volume** histogram strip.
  - Instant timeframe switching: `1m`, `3m`, `5m`, `10m`, `15m`, `30m`, `1h`, `1D`, `1W`, `1M`.

### 3. Deterministic Order Lifecycle & Emergency Panic Flatten (`Shift+K` / `K`)
- **Typed Lifecycle State Machine**: `NEW` → `PENDING_SUBMIT` → `OPEN` → `TRIGGER_PENDING` → `PARTIALLY_FILLED` → `FILLED` / `CANCELLED` / `REJECTED`.
- **Structured RMS Reason Codes**: Categorizes rejections (`RMS_INSUFFICIENT_MARGIN`, `RMS_CIRCUIT_LIMIT`, `RMS_MAX_QTY_EXCEEDED`, `RMS_DRAWDOWN_LOCKOUT`, `RMS_DERIVATIVE_NO_SL`, `MARKET_CLOSED`).
- **Emergency Panic Flatten (`K` or `/flatten`)**: Single-key confirmation cancels all open orders and squares off open intraday positions at market.
- **Tamper-Evident Audit Trail**: Every submission, rejection, fill, and cancel is written with timestamp to `~/.local/share/sktui/audit.jsonl`.

### 4. Feed Telemetry & Staleness Badging
- **High-Visibility Connection Badge**: Real-time header telemetry:
  - `● LIVE 18ms` (Vibrant emerald `#00ff87`)
  - `▲ STALE 3.2s` (Amber `#f59e0b` when tick age exceeds 2.5s)
  - `■ RECONNECTING` / `✕ OFFLINE` (Crimson `#ff4757`)
- **Watchlist Staleness Dimming**: Active symbols stream with `● SYMBOL`, while quiet or disconnected ticks dim to `▲ SYMBOL ~ PRICE`.

### 5. Persistent Alert Engine (`/alert`, `/alerts`)
- **Trader-Defined Triggers**:
  - Price: `/alert RELIANCE > 3000` or `/alert INFY < 1400`
  - Technical: `/alert TCS RSI > 70` or `/alert TCS RSI < 30`
  - Volume: `/alert ONGC VOL > 2.5`
- **JSON Persistence**: Saved securely to `~/.config/sktui/alerts.json` (`0o600` permissions) across app restarts.
- **Live Notifications**: Fires instant toast alerts and records breach events in the audit log.

### 6. Portfolio Analytics & CSV Export (`/analytics`, `/export`)
- Realized vs Unrealized P&L breakdown, win/loss ratio, and profit factor.
- Symbol concentration and sector attribution heatmap.
- `/export` dumps complete session analytics, position records, and order audits to `~/.local/share/sktui/session_YYYYMMDD_HHMMSS.csv`.

---

## 🚀 Installation & Deployment

### Method 1: Automated Installer (Linux / macOS — Recommended)

The installer sets up an isolated virtual environment and creates an executable symlink in `~/.local/bin`:

```bash
# 1. Clone repository
git clone https://github.com/your-username/sktui.git
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
pipx install git+https://github.com/your-username/sktui.git
```

#### Using `uv`:
```bash
uv tool install .
```

---

### Method 3: Windows 10/11 PowerShell Installer

```powershell
# Clone and run installer
git clone https://github.com/your-username/sktui.git
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

## ⚡ Running SKTUI

Launch directly from any terminal window:

```bash
# 1. Paper Trading Mode (Simulated fills & risk guardrails — zero real capital risk)
sktui --paper

# 2. Live Trading Mode (Direct execution against broker API)
sktui

# 3. Environment Profiles (Switch between live, paper, or custom environments)
sktui --profile live
sktui --profile paper

# 4. Diagnostic Debug Mode (Verbose logging to stdout and ~/.local/share/sktui/sktui.log)
sktui --debug
```

---

## ⚙️ Configuration & Profiles

SKTUI supports profile-based configurations stored in `~/.config/sktui/config.json`. You can maintain isolated risk rules and API credentials for paper testing versus live execution:

```json
{
  "active_profile": "default",
  "profiles": {
    "default": {
      "customer_id": "YOUR_ID",
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

## ⌨️ Workstation Keyboard Map

### 1. Navigation & Views
| Key | Action | Description |
|:---:|---|---|
| `1` | Dashboard | Overview cards: Net P&L, orders, watchlist snapshot, feed activity |
| `2` | Watchlist | Streaming market watch table |
| `3` | Orders | Active & historical orders table |
| `4` | Positions | Open & closed positions with MTM and booked P&L |
| `5` | Holdings | Demat CNC and investment portfolio |
| `6` | Funds | Trading limits, cash balance, and collateral |
| `7` | Activity | Real-time audit log and system events |
| `f` | **Focus Mode** | **Toggle sidebar & indices bar off/on for distraction-free charting** |
| `/` | **Command Palette** | **Open slash command input with live fuzzy suggestions** |

### 2. Execution & Orders
| Key | Action | Description |
|:---:|---|---|
| `b` | Buy Order | Open dual-panel order ticket pre-filled on BUY side |
| `s` | Sell Order | Open dual-panel order ticket pre-filled on SELL side |
| `m` | Modify Order | Modify selected pending order's price, quantity, or trigger |
| `x` | Cancel Order | Cancel the currently selected open order |
| `X` | Cancel All | Bulk cancel all open orders |
| `K` | **Panic Flatten** | **Emergency kill switch: cancel all orders & flatten open positions at MKT** |

### 3. Charting & Analysis
| Key | Action | Description |
|:---:|---|---|
| `c` | Chart Modal | Open native analytical candlestick chart for selected symbol |
| `k` | Candle / Line | Toggle between **OHLC Candlestick** and **Braille Line** modes |
| `e` | Toggle EMA | Toggle **EMA(9)** and **EMA(21)** trend overlays |
| `i` | Toggle RSI | Toggle **RSI(14)** momentum oscillator sub-panel |
| `v` | Toggle Volume | Toggle directional volume histogram panel |
| `1`-`0`, `f`, `d`, `w` | Timeframe | Instant timeframe switch (`1m`, `3m`, `5m`, `15m`, `1h`, `1D`, `1W`) |

---

## 💬 Slash Commands Reference (`/`)

Press `/` anywhere in the app to open the command palette with live fuzzy autocomplete:

| Command | Syntax / Usage | Description |
|---|---|---|
| `/alert` | `/alert RELIANCE > 3000` | Register persistent price trigger (above / below) |
| `/alert` | `/alert TCS RSI > 70` | Register technical trigger (RSI overbought / oversold) |
| `/alerts` | `/alerts` | Open the alerts registry modal to view, inspect, or clear alerts |
| `/flatten` | `/flatten` | Trigger the emergency panic flatten confirmation modal |
| `/export` | `/export` | Export session trades, positions, and analytics to CSV |
| `/risk` | `/risk` | View pre-trade risk policy limits, daily drawdown, and lockout status |
| `/whatif` | `/whatif` | Calculate margin requirements and portfolio risk impact |
| `/analytics`| `/analytics` | View portfolio P&L decomposition and sector attribution |
| `/audit` | `/audit` | Inspect the local JSONL execution audit trail |
| `/status` | `/status` | View system health, feed latency, and public IP diagnostics |
| `/buy`, `/sell` | `/buy` / `/sell` | Open order ticket for the currently selected symbol |
| `/chart` | `/chart` | Open analytical chart for selected symbol |
| `/add` | `/add` | Search symbol master catalog and add to watchlist |
| `/help` | `/help` | Display interactive workstation documentation and key reference |

---

## 📂 Storage Architecture & Safe Logging

SKTUI conforms to standard XDG desktop environment directory specifications:

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

## 🧪 Testing & Reliability

The workstation includes an automated test suite covering API normalization, risk guardrails, state store transitions, indicator calculations, feed staleness, alert persistence, and UI components:

```bash
# Run pytest test suite
pytest -v

# Results:
# ============================== 72 passed in 8.91s ==============================
# - tests/test_api.py ......................... (13 passed)
# - tests/test_new_modules.py ................. (39 passed)
# - tests/test_risk_and_analytics.py .......... (12 passed)
# - tests/test_services.py .................... (5 passed)
# - tests/test_ui.py .......................... (3 passed)
```

---

## ⚖️ License & Disclaimer

- **License**: MIT License.
- **Risk Notice**: Live financial trading involves substantial risk of loss. Always test your configuration in **Paper Mode** (`sktui --paper`) before deploying live capital.
