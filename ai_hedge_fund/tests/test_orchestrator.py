"""Tests for the Orchestrator pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ai_hedge_fund.agents.base import Action, MarketSnapshot
from ai_hedge_fund.orchestrator import Orchestrator
from ai_hedge_fund.risk_manager import RiskLimits


def _make_bars(n: int = 300, base: float = 1.08, trend: float = 0.0,
               vol: float = 0.002, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = base + np.cumsum(rng.normal(trend, vol, n))
    closes = np.maximum(closes, base * 0.5)
    highs = closes + np.abs(rng.normal(0, vol * 0.5, n))
    lows = closes - np.abs(rng.normal(0, vol * 0.5, n))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    volume = rng.integers(1000, 5000, n).astype(float)
    return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": volume})


class TestOrchestrator:
    def test_run_symbol(self):
        orch = Orchestrator()
        snap = MarketSnapshot(symbol="EURUSD", bars=_make_bars())
        result = orch.run_symbol(
            snapshot=snap, equity=1000, balance=1000,
            day_start_equity=1000, peak_equity=1000,
        )
        assert result.symbol == "EURUSD"
        assert len(result.agent_signals) == 7
        assert result.risk_verdict is not None
        assert result.portfolio_decision is not None

    def test_run_cycle_multiple_symbols(self):
        orch = Orchestrator()
        snaps = [
            MarketSnapshot(symbol="EURUSD", bars=_make_bars(seed=1)),
            MarketSnapshot(symbol="GBPUSD", bars=_make_bars(seed=2, base=1.27)),
        ]
        report = orch.run_cycle(
            snapshots=snaps, equity=1000, balance=1000,
            day_start_equity=1000, peak_equity=1000,
        )
        assert len(report.results) == 2
        assert report.results[0].symbol == "EURUSD"
        assert report.results[1].symbol == "GBPUSD"

    def test_as_dict_serializable(self):
        orch = Orchestrator()
        snap = MarketSnapshot(symbol="XAUUSD", bars=_make_bars(base=2350, vol=18, seed=7))
        result = orch.run_symbol(
            snapshot=snap, equity=1000, balance=1000,
            day_start_equity=1000, peak_equity=1000,
        )
        d = result.as_dict()
        assert d["symbol"] == "XAUUSD"
        assert len(d["agent_signals"]) == 7
        assert "risk_verdict" in d
        assert "portfolio_decision" in d

    def test_risk_limits_propagate(self):
        limits = RiskLimits(max_open_positions=0)  # block everything
        orch = Orchestrator(risk_limits=limits)
        snap = MarketSnapshot(symbol="EURUSD", bars=_make_bars())
        result = orch.run_symbol(
            snapshot=snap, equity=1000, balance=1000,
            day_start_equity=1000, peak_equity=1000,
        )
        assert not result.risk_verdict.approved
        assert result.order is None
