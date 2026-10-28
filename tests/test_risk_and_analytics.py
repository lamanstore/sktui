"""Tests for professional workstation components:
Risk Engine, Audit Trail, Order Store, Quote Staleness, Alerts, Chart Indicators, and Portfolio Analytics.
"""
import time
from datetime import datetime
from pathlib import Path

import pytest

from sktui.chart import (
    Candle, calc_ema, calc_rsi, calc_sma, calc_vwap, render_candlestick_chart,
)
from sktui.services.alert_engine import AlertEngine
from sktui.services.audit import AuditTrail
from sktui.services.portfolio_analytics import PortfolioAnalytics
from sktui.services.risk_engine import RiskEngine, RiskLimits
from sktui.state.order_store import OrderStatus, OrderStore
from sktui.state.quote_store import QuoteStore


# ── Risk Engine Tests ─────────────────────────────────────────────────────────

def test_risk_order_qty_and_value_caps():
    limits = RiskLimits(max_order_qty=1000, max_order_value=100_000.0)
    engine = RiskEngine(limits)

    # Valid order
    res = engine.validate_order({"tradingSymbol": "TCS", "quantity": 10, "price": "3500.00"})
    assert res.allowed is True
    assert not res.violations

    # Exceed quantity
    res_qty = engine.validate_order({"tradingSymbol": "TCS", "quantity": 1500, "price": "50.00"})
    assert res_qty.allowed is False
    assert any("quantity" in v.lower() for v in res_qty.violations)

    # Exceed value
    res_val = engine.validate_order({"tradingSymbol": "TCS", "quantity": 100, "price": "1500.00"})
    assert res_val.allowed is False
    assert any("order value" in v.lower() for v in res_val.violations)


def test_risk_drawdown_lockout():
    limits = RiskLimits(max_daily_loss=10_000.0)
    engine = RiskEngine(limits)

    # Acceptable loss
    engine.update_daily_pnl(-5000.0)
    res = engine.validate_order({"tradingSymbol": "INFY", "quantity": 10, "price": "1500.00"})
    assert res.allowed is True

    # Breach max daily loss
    engine.update_daily_pnl(-12000.0)
    res_blocked = engine.validate_order({"tradingSymbol": "INFY", "quantity": 10, "price": "1500.00"})
    assert res_blocked.allowed is False
    assert any("lockout active" in v.lower() for v in res_blocked.violations)

    # Manual reset
    engine.reset_lockout()
    res_reset = engine.validate_order({"tradingSymbol": "INFY", "quantity": 10, "price": "1500.00"})
    assert res_reset.allowed is True


def test_risk_rate_limiting():
    limits = RiskLimits(max_orders_per_minute=3)
    engine = RiskEngine(limits)

    for _ in range(3):
        engine.record_order_submission()

    res = engine.validate_order({"tradingSymbol": "SBIN", "quantity": 1, "price": "800.00"})
    assert res.allowed is False
    assert any("rate limit" in v.lower() for v in res.violations)


# ── Audit Trail Tests ─────────────────────────────────────────────────────────

def test_audit_trail_logging(tmp_path: Path):
    audit = AuditTrail(audit_dir=tmp_path)
    ev = audit.record(
        event_type="ORDER_SUBMITTED",
        symbol="RELIANCE",
        side="B",
        quantity=50,
        price=2900.0,
        order_id="ORD-101",
        status="SUBMITTED",
    )
    assert ev.order_id == "ORD-101"
    recent = audit.recent_events(limit=10)
    assert len(recent) == 1
    assert recent[0].symbol == "RELIANCE"
    assert (tmp_path / "audit.jsonl").exists()


# ── Order Store Tests ─────────────────────────────────────────────────────────

def test_order_store_lifecycle():
    store = OrderStore()
    order = store.record_intent({
        "orderId": "12345",
        "tradingSymbol": "HDFCBANK",
        "transactionType": "B",
        "quantity": 100,
        "price": "1650.00",
    })
    assert order.status == OrderStatus.PENDING_SUBMIT
    assert order.is_active is True

    # Update to open
    store.update_from_feed({"orderId": "12345", "orderStatus": "Open", "tradingSymbol": "HDFCBANK"})
    assert store.get_order("12345").status == OrderStatus.OPEN

    # Update to filled
    store.update_from_feed({
        "orderId": "12345",
        "orderStatus": "Fully Executed",
        "tradingSymbol": "HDFCBANK",
        "execQty": 100,
        "execPrice": "1649.50",
    })
    updated = store.get_order("12345")
    assert updated.status == OrderStatus.FILLED
    assert updated.is_filled is True
    assert updated.average_price == 1649.50
    assert not store.active_orders()


