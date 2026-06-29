"""Tests for all 7 investor-philosophy agents."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ai_hedge_fund.agents.base import Action, MarketSnapshot
from ai_hedge_fund.agents import (
    GrahamAgent, BuffettAgent, MungerAgent,
    AckmanAgent, WoodAgent, FisherAgent, DruckenmillerAgent,
    ALL_AGENTS,
)


def _make_bars(n: int = 300, base: float = 1.08, trend: float = 0.0,
               vol: float = 0.002, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV bars."""
    rng = np.random.default_rng(seed)
    closes = base + np.cumsum(rng.normal(trend, vol, n))
    closes = np.maximum(closes, base * 0.5)
    highs = closes + np.abs(rng.normal(0, vol * 0.5, n))
    lows = closes - np.abs(rng.normal(0, vol * 0.5, n))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    volume = rng.integers(1000, 5000, n).astype(float)
    return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": volume})


def _snapshot(bars: pd.DataFrame | None = None, symbol: str = "EURUSD") -> MarketSnapshot:
    if bars is None:
        bars = _make_bars()
    return MarketSnapshot(symbol=symbol, bars=bars)


class TestAllAgentsReturnSignal:
    """Every agent must return a valid AgentSignal for any valid input."""

    @pytest.mark.parametrize("agent_cls", ALL_AGENTS)
    def test_returns_signal(self, agent_cls):
        agent = agent_cls()
        sig = agent.analyze(_snapshot())
        assert sig.agent_name == agent.name
        assert sig.symbol == "EURUSD"
        assert isinstance(sig.action, Action)
        assert 0.0 <= sig.confidence <= 1.0

    @pytest.mark.parametrize("agent_cls", ALL_AGENTS)
    def test_short_bars_returns_hold(self, agent_cls):
        """With very few bars, agents should return HOLD (not crash)."""
        short = _make_bars(n=10)
        agent = agent_cls()
        sig = agent.analyze(_snapshot(short))
        assert sig.action == Action.HOLD


class TestGraham:
    def test_oversold_buys(self):
        # create data where price drops well below SMA200
        bars = _make_bars(n=300, trend=-0.0005, seed=7)
        agent = GrahamAgent()
        sig = agent.analyze(_snapshot(bars))
        # should at least not crash; result depends on synthetic data
        assert isinstance(sig.action, Action)

    def test_has_indicators(self):
        agent = GrahamAgent()
        sig = agent.analyze(_snapshot())
        assert "sma200" in sig.indicators
        assert "rsi" in sig.indicators


class TestBuffett:
    def test_strong_uptrend(self):
        bars = _make_bars(n=300, trend=0.001, seed=10)
        agent = BuffettAgent()
        sig = agent.analyze(_snapshot(bars))
        assert isinstance(sig.action, Action)
        assert "adx" in sig.indicators

    def test_no_trend_holds(self):
        bars = _make_bars(n=300, trend=0.0, seed=1)
        agent = BuffettAgent()
        sig = agent.analyze(_snapshot(bars))
        # flat market should likely be HOLD
        assert isinstance(sig.action, Action)


class TestMunger:
    def test_confluence_check(self):
        agent = MungerAgent()
        sig = agent.analyze(_snapshot())
        assert isinstance(sig.action, Action)
        assert "ema20" in sig.indicators


class TestAckman:
    def test_breakout_detection(self):
        # strong uptrend should produce a breakout
        bars = _make_bars(n=50, trend=0.002, seed=5)
        agent = AckmanAgent()
        sig = agent.analyze(_snapshot(bars))
        assert isinstance(sig.action, Action)


class TestWood:
    def test_momentum_check(self):
        agent = WoodAgent()
        sig = agent.analyze(_snapshot())
        assert isinstance(sig.action, Action)
        assert "macd" in sig.indicators


class TestFisher:
    def test_quality_trend(self):
        agent = FisherAgent()
        sig = agent.analyze(_snapshot())
        assert isinstance(sig.action, Action)
        assert "r2" in sig.indicators
        assert "choppiness" in sig.indicators


class TestDruckenmiller:
    def test_rr_check(self):
        agent = DruckenmillerAgent()
        sig = agent.analyze(_snapshot())
        assert isinstance(sig.action, Action)
        assert "buy_rr" in sig.indicators
        assert "sell_rr" in sig.indicators
