"""Test suite for performance optimizations and edge cases:
- Tick size rounding, boundary conditions, and precision
- Order building and validation edge cases (volumes, lot sizes, SL triggers)
- Chart rendering edge cases (empty data, single candle, flat lines, zero volume)
- Paper trading O(1) indexed lookups and cancellation
- DataTable in-place diffing and column preservation
"""
import asyncio
from decimal import Decimal
import pytest
from rich.text import Text
from textual.app import App
from textual.widgets import DataTable

from sktui.api.client import Client
from sktui.chart import (
    Candle,
    calc_ema,
    calc_rsi,
    calc_sma,
    calc_vwap,
    render_candlestick_chart,
    render_chart,
)
from sktui.utils import (
    _table_row_key,
    build_order,
    default_tick_size,
    fill_table,
    round_to_tick,
)


# ── 1. Tick Rounding & Boundary Edge Cases ────────────────────────────────────

def test_default_tick_size():
    # Equity / Derivatives should default to 0.05
    assert default_tick_size("NC") == Decimal("0.05")
    assert default_tick_size("BC") == Decimal("0.05")
    assert default_tick_size("NF") == Decimal("0.05")
    assert default_tick_size("") == Decimal("0.05")

    # Currency exchange in Sharekhan (RN) is 0.0025
    assert default_tick_size("RN") == Decimal("0.0025")

    # MCX Commodity (MX) is 0.1
    assert default_tick_size("MX") == Decimal("0.1")


def test_round_to_tick_exact_boundaries():
    tick = Decimal("0.05")
    # Exact tick boundaries stay identical
    assert round_to_tick(Decimal("100.00"), tick) == Decimal("100.00")
    assert round_to_tick(Decimal("100.05"), tick) == Decimal("100.05")
    assert round_to_tick(Decimal("100.10"), tick) == Decimal("100.10")


def test_round_to_tick_half_up_and_rounding():
    tick = Decimal("0.05")
    # 100.02 rounds down to 100.00
    assert round_to_tick(Decimal("100.02"), tick) == Decimal("100.00")
    # 100.03 rounds up to 100.05
    assert round_to_tick(Decimal("100.03"), tick) == Decimal("100.05")
    # 100.025 rounds up to 100.05 (ROUND_HALF_UP)
    assert round_to_tick(Decimal("100.025"), tick) == Decimal("100.05")
    # 100.07 rounds down to 100.05
    assert round_to_tick(Decimal("100.07"), tick) == Decimal("100.05")
    # 100.08 rounds up to 100.10
    assert round_to_tick(Decimal("100.08"), tick) == Decimal("100.10")


def test_round_to_tick_currency_precision():
    tick = Decimal("0.0025")
    # 82.1234 -> closest 0.0025 multiple is 82.1225
    assert round_to_tick(Decimal("82.1234"), tick) == Decimal("82.1225")
    # 82.1238 -> closest 0.0025 multiple is 82.1250
    assert round_to_tick(Decimal("82.1238"), tick) == Decimal("82.1250")


def test_round_to_tick_invalid_or_zero():
    tick = Decimal("0.05")
    # Zero or negative should return unmodified
    assert round_to_tick(Decimal("0"), tick) == Decimal("0")
    assert round_to_tick(Decimal("-10.5"), tick) == Decimal("-10.5")
    # Zero or negative tick size should return unmodified value
    assert round_to_tick(Decimal("100.03"), Decimal("0")) == Decimal("100.03")
    assert round_to_tick(Decimal("100.03"), Decimal("-0.05")) == Decimal("100.03")


# ── 2. Order Building & Validation Edge Cases ─────────────────────────────────

def test_build_order_normal_equity():
    f = {
        "exchange": "NC",
        "scripCode": "2475",
        "tradingSymbol": "ONGC",
        "transactionType": "B",
        "quantity": "50",
        "price": "92.53",  # Unrounded: should round to 92.55
        "orderType": "NORMAL",
        "productType": "INVESTMENT",
    }
    p, warns = build_order(f, "NEW", "12345", "LOGIN")
    assert p["scripCode"] == 2475
    assert p["quantity"] == 50
    assert p["price"] == "92.55"  # Auto-rounded to nearest 0.05 tick!
    assert p["exchange"] == "NC"


