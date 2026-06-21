import time

from dashboard.engine import TradeEngine
from dashboard.providers import DemoProvider
from dashboard.state import DashboardConfig, build_state


def test_engine_start_stop_demo(monkeypatch):
    monkeypatch.delenv("SHROUD_LIVE", raising=False)
    monkeypatch.setenv("TL_POLL_SECONDS", "1")
    eng = TradeEngine()

    assert eng.status()["running"] is False

    s = eng.start()
    assert s["running"] is True
    assert s["mode"] == "DEMO"

    # let the demo loop run at least one cycle
    for _ in range(20):
        if eng.status()["cycles"] >= 1:
            break
        time.sleep(0.1)
    assert eng.status()["cycles"] >= 1

    s = eng.stop()
    assert s["running"] is False
    # thread must actually be gone
    assert eng._thread is None


def test_engine_start_is_idempotent(monkeypatch):
    monkeypatch.delenv("SHROUD_LIVE", raising=False)
    eng = TradeEngine()
    a = eng.start()
    b = eng.start()  # second start should not spawn a second thread
    try:
        assert a["running"] and b["running"]
        assert b["started_at"] == a["started_at"]
    finally:
        eng.stop()


def test_state_reflects_engine_running():
    prov = DemoProvider(symbols=["EURUSD"])
    cfg = DashboardConfig(mode="LIVE")
    running = build_state(prov, cfg, engine={"running": True, "mode": "DEMO",
                                             "cycles": 3, "last_action": "scan"})
    stopped = build_state(prov, cfg, engine={"running": False, "mode": "DEMO",
                                             "cycles": 0, "last_action": "idle"})
    exec_running = next(a for a in running["agents"] if a["name"] == "Execution Agent")
    exec_stopped = next(a for a in stopped["agents"] if a["name"] == "Execution Agent")
    assert exec_running["status"] == "RUNNING"
    assert exec_stopped["status"] == "WAITING"
    assert running["engine"]["running"] is True


def test_safe_mode_overrides_engine_running():
    prov = DemoProvider(symbols=["EURUSD"])
    # tiny daily limit -> breach -> SAFE MODE even though engine is running
    cfg = DashboardConfig(daily_loss_limit_pct=0.1, mode="LIVE")
    state = build_state(prov, cfg, engine={"running": True, "mode": "DEMO"})
    assert state["system_status"] == "SAFE MODE"
    exec_agent = next(a for a in state["agents"] if a["name"] == "Execution Agent")
    assert exec_agent["status"] == "WAITING"
