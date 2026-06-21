import json

from dashboard.providers import DemoProvider
from dashboard.state import DashboardConfig, build_state


def test_build_state_demo_is_json_serialisable():
    prov = DemoProvider(symbols=["EURUSD", "XAUUSD"])
    cfg = DashboardConfig()
    state = build_state(prov, cfg)
    # must serialise cleanly (no NaN/inf leaking through)
    json.dumps(state)
    assert state["system_status"] in ("DRY RUN", "LIVE", "SAFE MODE", "HALTED")
    assert "account" in state and "performance" in state
    assert len(state["market"]) == 2
    names = [a["name"] for a in state["agents"]]
    assert "Risk Agent" in names and "Execution Agent" in names


def test_safe_mode_triggers_on_breach():
    prov = DemoProvider(symbols=["EURUSD"])
    cfg = DashboardConfig(daily_loss_limit_pct=0.1, mode="LIVE")  # tiny limit -> breach
    state = build_state(prov, cfg)
    assert state["system_status"] == "SAFE MODE"
    assert state["risk"]["safe_mode"] is True


def test_news_and_reflection_offline_by_default():
    prov = DemoProvider(symbols=["EURUSD"])
    state = build_state(prov, DashboardConfig())
    statuses = {a["name"]: a["status"] for a in state["agents"]}
    assert statuses["News Agent"] == "OFFLINE"
    assert statuses["Reflection Agent"] == "OFFLINE"


def test_market_scanner_running_with_data():
    prov = DemoProvider(symbols=["EURUSD", "GBPUSD"])
    state = build_state(prov, DashboardConfig())
    statuses = {a["name"]: a["status"] for a in state["agents"]}
    assert statuses["Market Scanner"] == "RUNNING"