def test_build_order_currency_four_decimal_places():
    f = {
        "exchange": "RN",
        "scripCode": "100",
        "tradingSymbol": "USDINR-FUT",
        "transactionType": "B",
        "quantity": "1",
        "price": "83.1234",
        "orderType": "NORMAL",
        "productType": "INVESTMENT",
        "instrumentType": "FUTCUR",
        "expiry": "28/11/2026",
    }
    p, warns = build_order(f, "NEW", "12345", "LOGIN")
    # Currency RN exchange formats to 4 decimal places and auto-rounds 83.1234 -> 83.1225
    assert p["price"] == "83.1225"


def test_build_order_validation_errors():
    base = {
        "exchange": "NC",
        "scripCode": "2475",
        "tradingSymbol": "ONGC",
        "transactionType": "B",
        "quantity": "10",
        "price": "100.0",
    }

    # Negative quantity
    with pytest.raises(ValueError, match="quantity must be > 0"):
        build_order({**base, "quantity": "-5"}, "NEW", "1", "1")

    # Zero quantity
    with pytest.raises(ValueError, match="quantity must be > 0"):
        build_order({**base, "quantity": "0"}, "NEW", "1", "1")

    # Invalid scrip code
    with pytest.raises(ValueError, match="scrip code must be an integer"):
        build_order({**base, "scripCode": "invalid"}, "NEW", "1", "1")

    # Invalid exchange
    with pytest.raises(ValueError, match="exchange must be one of"):
        build_order({**base, "exchange": "XYZ"}, "NEW", "1", "1")

    # Negative price
    with pytest.raises(ValueError, match="cannot be negative"):
        build_order({**base, "price": "-10.0"}, "NEW", "1", "1")

    # Derivatives missing expiry
    with pytest.raises(ValueError, match="derivatives need instrument type and expiry"):
        build_order(
            {
                "exchange": "NF",
                "scripCode": "10",
                "tradingSymbol": "NIFTY-FUT",
                "transactionType": "B",
                "quantity": "50",
                "price": "22000",
            },
            "NEW", "1", "1",
        )

    # Stop Loss order without trigger price
    with pytest.raises(ValueError, match="requires Trigger Price > 0"):
        build_order(
            {**base, "triggerPrice": "0", "orderType": "SL"},
            "NEW", "1", "1",
        )


def test_build_order_lot_and_market_warnings():
    f = {
        "exchange": "NC",
        "scripCode": "2475",
        "tradingSymbol": "ONGC",
        "transactionType": "B",
        "quantity": "25",
        "lotSize": "50",  # 25 is not a multiple of 50
        "price": "0",     # Market order
        "orderType": "NORMAL",
    }
    p, warns = build_order(f, "NEW", "12345", "LOGIN")
    assert any("not a multiple of lot size" in w for w in warns)
    assert any("Price 0 = MARKET order" in w for w in warns)


# ── 3. Chart Rendering Edge Cases ─────────────────────────────────────────────

def test_render_chart_empty():
    txt = render_chart([])
    assert "no data" in txt.plain


def test_render_chart_single_value():
    txt = render_chart([150.0], width=40, height=8, symbol="RELIANCE")
    assert "RELIANCE" in txt.plain
    assert "150.00" in txt.plain


def test_render_chart_flat_series():
    # Completely flat line where hi == lo
    flat = [200.0] * 30
    txt = render_chart(flat, width=40, height=8, symbol="NIFTY")
    assert "NIFTY" in txt.plain
    assert "200.00" in txt.plain


def test_render_chart_extreme_values_and_volume():
    # Large scale prices
    large_prices = [1_500_000.0, 1_550_000.0, 1_520_000.0]
    volumes = [0.0, 0.0, 0.0]  # Zero volume strip
    txt = render_chart(large_prices, volumes=volumes, width=50, height=10, symbol="BTC")
    assert "BTC" in txt.plain
    assert "1.52M" in txt.plain or "1.55M" in txt.plain


