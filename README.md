# ⚡ SKTUI — Professional Terminal Trading Interface for Sharekhan

**SKTUI** is a modern, high-performance, dark-themed Terminal User Interface (TUI) for the **Mirae Asset Sharekhan API**, built with [Textual](https://textual.textualize.io/) and Python. 

Designed for active traders, quantitative developers, and terminal enthusiasts, SKTUI provides full real-time market data streaming, rate.sx-style braille charts, instant symbol search, and an intuitive two-panel order ticket—all directly inside your terminal.

> ⚠️ **Risk Notice:** SKTUI places live orders on your Sharekhan trading account. Always test your setup using **Paper Mode** (`sktui --paper`) first. You are solely responsible for all trades executed.

---

## ✨ Key Features & Highlights

- ❖ **Portfolio & Market Overview Dashboard (`/dashboard` or `1`)**: Unified 4-card overview showing Net P&L (Realised + MTM), Order Status Distribution, Watchlist Quick Snapshot with sparklines, and Live Activity Audit Log.
- 📊 **Live Watchlist (`/watchlist` or `2`)**: Real-time websocket quotes with dynamic columns (`LTP`, `Chg ₹`, `Chg%`, `Bid`, `Ask`, `Open`, `High`, `Low`, `Close`, `Volume`, `OI`) and micro sparkline trend charts.
- 📈 **Rate.sx Braille Charts with Volume Sub-strips (`c`)**: Dual-panel price braille dots + volume histograms, candle volume metrics, clickable interval pills (`1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `1D`, `1W`, `1M`), instant hotkeys (`1`, `3`, `5`, `0`, `f`, `t`, `h`, `d`, `w`, `m`), and full-screen volume mode (`v`).
- 🛒 **Side-by-Side Dual-Panel Order Ticket (`b` / `s` / `m`)**:
  - **Left Panel (Core Order)**: Scrip Search, Buy/Sell, Quantity, Limit/Market Price, Order Type (`NORMAL`, `SL`, `SL-M`), Validity (`GFD`, `IOC`), and ⚡ **Auto-fill LTP** button.
  - **Right Panel (Advanced & Derivatives)**: Stop Loss Trigger, Target Price, Trailing SL, Product Type (`INVESTMENT`, `BIGTRADE`, `BIGTRADE+`), Option Type (`CE`/`PE`), Strike Price, and Expiry Date.
  - **Scrip Code Auto-Resolution**: Automatically looks up and displays the exact numerical exchange scrip code (e.g. `23481` for ONGC on NSE `NC` vs `500312` for ONGC on BSE `BC`).
  - **Tick Size Auto-Rounding**: Automatically quantizes limit/trigger prices to exact exchange tick size boundaries (e.g. `0.05`), preventing `[400] Kindly enter proper tick price` RMS errors.
- ⚡ **Non-Blocking Asynchronous Master Search (`a`)**: Instant search across NSE/BSE Equity, NSE F&O, Currency (`RN`), and Commodities (`MX`) powered by background worker threads and built-in stock catalog (`BUILTIN_SCRIPS`).
- 📝 **Full In-Memory Paper Trading Engine (`sktui --paper`)**: Local mock order ledger (`POP-1001`), simulated execution, paper positions tracking with live average prices, and paper holdings management without live broker risk.
- 🌐 **Public IP Whitelisting Diagnostics**: Automatically fetches machine public IP address and displays it on the Login Screen (`⚙ API Config`) and `/status` screen for instant Sharekhan portal whitelisting.

---

## 🚀 Installation & Update Guide

### 🐧 Linux Installation (Arch / Ubuntu / Debian / Fedora)

```bash
# 1. Clone repository
git clone https://github.com/your-username/sktui.git
cd sktui

# 2. Run install script
./install.sh
```

### 🪟 Windows Installation (PowerShell)

```powershell
# 1. Clone repository
git clone https://github.com/your-username/sktui.git
cd sktui

# 2. Run install script
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

---

## 🔄 How Updates Work (`git pull`)

**Do I need to re-run `install.sh` or `install.ps1` every time the developer pushes updates?**

> **NO!** Both `install.sh` and `install.ps1` install SKTUI in **Editable Mode** (`pip install -e .`). 
> 
> When SKTUI is installed in editable mode, Python links directly to your cloned source code folder. 
> Whenever you pull updates from GitHub:
> ```bash
> git pull
> ```
> **The updates are active immediately!** You do **NOT** need to re-run any installer or setup script.

---

## ⚡ Running SKTUI & Environment Activation

### Running Directly from Terminal
If `~/.local/bin` (Linux) or `%USERPROFILE%\.local\share\sktui\venv\Scripts` (Windows) is in your `PATH`:

```bash
# Paper Mode (Simulated / Dry-run)
sktui --paper

# Live Mode (Real Sharekhan API Orders)
sktui
```

### Manual Virtual Environment Activation

If you prefer to activate the virtual environment manually before running:

#### Linux:
```bash
source ~/.local/share/sktui/venv/bin/activate
sktui
```

#### Windows (PowerShell):
```powershell
& "$HOME\.local\share\sktui\venv\Scripts\Activate.ps1"
sktui
```

---

## 🔐 Login & Sharekhan Authentication Flow

1. On launch, click **⚙ API Config** and enter your **API Key** and **Secret Key** (32 characters).
   - Your machine's **Public IP Address** is displayed right in the API Config box so you can whitelist it in the [Sharekhan API Portal](https://api.sharekhan.com).
2. Click **Step 1 · Open Login Page in Browser** -> log into Sharekhan in your browser.
3. Upon successful login, copy the browser URL (or `request_token=...`) and paste it into **Step 2**.
4. Click **Connect to Sharekhan**. SKTUI decrypts the token with your secret key, exchanges it for a 24-hour JWT session token, and launches the terminal.

---

## ⌨️ Keyboard Shortcuts & Slash Commands

### Tab Navigation & Views
| Key / Command | View / Action |
|---|---|
| `1` or `/dashboard` | Portfolio & Market Overview Dashboard |
| `2` or `/watchlist` | Live Watchlist Data Table |
| `3` or `/orders` | Open Orders & Order History |
| `4` or `/positions` | Open & Closed Positions |
| `5` or `/holdings` | Account Holdings |
| `6` or `/funds` | Funds & Margin Statement |
| `7` or `/activity` | Live Event Audit Log |

### Order & Trading Actions
| Key / Command | Action |
|---|---|
| `b` or `/buy` | Open BUY Order Ticket for selected scrip |
| `s` or `/sell` | Open SELL Order Ticket for selected scrip |
| `m` or `/modify` | Modify selected order |
| `x` or `/cancel` | Cancel selected open order |
| `X` | Cancel ALL open orders |
| `a` or `/add` | Add symbol via non-blocking Master Search |
| `Del` or `/remove` | Remove selected symbol from Watchlist |

### Chart & Tools
| Key / Command | Action |
|---|---|
| `c` or `/chart` | Open dual Price + Volume chart |
| `v` (inside chart) | Toggle full-screen volume histogram mode |
| `1 3 5 0 f t h d w m` | Switch chart interval (`1m` … `1M`) |
| `/whatif` | Order margin & P&L impact calculator |
| `/risk` | System safety & risk controls dashboard |
| `/status` | System health, API status & Public IP |
| `r` or `/refresh` | Refresh all account data |
| `F1` or `/help` | Complete help manual |
| `Esc` | Close active modal dialog |
| `Ctrl+L` | Log out and clear session |
| `q` | Quit SKTUI |

---

## 🛠️ Development & Contributing

To set up a local development environment:

```bash
# Clone repo
git clone https://github.com/your-username/sktui.git
cd sktui

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install editable with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

---

## 📄 License
MIT License. Unofficial software; not affiliated with Sharekhan or Mirae Asset.
