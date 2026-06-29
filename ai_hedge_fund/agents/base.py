"""Base agent and shared signal types for the AI Hedge Fund."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pandas as pd


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    SHORT = "SHORT"
    COVER = "COVER"
    HOLD = "HOLD"


@dataclass
class AgentSignal:
    """A single agent's recommendation for a symbol."""
    agent_name: str
    symbol: str
    action: Action
    confidence: float          # 0.0 .. 1.0
    reasoning: str
    indicators: dict = field(default_factory=dict)
    weight: float = 1.0        # relative vote weight


@dataclass
class MarketSnapshot:
    """Everything an agent receives for one symbol."""
    symbol: str
    bars: pd.DataFrame         # OHLCV, oldest-first
    timeframe: str = "1H"
    spread: float = 0.0
    current_position_side: str | None = None  # "buy", "sell", or None


class BaseAgent:
    """Abstract agent that analyses a single symbol and returns a signal.

    Subclasses override ``analyze`` with their own philosophy. The convention
    is that pure-technical analysis happens inside ``analyze`` so the agent is
    fully testable without network access.
    """

    name: str = "BaseAgent"
    philosophy: str = ""
    default_weight: float = 1.0

    def analyze(self, snapshot: MarketSnapshot) -> AgentSignal:
        raise NotImplementedError

    def _hold(self, snapshot: MarketSnapshot, reason: str = "No setup") -> AgentSignal:
        return AgentSignal(
            agent_name=self.name,
            symbol=snapshot.symbol,
            action=Action.HOLD,
            confidence=0.0,
            reasoning=reason,
            weight=self.default_weight,
        )