def test_render_candlestick_chart_empty():
    txt = render_candlestick_chart([])
    assert "no candlestick data" in txt.plain


def test_render_candlestick_chart_single_candle():
    candle = Candle(timestamp="1", open=100.0, high=105.0, low=98.0, close=102.0, volume=500.0)
    txt = render_candlestick_chart([candle], width=40, height=10, symbol="TCS")
    assert "TCS" in txt.plain
    assert "102.00" in txt.plain


def test_render_candlestick_chart_flat_candle():
    # Open == High == Low == Close, 0 volume
    flat_candle = Candle(timestamp="1", open=50.0, high=50.0, low=50.0, close=50.0, volume=0.0)
    txt = render_candlestick_chart([flat_candle], width=40, height=8, symbol="FLAT")
    assert "FLAT" in txt.plain
    assert "50.00" in txt.plain


def test_indicator_edge_cases():
    assert calc_sma([], 5) == []
    assert calc_sma([10.0, 20.0], 5) == [None, None]

    assert calc_ema([], 9) == []
    assert calc_ema([10.0] * 5, 9) == [None] * 5

    assert calc_rsi([], 14) == []
    # Flat price series has 0 gain and 0 loss -> safe neutral 50.0 RSI
    flat_prices = [100.0] * 25
    rsi_flat = calc_rsi(flat_prices, 14)
    assert rsi_flat[14] == 50.0

    assert calc_vwap([]) == []
    # Zero volume candle in calc_vwap
    c_zero_vol = Candle(timestamp="1", open=100.0, high=100.0, low=100.0, close=100.0, volume=0.0)
    vwap = calc_vwap([c_zero_vol])
    assert len(vwap) == 1
    assert vwap[0] == 100.0


# ── 4. Paper Trading O(1) Indexed Lookups ─────────────────────────────────────

def test_paper_trading_indexed_lookups():
    client = Client("key", "tok", "123", paper=True)

    # Place order 1
    p1 = {
        "tradingSymbol": "INFY",
        "exchange": "NC",
        "transactionType": "B",
        "quantity": 10,
        "price": "1400.00",
        "productType": "INVESTMENT",
    }
    res1 = client.submit(p1)
    oid1 = res1["orderId"]

    # Verify O(1) indexed order presence
    assert oid1 in client._paper_orders_by_id
    assert client._paper_orders_by_id[oid1]["tradingSymbol"] == "INFY"

    # Verify O(1) position presence
    assert ("INFY", "NC") in client._paper_positions_by_key
    pos = client._paper_positions_by_key[("INFY", "NC")]
    assert pos["netQty"] == 10
    assert pos["avgPrice"] == 1400.0

    # Verify O(1) holding presence
    assert "INFY" in client._paper_holdings_by_sym
    assert client._paper_holdings_by_sym["INFY"]["aval"] == 10

    # Place order 2 for same scrip -> should aggregate in O(1)
    p2 = {
        "tradingSymbol": "INFY",
        "exchange": "NC",
        "transactionType": "B",
        "quantity": 10,
        "price": "1500.00",
        "productType": "INVESTMENT",
    }
    client.submit(p2)
    assert len(client.positions()) == 1  # 1 consolidated position
    assert pos["netQty"] == 20
    assert pos["avgPrice"] == 1450.0  # (10*1400 + 10*1500)/20 = 1450
    assert client._paper_holdings_by_sym["INFY"]["aval"] == 20

    # Fast O(1) order cancellation
    cancel_res = client.cancel_by_id(oid1)
    assert cancel_res["sent"] is True
    assert client._paper_orders_by_id[oid1]["orderStatus"] == "Cancelled"


# ── 5. Table Diffing and In-Place Updates ─────────────────────────────────────

