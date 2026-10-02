# SKTUI

Terminal trading UI for the **Mirae Asset Sharekhan** API, built with [Textual](https://textual.textualize.io/).
Implemented directly against Sharekhan's REST + websocket API documentation (no SDK dependency).
Unofficial; not affiliated with Sharekhan.

> **Risk:** this software can place real orders. Start with `sktui --paper` (nothing is sent or cancelled).
> You are responsible for every order.

## Features
- **Trading:** buy / sell / modify / cancel (single or all open) with a review + confirmation step
  - Segments: NSE & BSE equity (incl. ETFs), NSE F&O (FS/FI/OS/OI), NSE currency, MCX
  - Products INVESTMENT / BIGTRADE / BIGTRADE+, validity GFD / MyGTD / IOC, AMO, market (price 0) & limit
  - Lot-size, tick-size, market-order and AMO warnings
- **Live websocket:** quotes (LTP, change, bid/ask, OHLC, volume, OI), quote detail, live order/trade acknowledgements
- **Account:** orders of the day, positions, holdings, funds per segment, order history & trades
- **Market data:** scrip-master search (cached daily), historical candles (1 min … yearly) with sparkline
- **Products screen:** what is tradable via the API, plus browser shortcuts for IPO, MF, PMS, bonds, etc.
  (those are not part of Sharekhan's API)

## Install on Windows 11
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
Or via pip / virtual environment:
```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .
```

## Install on Arch Linux
```bash
sudo pacman -S --needed git python
git clone https://github.com/<your-user>/sktui.git
cd sktui
./install.sh
```
Alternative: `sudo pacman -S --needed python-pipx && pipx install .`
Make sure `~/.local/bin` is in your `PATH`.

## Run
```bash
sktui --paper     # dry-run
sktui             # live
```

## Login (Sharekhan flow)
1. Enter **API key** and **secret key** (32 characters). Vendor key only for partner logins.
2. **Open login page** -> log in in the browser. You are redirected to a URL containing `request_token=...`.
3. Paste the token (or the whole URL) and press **Log in**. SKTUI decrypts the token with your secret key,
   swaps the RequestId/CustomerId halves, re-encrypts it and exchanges it for an access token.

The access token is valid for 24 hours and cached in `~/.local/share/sktui/session.json` (mode 600).
"Remember" stores keys in `~/.config/sktui/config.json` (mode 600).
Env vars also work: `SK_API_KEY`, `SK_SECRET_KEY`, `SK_VENDOR_KEY`, `SK_VERSION_ID`.

## Keys
| Key | Action | Key | Action |
|---|---|---|---|
| a | add symbol (search scrip master) | b / s | buy / sell selected |
| Del | remove symbol | m | modify selected order |
| x | cancel selected order | X | cancel all open orders |
| i | order history & trades | c | historical chart |
| ? | live quote detail | p | products & services |
| 1-6 | tabs (Watchlist, Orders, Positions, Holdings, Funds, Activity) | r | refresh |
| d | raw feed log | ctrl+l | log out |
| q | quit | | |

Derivatives: search like `NIFTY 25000 CE` or `NIFTY` in the NSE F&O segment; instrument type, strike, option
type and expiry are filled from the scrip master.

## Notes / assumptions
- Intraday vs delivery is expressed through the API's `productType` field; the docs list INVESTMENT, BIGTRADE and BIGTRADE+.
- Only exchanges enabled on your account (returned at login) are offered.
- Historical candles: Sharekhan returns minute candles up to 90 minutes plus daily and longer.
- Websocket subscriptions are sent one scrip per request, exactly as in the documentation.

## Develop
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License
MIT
