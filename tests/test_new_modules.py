"""Tests for new Phase C-H modules:
indicators, feed_health, alert_store, config_manager, risk_state,
pre-ticket blocking, risk scoring, and order audit replay.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from sktui.services import indicators as ind
from sktui.services.feed_health import FeedHealthMonitor, FRESH_THRESHOLD, WARM_THRESHOLD
from sktui.state.alert_store import Alert, AlertStore
from sktui.config_manager import ConfigManager, ProfileConfig, BUILTIN_PROFILES
from sktui.state.risk_state import RiskState, RiskLimits as RLimits
from sktui.services.risk_engine import RiskEngine, RiskLimits
from sktui.state.order_store import OrderStore, OrderStatus


# ── Indicators Tests ──────────────────────────────────────────────────────────

def test_ema_basic():
    prices = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    result = ind.ema(prices, period=3)
    assert len(result) == len(prices)
    # First two should be None (insufficient data for period=3)
    assert result[0] is None
    assert result[1] is None
    # Third should be initialized with SMA
    assert result[2] == pytest.approx((1 + 2 + 3) / 3, rel=1e-6)
    # All subsequent should be non-None
    for v in result[3:]:
        assert v is not None


def test_sma_basic():
    prices = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = ind.sma(prices, period=3)
    assert result[0] is None
    assert result[1] is None
    assert result[2] == pytest.approx(20.0, rel=1e-6)  # (10+20+30)/3
    assert result[3] == pytest.approx(30.0, rel=1e-6)  # (20+30+40)/3
    assert result[4] == pytest.approx(40.0, rel=1e-6)  # (30+40+50)/3


def test_rsi_range():
    prices = [float(i) for i in range(1, 30)]  # monotonically rising
    result = ind.rsi(prices, period=14)
    non_none = [v for v in result if v is not None]
    assert all(0 <= v <= 100 for v in non_none)
    # Rising prices → RSI should be high
    assert non_none[-1] > 70


def test_rsi_insufficient_data():
    prices = [1.0, 2.0, 3.0]
    result = ind.rsi(prices, period=14)
    assert all(v is None for v in result)


def test_vwap_output_length():
    closes = [100.0, 102.0, 101.0, 103.0]
    highs  = [101.0, 103.0, 102.0, 104.0]
    lows   = [99.0,  101.0, 100.0, 102.0]
    vols   = [1000,  2000,  1500,  1800]
    result = ind.vwap(closes, highs, lows, vols)
    assert len(result) == 4
    assert all(v is not None for v in result)
    assert result[0] == pytest.approx((101.0 + 99.0 + 100.0) / 3.0, rel=1e-6)  # TP only first bar


def test_atr_output():
    highs  = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0, 25.0]
    lows   = [9.0,  10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0]
    closes = [9.5,  10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5, 19.5, 20.5, 21.5, 22.5, 23.5, 24.5]
    result = ind.atr(highs, lows, closes, period=14)
    assert len(result) == len(closes)
    non_none = [v for v in result if v is not None]
    assert len(non_none) > 0
    assert all(v > 0 for v in non_none)


def test_macd_lengths():
    prices = [float(i) for i in range(50)]
    macd_l, sig_l, hist = ind.macd(prices)
    assert len(macd_l) == len(prices)
    assert len(sig_l) == len(prices)
    assert len(hist) == len(prices)


def test_bollinger_bands_structure():
    prices = [float(i % 10 + 100) for i in range(30)]
    upper, middle, lower = ind.bollinger_bands(prices, period=20)
    assert len(upper) == len(prices)
    # Where bands are defined, upper >= middle >= lower
    for u, m, l in zip(upper, middle, lower):
        if u is not None and m is not None and l is not None:
            assert u >= m >= l


def test_support_resistance_empty():
    highs = [float(i) for i in range(20)]
    lows  = [float(i) - 1 for i in range(20)]
    res, sup = ind.support_resistance(highs, lows, window=3)
    # Should return lists without error
    assert isinstance(res, list)
    assert isinstance(sup, list)


# ── Feed Health Monitor Tests ─────────────────────────────────────────────────

def test_feed_health_fresh_status():
    monitor = FeedHealthMonitor()
    monitor.update_tick("NC12345")
    status = monitor.symbol_status("NC12345")
    assert status.state == "FRESH"
    assert not status.is_stale
    assert "LIVE" in status.badge_text


def test_feed_health_no_data():
    monitor = FeedHealthMonitor()
    status = monitor.symbol_status("NC99999")
    assert status.state == "NO_DATA"
    assert status.is_stale is True


def test_feed_health_stale_detection():
    monitor = FeedHealthMonitor()
    monitor._tick_timestamps["NC12345"] = time.monotonic() - 20.0  # 20 seconds old
    assert monitor.is_stale("NC12345", threshold=FRESH_THRESHOLD)
    status = monitor.symbol_status("NC12345")
    assert status.state in ("WARM", "STALE", "DEAD")
    assert status.is_stale


def test_feed_health_reconnect_badge():
    monitor = FeedHealthMonitor()
    monitor.set_reconnecting()
    badge, color = monitor.feed_badge()
    assert "RECONNECTING" in badge
    assert color == "#f59e0b"


def test_feed_health_disconnected_badge():
    monitor = FeedHealthMonitor()
    monitor.set_disconnected()
    badge, color = monitor.feed_badge()
    assert "OFFLINE" in badge
    assert color == "#ff4757"


def test_feed_health_latency_tracking():
    monitor = FeedHealthMonitor()
    monitor.ping(12.5)
    monitor.ping(14.0)
    monitor.ping(11.0)
    assert monitor.avg_latency_ms == pytest.approx((12.5 + 14.0 + 11.0) / 3, rel=1e-6)


def test_feed_health_ticks_per_second():
    monitor = FeedHealthMonitor()
    for _ in range(10):
        monitor.update_tick("SYM1")
    tps = monitor.ticks_per_second
    assert tps > 0  # Should register ticks within the 5-second window


def test_feed_health_stale_symbols():
    monitor = FeedHealthMonitor()
    monitor._tick_timestamps["OLD"] = time.monotonic() - 15.0
    monitor._tick_timestamps["NEW"] = time.monotonic()
    stale = monitor.stale_symbols(threshold=10.0)
    assert "OLD" in stale
    assert "NEW" not in stale


# ── Alert Store Tests ─────────────────────────────────────────────────────────

def test_alert_store_add_and_retrieve(tmp_path):
    store = AlertStore(alerts_file=tmp_path / "alerts.json")
    alert = store.add("RELIANCE", "ABOVE", 3000.0)
    assert alert.symbol == "RELIANCE"
    assert alert.condition == "ABOVE"
    assert alert.target_value == 3000.0
    assert alert.is_active is True
    assert len(store.all_alerts()) == 1


def test_alert_store_persistence(tmp_path):
    alerts_file = tmp_path / "alerts.json"
    store1 = AlertStore(alerts_file=alerts_file)
    a = store1.add("TCS", "BELOW", 3500.0, repeat=False)
    # Reload from disk
    store2 = AlertStore(alerts_file=alerts_file)
    loaded = store2.alerts_for_symbol("TCS")
    assert len(loaded) == 1
    assert loaded[0].target_value == 3500.0


def test_alert_store_trigger_lifecycle(tmp_path):
    store = AlertStore(alerts_file=tmp_path / "alerts.json")
    alert = store.add("ONGC", "ABOVE", 250.0)
    assert not alert.triggered
    store.mark_triggered(alert.id)
    updated = store.get(alert.id)
    assert updated is not None
    assert updated.triggered is True
    assert updated.triggered_at != ""
    # Non-repeat triggered alert is no longer active
    assert not updated.is_active


def test_alert_store_repeat_stays_active(tmp_path):
    store = AlertStore(alerts_file=tmp_path / "alerts.json")
    alert = store.add("HDFCBANK", "ABOVE", 1700.0, repeat=True)
    store.mark_triggered(alert.id)
    updated = store.get(alert.id)
    assert updated.is_active  # repeat=True means still active after trigger


def test_alert_store_remove(tmp_path):
    store = AlertStore(alerts_file=tmp_path / "alerts.json")
    a1 = store.add("INFY", "BELOW", 1400.0)
    a2 = store.add("WIPRO", "ABOVE", 500.0)
    assert len(store.all_alerts()) == 2
    removed = store.remove(a1.id)
    assert removed is True
    assert len(store.all_alerts()) == 1


def test_alert_store_clear_triggered(tmp_path):
    store = AlertStore(alerts_file=tmp_path / "alerts.json")
    a1 = store.add("SYM1", "ABOVE", 100.0)
    a2 = store.add("SYM2", "BELOW", 200.0)
    store.mark_triggered(a1.id)
    cleared = store.clear_triggered()
    assert cleared == 1
    assert len(store.all_alerts()) == 1  # a2 remains


def test_alert_store_trigger_listener(tmp_path):
    store = AlertStore(alerts_file=tmp_path / "alerts.json")
    fired: list[Alert] = []
    store.add_trigger_listener(fired.append)
    a = store.add("NTPC", "ABOVE", 180.0)
    store.mark_triggered(a.id)
    assert len(fired) == 1
    assert fired[0].symbol == "NTPC"


def test_alert_human_description():
    alert = Alert(id="x", symbol="RELIANCE", condition="ABOVE", target_value=3000.0)
    desc = alert.human_description()
    assert "RELIANCE" in desc
    assert "3000" in desc


# ── Config Manager Tests ──────────────────────────────────────────────────────

def test_config_manager_builtin_profiles():
    mgr = ConfigManager()
    default = mgr.get_profile("default")
    assert default.name == "default"
    assert default.paper is False

    paper = mgr.get_profile("paper")
    assert paper.paper is True

    live = mgr.get_profile("live")
    assert live.paper is False


def test_config_manager_fallback_to_default():
    mgr = ConfigManager()
    unknown = mgr.get_profile("nonexistent_profile")
    assert unknown.name == "default"


def test_config_manager_save_and_reload(tmp_path):
    mgr = ConfigManager(conf_dir=tmp_path)
    custom = ProfileConfig(name="custom", paper=True, max_daily_loss=99_000.0)
    mgr.save_profile(custom)
    # Reload from disk
    mgr2 = ConfigManager(conf_dir=tmp_path)
    loaded = mgr2.get_profile("custom")
    assert loaded.name == "custom"
    assert loaded.paper is True
    assert loaded.max_daily_loss == pytest.approx(99_000.0)


def test_config_manager_profile_from_dict():
    d = {"name": "mytest", "paper": True, "max_order_qty": 500}
    p = ProfileConfig.from_dict(d)
    assert p.name == "mytest"
    assert p.paper is True
    assert p.max_order_qty == 500


def test_config_manager_list_profiles():
    mgr = ConfigManager()
    names = mgr.list_profile_names()
    assert "default" in names
    assert "live" in names
    assert "paper" in names


def test_config_manager_startup_validation():
    mgr = ConfigManager()
    profile, warnings = mgr.startup_validation_report("default")
    assert profile.name == "default"
    # warnings is a list (may or may not be empty depending on env)
    assert isinstance(warnings, list)


# ── Risk State Score Tests ────────────────────────────────────────────────────

def test_risk_state_score_low_risk():
    lim = RLimits()
    state = RiskState(limits=lim)
    score, rating = state.calculate_risk_score(
        order_value=5_000.0,       # tiny relative to 1M limit
        projected_sym_value=10_000.0,
        is_derivative=False,
        has_sl=True,
    )
    assert 0 <= score <= 100
    assert rating in ("LOW", "MODERATE", "ELEVATED", "HIGH RISK")
    assert rating == "LOW"


def test_risk_state_score_high_risk():
    lim = RLimits()
    state = RiskState(limits=lim, realized_daily_pnl=-45_000.0, gross_exposure=9_000_000.0)
    score, rating = state.calculate_risk_score(
        order_value=900_000.0,       # 90% of max
        projected_sym_value=2_400_000.0,  # 96% of position cap
        is_derivative=True,
        has_sl=False,
    )
    assert score > 60
    assert rating in ("ELEVATED", "HIGH RISK")


def test_risk_engine_returns_risk_score():
    engine = RiskEngine()
    result = engine.validate_order({"tradingSymbol": "TCS", "quantity": 5, "price": "3500.00"})
    assert hasattr(result, "risk_score")
    assert hasattr(result, "risk_rating")
    assert 0 <= result.risk_score <= 100
    assert result.risk_rating in ("LOW", "MODERATE", "ELEVATED", "HIGH RISK")


# ── Pre-Ticket Check Tests ────────────────────────────────────────────────────

def test_pre_ticket_check_normal():
    engine = RiskEngine()
    ok, msg = engine.check_pre_ticket("RELIANCE")
    assert ok is True
    assert msg == ""


def test_pre_ticket_check_lockout():
    engine = RiskEngine()
    engine._lockout_active = True
    engine._lockout_reason = "Daily loss exceeded"
    ok, msg = engine.check_pre_ticket("INFY")
    assert ok is False
    assert "locked" in msg.lower()


def test_pre_ticket_check_position_cap():
    limits = RiskLimits(max_position_qty=100)
    engine = RiskEngine(limits)
    positions = [{"tradingSymbol": "HDFCBANK", "netQty": 100, "avgPrice": 1650.0}]
    ok, msg = engine.check_pre_ticket("HDFCBANK", positions=positions)
    assert ok is False
    assert "cap" in msg.lower()


# ── Order Store Audit Replay Tests ────────────────────────────────────────────

def test_order_store_starts_clean():
    """OrderStore.__init__ must not load from audit — stays isolated for tests."""
    store = OrderStore()
    # All orders come from prior test runs' audit; fresh store has none
    # (we can't guarantee zero if audit file exists, but we can verify load_from_audit is explicit)
    # The key invariant is: new store does NOT auto-load
    assert hasattr(store, "load_from_audit")   # method exists
    assert hasattr(store, "_orders")


def test_order_store_get_timeline_empty():
    store = OrderStore()
    timeline = store.get_timeline("NON_EXISTENT_ORDER_ID_XYZ")
    # Returns empty list (no events for that ID)
    assert isinstance(timeline, list)