def test_fill_table_in_place_updating():
    class TableApp(App):
        def compose(self):
            yield DataTable(id="tbl")

    async def run():
        app = TableApp()
        async with app.run_test() as pilot:
            table = app.query_one("#tbl", DataTable)
            cols = [("sym", "Symbol"), ("ltp", "Price"), ("status", "Status")]
            rows_v1 = [
                {"orderId": "101", "sym": "INFY", "ltp": 1400.0, "status": "Pending"},
                {"orderId": "102", "sym": "TCS", "ltp": 3500.0, "status": "Pending"},
            ]

            # First load: initializes columns and rows
            fill_table(table, rows_v1, cols)
            assert table.row_count == 2
            col_keys = [c.value for c in table.columns.keys()]
            assert col_keys == ["sym", "ltp", "status"]

            # Second load: same rows, updated values (status & price changed)
            rows_v2 = [
                {"orderId": "101", "sym": "INFY", "ltp": 1405.0, "status": "Fully Executed"},
                {"orderId": "102", "sym": "TCS", "ltp": 3510.0, "status": "Pending"},
            ]
            fill_table(table, rows_v2, cols)

            # Row count and column structure remain unchanged
            assert table.row_count == 2
            assert [c.value for c in table.columns.keys()] == ["sym", "ltp", "status"]
            # Updated cell verified
            cell_101_status = table.get_cell("ord_101", "status")
            assert "Fully Executed" in str(cell_101_status)

            # Empty data preserves column layout without wiping headers
            fill_table(table, [], cols)
            assert table.row_count == 0
            assert [c.value for c in table.columns.keys()] == ["sym", "ltp", "status"]

    asyncio.run(run())


# ── 6. Real-Time Market Scanner Tests ─────────────────────────────────────────

def test_market_scanner_analytics():
    from sktui.state.quote_store import QuoteStore
    from sktui.services.scanner import MarketScanner

    store = QuoteStore()
    store.update("NC100", {
        "tradingSymbol": "GAIN", "exchange": "NC", "scripCode": "100",
        "ltp": 120.0, "open": 100.0, "high": 122.0, "low": 99.0, "close": 100.0,
        "rsChange": 20.0, "perChange": 20.0, "qty": 50000.0,
    })
    store.update("NC200", {
        "tradingSymbol": "LOSE", "exchange": "NC", "scripCode": "200",
        "ltp": 80.0, "open": 100.0, "high": 101.0, "low": 79.0, "close": 100.0,
        "rsChange": -20.0, "perChange": -20.0, "qty": 10000.0,
    })
    store.update("NC300", {
        "tradingSymbol": "FLAT", "exchange": "NC", "scripCode": "300",
        "ltp": 100.0, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0,
        "rsChange": 0.0, "perChange": 0.0, "qty": 2000.0,
    })

    scanner = MarketScanner(store)

    # Top Movers: GAIN (20%) and LOSE (-20%) should rank highest
    movers = scanner.scan_top_movers(5)
    assert len(movers) == 3
    assert movers[0]["symbol"] in ("GAIN", "LOSE")
    assert movers[1]["symbol"] in ("GAIN", "LOSE")
    assert movers[2]["symbol"] == "FLAT"

    # Volume Spikes: GAIN (50,000) > LOSE (10,000) > FLAT (2,000)
    vol_spikes = scanner.scan_volume_spikes(5)
    assert vol_spikes[0]["symbol"] == "GAIN"
    assert vol_spikes[0]["volume"] == 50000.0
    assert vol_spikes[1]["symbol"] == "LOSE"

    # Breakouts: GAIN is near Day High (120/122 = ~91% of range)
    breakouts = scanner.scan_breakouts(5)
    assert any(b["symbol"] == "GAIN" for b in breakouts)

    # Test Scanner with duplicate watchlist items (e.g. same symbol added twice)
    duplicate_watch = [
        {"tradingSymbol": "ONGC", "exchange": "NC", "scripCode": "2475"},
        {"tradingSymbol": "ONGC", "exchange": "NC", "scripCode": "2475"},
    ]
    scanner_dup = MarketScanner(store, watch=duplicate_watch)
    cands = scanner_dup._extract_candidates()
    # Deduplication ensures ONGC is only extracted once
    ongc_cands = [c for c in cands if c["symbol"] == "ONGC"]
    assert len(ongc_cands) == 1


# ── 7. Focus Range Bar & Context Panel Tests ─────────────────────────────────

