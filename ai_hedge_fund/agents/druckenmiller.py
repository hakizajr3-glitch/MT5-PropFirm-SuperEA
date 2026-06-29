"""Stan Druckenmiller Agent — macro / risk-reward optimization.

Philosophy: obsessed with risk/reward.  Only enters trades where the reward
potential is at least 2.5x the risk.  Uses swing structure (recent highs/lows)
to define support/resistance, then calculates exact R:R before deciding.
Adapts position conviction to the quality of the setup.
"""

from __future__ import annotations

import numpy as np

from tradelocker_bot.strategy import atr as calc_atr, ema as calc_ema, rsi as calc_rsi
from dashboard.analytics import adx as calc_adx

from .base import Action, AgentSignal, BaseAgent, MarketSnapshot


def _swing_levels(df, lookback: int = 20) -> tuple[float, float]:
    """Return (support, resistance) from recent swing lows/highs."""
    high = df["high"].iloc[-lookback:]
    low = df["low"].iloc[-lookback:]
    return float(low.min()), float(high.max())


class DruckenmillerAgent(BaseAgent):
    name = "Stan Druckenmiller"
    philosophy = "Macro risk/reward: only trade when R:R >= 2.5, optimal setups"
    default_weight = 1.15

    min_rr: float = 2.5

    def analyze(self, snapshot: MarketSnapshot) -> AgentSignal:
        df = snapshot.bars
        if len(df) < 52:
            return self._hold(snapshot, "Insufficient bars for swing analysis")

        close = df["close"]
        price = float(close.iloc[-1])

        atr_val = float(calc_atr(df, 14).iloc[-1])
        rsi_val = float(calc_rsi(close, 14).iloc[-1])
        adx_val = float(calc_adx(df, 14).iloc[-1])
        ema20 = float(calc_ema(close, 20).iloc[-1])
        ema50 = float(calc_ema(close, 50).iloc[-1])

        support, resistance = _swing_levels(df, 20)

        # BUY setup: risk = distance to support, reward = distance to resistance
        buy_risk = max(price - support, atr_val * 1.5)
        buy_reward = max(resistance - price, 0)
        buy_rr = buy_reward / buy_risk if buy_risk > 0 else 0

        # SELL setup: risk = distance to resistance, reward = distance to support
        sell_risk = max(resistance - price, atr_val * 1.5)
        sell_reward = max(price - support, 0)
        sell_rr = sell_reward / sell_risk if sell_risk > 0 else 0

        indicators = {
            "support": round(support, 5), "resistance": round(resistance, 5),
            "buy_rr": round(buy_rr, 2), "sell_rr": round(sell_rr, 2),
            "adx": round(adx_val, 2), "rsi": round(rsi_val, 2),
            "ema20": round(ema20, 5), "ema50": round(ema50, 5),
        }

        # bullish: good R:R + trend confirmation
        if buy_rr >= self.min_rr and price > ema20 and rsi_val > 40:
            conf = round(min(1.0, 0.3 * min(buy_rr / 5.0, 1.0) + 0.3 * (adx_val / 50) + 0.2 * (rsi_val / 100) + 0.2), 3)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.BUY, confidence=conf,
                reasoning=(f"Optimal BUY R:R={buy_rr:.1f}:1 "
                           f"(risk to {support:.5f}, target {resistance:.5f}), "
                           f"ADX={adx_val:.1f}, RSI={rsi_val:.1f}"),
                indicators=indicators, weight=self.default_weight,
            )

        # bearish: good R:R + trend confirmation
        if sell_rr >= self.min_rr and price < ema20 and rsi_val < 60:
            conf = round(min(1.0, 0.3 * min(sell_rr / 5.0, 1.0) + 0.3 * (adx_val / 50) + 0.2 * (1 - rsi_val / 100) + 0.2), 3)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.SELL, confidence=conf,
                reasoning=(f"Optimal SELL R:R={sell_rr:.1f}:1 "
                           f"(risk to {resistance:.5f}, target {support:.5f}), "
                           f"ADX={adx_val:.1f}, RSI={rsi_val:.1f}"),
                indicators=indicators, weight=self.default_weight,
            )

        better_rr = max(buy_rr, sell_rr)
        return AgentSignal(
            agent_name=self.name, symbol=snapshot.symbol,
            action=Action.HOLD, confidence=0.0,
            reasoning=f"R:R insufficient (best={better_rr:.1f}:1, need >={self.min_rr}:1)",
            indicators=indicators, weight=self.default_weight,
        )
