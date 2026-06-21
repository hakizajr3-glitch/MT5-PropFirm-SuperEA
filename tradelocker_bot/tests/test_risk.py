from datetime import datetime, timezone

from tradelocker_bot.config import RiskConfig
from tradelocker_bot.risk import RiskManager


def _mgr(**overrides):
    cfg = RiskConfig(**overrides)
    return RiskManager(cfg, state_path=None)


def test_daily_loss_lock():
    m = _mgr(max_daily_loss_pct=5.0, max_total_dd_pct=0.0)
    now = datetime(2026, 6, 21, 10, tzinfo=timezone.utc)
    m.on_equity_update(10000.0, now)
    status = m.check_limits(9600.0)  # -4%
    assert not status.locked
    status = m.check_limits(9500.0)  # -5%
    assert status.locked
    assert m.state.daily_locked


def test_total_drawdown_lock():
    m = _mgr(max_daily_loss_pct=0.0, max_total_dd_pct=10.0)
    now = datetime(2026, 6, 21, 10, tzinfo=timezone.utc)
    m.on_equity_update(10000.0, now)
    m.on_equity_update(12000.0, now)  # new peak
    status = m.check_limits(10900.0)  # -9.16% from peak
    assert not status.locked
    status = m.check_limits(10800.0)  # -10% from peak
    assert status.locked
    assert m.state.total_locked


def test_new_day_resets_daily_baseline():
    m = _mgr(max_daily_loss_pct=5.0)
    d1 = datetime(2026, 6, 21, 10, tzinfo=timezone.utc)
    m.on_equity_update(10000.0, d1)
    m.check_limits(9500.0)
    assert m.state.daily_locked
    d2 = datetime(2026, 6, 22, 10, tzinfo=timezone.utc)
    m.on_equity_update(9500.0, d2)
    assert not m.state.daily_locked
    assert m.state.day_start_equity == 9500.0


def test_session_filter_weekend_and_hours():
    m = _mgr(use_session=True, start_hour=7, end_hour=20)
    sat = datetime(2026, 6, 20, 10, tzinfo=timezone.utc)  # Saturday
    assert not m.in_session(sat)
    wed_in = datetime(2026, 6, 17, 10, tzinfo=timezone.utc)
    assert m.in_session(wed_in)
    wed_out = datetime(2026, 6, 17, 22, tzinfo=timezone.utc)
    assert not m.in_session(wed_out)


def test_session_disabled_always_true():
    m = _mgr(use_session=False)
    sat = datetime(2026, 6, 20, 3, tzinfo=timezone.utc)
    assert m.in_session(sat)


def test_position_size_risk_percent():
    m = _mgr(use_risk_percent=True, risk_percent=1.0)
    # balance 10000, risk 1% = $100. SL distance 0.0010, contract 100000 ->
    # loss per qty = 0.0010 * 100000 = $100 -> qty 1.0
    qty = m.position_size(balance=10000.0, sl_distance_price=0.0010,
                          money_per_price_per_qty=100000.0,
                          min_qty=0.01, max_qty=100.0, qty_step=0.01)
    assert abs(qty - 1.0) < 1e-9


def test_position_size_fixed():
    m = _mgr(use_risk_percent=False, fixed_quantity=0.25)
    qty = m.position_size(balance=10000.0, sl_distance_price=0.0010,
                          money_per_price_per_qty=100000.0,
                          min_qty=0.01, max_qty=100.0, qty_step=0.01)
    assert qty == 0.25


def test_position_size_respects_min():
    m = _mgr(use_risk_percent=True, risk_percent=0.0001)
    qty = m.position_size(balance=100.0, sl_distance_price=1.0,
                          money_per_price_per_qty=100000.0,
                          min_qty=0.01, max_qty=100.0, qty_step=0.01)
    assert qty == 0.01