def test_focus_range_bar():
    from sktui.screens.modals import render_range_bar

    # Normal range at 50%
    bar_mid = render_range_bar(low=100.0, high=200.0, current=150.0, width=20)
    assert "50.0% of range" in bar_mid.plain
    assert "L: ₹100.00" in bar_mid.plain
    assert "H: ₹200.00" in bar_mid.plain
    assert "●" in bar_mid.plain

    # Range at 100% (Day High)
    bar_high = render_range_bar(low=100.0, high=200.0, current=200.0, width=20)
    assert "100.0% of range" in bar_high.plain

    # Range at 0% (Day Low)
    bar_low = render_range_bar(low=100.0, high=200.0, current=100.0, width=20)
    assert "0.0% of range" in bar_low.plain

    # Flat range (high <= low)
    bar_flat = render_range_bar(low=100.0, high=100.0, current=100.0, width=20)
    assert "L: ₹100.00" in bar_flat.plain


# ── 8. Pre-Trade Risk Guardrails (Fat-Finger & Loss Limits) ───────────────────

def test_pretrade_fat_finger_and_loss_limit():
    from sktui.services.risk_engine import RiskEngine, RiskLimits

    limits = RiskLimits(max_daily_loss=5000.0, max_order_value=1_000_000.0)
    engine = RiskEngine(limits=limits)

    # 1. Fat-Finger Limit Buy check: price ₹150 is >10% above market LTP ₹100
    buy_order = {
        "tradingSymbol": "TEST", "exchange": "NC", "transactionType": "B",
        "quantity": 10, "price": "150.00", "productType": "INVESTMENT",
    }
    res_buy = engine.validate_order(buy_order, quote_price=100.0)
    assert any("FAT-FINGER ALERT" in w for w in res_buy.warnings)
    assert any("above market LTP" in w for w in res_buy.warnings)

    # 2. Fat-Finger Limit Sell check: price ₹80 is >10% below market LTP ₹100
    sell_order = {
        "tradingSymbol": "TEST", "exchange": "NC", "transactionType": "S",
        "quantity": 10, "price": "80.00", "productType": "INVESTMENT",
    }
    res_sell = engine.validate_order(sell_order, quote_price=100.0)
    assert any("FAT-FINGER ALERT" in w for w in res_sell.warnings)
    assert any("below market LTP" in w for w in res_sell.warnings)

    # 3. Daily Drawdown Limit Breach
    engine.update_daily_pnl(-6000.0)  # Exceeds max_daily_loss (5000)
    normal_order = {
        "tradingSymbol": "TEST", "exchange": "NC", "transactionType": "B",
        "quantity": 10, "price": "100.00", "productType": "INVESTMENT",
    }
    res_drawdown = engine.validate_order(normal_order, quote_price=100.0)
    assert not res_drawdown.allowed
    assert any("Daily drawdown limit breached" in v or "Daily loss limit" in v for v in res_drawdown.violations)


# ── 9. Historical Replay Engine Tests ─────────────────────────────────────────

def test_historical_replay_engine():
    from sktui.chart import Candle
    from sktui.services.replay_engine import ReplayEngine

    candles = [
        Candle(timestamp="1", open=100.0, high=105.0, low=98.0, close=104.0, volume=400.0),
        Candle(timestamp="2", open=104.0, high=108.0, low=103.0, close=107.0, volume=800.0),
    ]

    ticks_received: list[dict] = []
    engine = ReplayEngine(on_tick=lambda t: ticks_received.append(t))
    engine.load_candles("NIFTY", "NC", candles, scrip_code=2475)

    # 2 candles * 4 micro-ticks per candle = 8 ticks total
    assert engine.total_ticks == 8
    assert engine.current_tick_index == 0

    # Step 1 tick
    t1 = engine.step()
    assert t1 is not None
    assert t1["tradingSymbol"] == "NIFTY"
    assert t1["scripCode"] == 2475
    assert len(ticks_received) == 1
    assert engine.current_tick_index == 1

    # Run remaining ticks to end
    processed = engine.run_all()
    assert processed == 7
    assert len(ticks_received) == 8
    assert engine.current_tick_index == 8

    # Reset
    engine.reset()
    assert engine.current_tick_index == 0