# ── Quote Store Staleness & Health Tests ──────────────────────────────────────

def test_quote_store_staleness_and_health():
    quotes = QuoteStore()
    quotes.update("NC2475", {"ltp": 100.0})

    status, color = quotes.staleness_status("NC2475")
    assert status == "FRESH"
    assert color == "#00ff87"

    # Simulate age > 3 seconds
    quotes.tick_timestamps["NC2475"] = time.monotonic() - 5.0
    status_warm, _ = quotes.staleness_status("NC2475")
    assert status_warm == "WARM"

    # Simulate age > 12 seconds
    quotes.tick_timestamps["NC2475"] = time.monotonic() - 15.0
    status_stale, _ = quotes.staleness_status("NC2475")
    assert "STALE" in status_stale

    badge_text, _ = quotes.feed_badge()
    assert "STALE" in badge_text

    # Fresh tick arrives
    quotes.update("NC2475", {"ltp": 105.0})
    fresh_badge, _ = quotes.feed_badge()
    assert "LIVE" in fresh_badge


def test_order_reject_code_classification():
    from sktui.state.order_store import OrderRejectCode, parse_reject_code, OrderStore, OrderStatus

    assert parse_reject_code("Insufficient margin for order") == OrderRejectCode.RMS_INSUFFICIENT_MARGIN
    assert parse_reject_code("Price outside circuit limit") == OrderRejectCode.RMS_CIRCUIT_LIMIT
    assert parse_reject_code("Quantity exceeds max order limit") == OrderRejectCode.RMS_MAX_QTY_EXCEEDED
    assert parse_reject_code("Daily drawdown limit breached") == OrderRejectCode.RMS_DRAWDOWN_LOCKOUT
    assert parse_reject_code("Mandatory Stop Loss required for F&O") == OrderRejectCode.RMS_DERIVATIVE_NO_SL
    assert parse_reject_code("Rate limit exceeded") == OrderRejectCode.RMS_RATE_LIMIT_EXCEEDED
    assert parse_reject_code("Market is closed") == OrderRejectCode.MARKET_CLOSED

    store = OrderStore()
    order = store.update_from_feed({
        "orderId": "ORD-99",
        "tradingSymbol": "NIFTY24OCTFUT",
        "orderStatus": "REJECTED",
        "errorMsg": "RMS: Margin shortfall of Rs. 45000",
    })
    assert order.status == OrderStatus.REJECTED
    assert order.reject_code == OrderRejectCode.RMS_INSUFFICIENT_MARGIN


# ── Alert Engine Tests ────────────────────────────────────────────────────────

def test_alert_engine_price_triggers():
    engine = AlertEngine()
    engine.add_alert("TCS", "ABOVE", 3600.0)
    engine.add_alert("TCS", "BELOW", 3400.0)

    # Within bounds -> no trigger
    assert not engine.evaluate_quote("TCS", 3500.0)

    # Cross above -> trigger
    fired = engine.evaluate_quote("TCS", 3605.0)
    assert len(fired) == 1
    assert fired[0].condition == "ABOVE"

    # Already triggered, non-repeat -> should not fire again
    assert not engine.evaluate_quote("TCS", 3610.0)


