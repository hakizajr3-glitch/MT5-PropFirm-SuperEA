"""Tests for the Risk Manager."""

from __future__ import annotations

import pytest

from ai_hedge_fund.agents.base import Action, AgentSignal
from ai_hedge_fund.risk_manager import RiskLimits, RiskManagerAgent


def _signal(name: str, action: Action, confidence: float, weight: float = 1.0) -> AgentSignal:
    return AgentSignal(
        agent_name=name, symbol="EURUSD", action=action,
        confidence=confidence, reasoning="test", weight=weight,
    )


class TestRiskManager:
    def test_consensus_buy(self):
        rm = RiskManagerAgent(RiskLimits(min_agents_agree=3, min_consensus_confidence=0.3))
        signals = [
            _signal("A", Action.BUY, 0.8),
            _signal("B", Action.BUY, 0.7),
            _signal("C", Action.BUY, 0.6),
            _signal("D", Action.HOLD, 0.0),
            _signal("E", Action.SELL, 0.3),
        ]
        v = rm.evaluate("EURUSD", signals, equity=1000, day_start_equity=1000,
                        peak_equity=1000, current_daily_pnl=0,
                        open_position_count=0, open_risk_pct=0)
        assert v.approved
        assert v.direction == Action.BUY
        assert v.consensus_confidence > 0
        assert v.risk_pct > 0

    def test_consensus_sell(self):
        rm = RiskManagerAgent(RiskLimits(min_agents_agree=3, min_consensus_confidence=0.3))
        signals = [
            _signal("A", Action.SELL, 0.9),
            _signal("B", Action.SELL, 0.8),
            _signal("C", Action.SELL, 0.7),
            _signal("D", Action.HOLD, 0.0),
        ]
        v = rm.evaluate("EURUSD", signals, equity=1000, day_start_equity=1000,
                        peak_equity=1000, current_daily_pnl=0,
                        open_position_count=0, open_risk_pct=0)
        assert v.approved
        assert v.direction == Action.SELL

    def test_blocks_when_daily_loss_exceeded(self):
        rm = RiskManagerAgent(RiskLimits(max_daily_loss_pct=5.0, min_agents_agree=1,
                                         min_consensus_confidence=0.1))
        signals = [_signal("A", Action.BUY, 0.9)]
        v = rm.evaluate("EURUSD", signals, equity=940, day_start_equity=1000,
                        peak_equity=1000, current_daily_pnl=-60,
                        open_position_count=0, open_risk_pct=0)
        assert not v.approved
        assert any("Daily loss" in r for r in v.blocked_reasons)

    def test_blocks_when_max_dd_exceeded(self):
        rm = RiskManagerAgent(RiskLimits(max_total_dd_pct=10.0, min_agents_agree=1,
                                         min_consensus_confidence=0.1))
        signals = [_signal("A", Action.BUY, 0.9)]
        v = rm.evaluate("EURUSD", signals, equity=880, day_start_equity=1000,
                        peak_equity=1000, current_daily_pnl=0,
                        open_position_count=0, open_risk_pct=0)
        assert not v.approved
        assert any("Total DD" in r for r in v.blocked_reasons)

    def test_blocks_max_positions(self):
        rm = RiskManagerAgent(RiskLimits(max_open_positions=2, min_agents_agree=1,
                                         min_consensus_confidence=0.1))
        signals = [_signal("A", Action.BUY, 0.9)]
        v = rm.evaluate("EURUSD", signals, equity=1000, day_start_equity=1000,
                        peak_equity=1000, current_daily_pnl=0,
                        open_position_count=2, open_risk_pct=0)
        assert not v.approved

    def test_blocks_low_confidence(self):
        rm = RiskManagerAgent(RiskLimits(min_consensus_confidence=0.5, min_agents_agree=1))
        signals = [_signal("A", Action.BUY, 0.2)]
        v = rm.evaluate("EURUSD", signals, equity=1000, day_start_equity=1000,
                        peak_equity=1000, current_daily_pnl=0,
                        open_position_count=0, open_risk_pct=0)
        assert not v.approved

    def test_no_direction_blocks(self):
        rm = RiskManagerAgent()
        signals = [
            _signal("A", Action.HOLD, 0.0),
            _signal("B", Action.HOLD, 0.0),
        ]
        v = rm.evaluate("EURUSD", signals, equity=1000, day_start_equity=1000,
                        peak_equity=1000, current_daily_pnl=0,
                        open_position_count=0, open_risk_pct=0)
        assert not v.approved
        assert v.direction == Action.HOLD

    def test_risk_scaling(self):
        rm = RiskManagerAgent(RiskLimits(max_risk_per_trade_pct=1.0,
                                         min_agents_agree=1, min_consensus_confidence=0.3))
        signals = [_signal("A", Action.BUY, 0.9, weight=1.0)]
        v = rm.evaluate("EURUSD", signals, equity=1000, day_start_equity=1000,
                        peak_equity=1000, current_daily_pnl=0,
                        open_position_count=0, open_risk_pct=0)
        assert v.approved
        assert 0 < v.risk_pct <= 1.0