def test_alert_command_parser_and_persistence(tmp_path):
    from sktui.services.alert_engine import parse_alert_command

    assert parse_alert_command("/alert RELIANCE > 3000") == ("RELIANCE", "ABOVE", 3000.0)
    assert parse_alert_command("alert INFY < 1400.50") == ("INFY", "BELOW", 1400.50)
    assert parse_alert_command("/alert TCS RSI > 70") == ("TCS", "RSI_OB", 70.0)
    assert parse_alert_command("/alert TCS RSI < 30") == ("TCS", "RSI_OS", 30.0)
    assert parse_alert_command("/alert ONGC VOL > 2.5") == ("ONGC", "VOL_SPIKE", 2.5)
    assert parse_alert_command("INVALID COMMAND") is None

    # Test JSON file persistence
    alert_file = tmp_path / "alerts.json"
    engine1 = AlertEngine(alert_file)
    engine1.add_alert("TCS", "ABOVE", 3600.0)
    engine1.add_alert("INFY", "BELOW", 1400.0)

    # Re-open from disk
    engine2 = AlertEngine(alert_file)
    assert len(engine2.alerts) == 2
    assert engine2.alerts[0].symbol == "TCS"
    assert engine2.alerts[1].symbol == "INFY"


# ── Portfolio Analytics Tests ─────────────────────────────────────────────────

def test_portfolio_analytics():
    positions = [
        {"tradingSymbol": "HDFCBANK", "exchange": "NC", "scripCode": 101, "netQty": 10, "avgPrice": 1600.0, "bpl": 500.0},
        {"tradingSymbol": "TCS", "exchange": "NC", "scripCode": 102, "netQty": -5, "avgPrice": 3500.0, "bpl": -200.0},
    ]
    ticks = {
        "NC101": {"ltp": 1650.0},
        "NC102": {"ltp": 3480.0},
    }
    summary = PortfolioAnalytics.analyze(positions, ticks)
    assert summary.realized_pnl == 300.0
    assert summary.unrealized_pnl == (10 * 50.0) + (-5 * -20.0) # 500 + 100 = 600
    assert summary.total_pnl == 900.0
    assert "Banking" in summary.sector_breakdown
    assert "IT" in summary.sector_breakdown


# ── Candlestick & Technical Indicator Tests ───────────────────────────────────

def test_chart_indicators_and_candlesticks():
    prices = [100.0 + i for i in range(30)]
    sma5 = calc_sma(prices, 5)
    assert sma5[4] == sum(prices[:5]) / 5.0
    assert sma5[0] is None

    ema9 = calc_ema(prices, 9)
    assert ema9[8] is not None
    assert ema9[0] is None

    rsi = calc_rsi(prices, 14)
    assert rsi[14] is not None
    assert rsi[14] == 100.0 # pure upward trend

    candles = [
        Candle(timestamp="1", open=100.0, high=105.0, low=98.0, close=104.0, volume=1000.0),
        Candle(timestamp="2", open=104.0, high=106.0, low=101.0, close=102.0, volume=1500.0),
    ]
    vwap = calc_vwap(candles)
    assert len(vwap) == 2
    assert vwap[0] is not None

    # Test candle renderer output
    rendered = render_candlestick_chart(candles, width=40, height=8, symbol="TEST")
    assert rendered is not None
    assert "TEST" in rendered.plain


def test_csv_export_format(tmp_path):
    out_file = tmp_path / "test_session.csv"
    positions = [
        {"tradingSymbol": "RELIANCE", "exchange": "NC", "productType": "INVESTMENT", "netQty": 20, "avgPrice": 2800.0, "bpl": 1000.0, "mtm": 400.0}
    ]
    orders = [
        {"orderId": "1001", "tradingSymbol": "RELIANCE", "exchange": "NC", "buySell": "B", "orderQty": 20, "execQty": 20, "orderPrice": 2800.0, "execPrice": 2800.0, "orderStatus": "FILLED", "errorMsg": ""}
    ]
    ticks = {"NC1001": {"ltp": 2820.0}}
    summary = PortfolioAnalytics.analyze(positions, ticks)

    with open(out_file, "w", encoding="utf-8") as f:
        f.write("# SKTUI SESSION REPORT\n")
        f.write(f"{summary.realized_pnl:.2f},{summary.unrealized_pnl:.2f},{summary.total_pnl:.2f}\n")
        f.write("Symbol,Exchange,NetQty,BookedPnL\n")
        for p in positions:
            f.write(f"{p['tradingSymbol']},{p['exchange']},{p['netQty']},{p['bpl']}\n")

    content = out_file.read_text(encoding="utf-8")
    assert "RELIANCE,NC,20,1000.0" in content
    assert "# SKTUI SESSION REPORT" in content
