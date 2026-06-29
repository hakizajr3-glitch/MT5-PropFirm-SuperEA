"""Ben Graham Agent — value / mean-reversion.

Philosophy: buy when price is significantly below its "fair value" (SMA-200)
and oversold, sell when above fair value and overbought.  Requires a "margin
of safety" before entry — price must be far enough from the mean.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from tradelocker_bot.strategy import rsi as calc_rsi

from .base import Action, AgentSignal, BaseAgent, MarketSnapshot


class GrahamAgent(BaseAgent):
    name = "Ben Graham"
    philosophy = "Value investing: buy below fair value with margin of safety"
    default_weight = 1.0

    # tunables
    sma_period: int = 200
    rsi_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0
    margin_of_safety_pct: float = 1.5   # price must be >=1.5% below SMA200 to be "undervalued"
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0

    def analyze(self, snapshot: MarketSnapshot) -> AgentSignal:
        df = snapshot.bars
        if len(df) < self.sma_period + 2:
            return self._hold(snapshot, "Insufficient bars for SMA200")

        close = df["close"]
        price = float(close.iloc[-1])

        sma200 = float(close.rolling(self.sma_period).mean().iloc[-1])
        rsi_val = float(calc_rsi(close, self.rsi_period).iloc[-1])

        bb_mid = close.rolling(self.bb_period).mean()
        bb_std = close.rolling(self.bb_period).std(ddof=0)
        bb_upper = float((bb_mid + self.bb_std * bb_std).iloc[-1])
        bb_lower = float((bb_mid - self.bb_std * bb_std).iloc[-1])

        deviation_pct = (price - sma200) / sma200 * 100.0 if sma200 > 0 else 0.0

        indicators = {
            "sma200": round(sma200, 5),
            "rsi": round(rsi_val, 2),
            "bb_upper": round(bb_upper, 5),
            "bb_lower": round(bb_lower, 5),
            "deviation_pct": round(deviation_pct, 2),
        }

        # undervalued: price well below SMA200 + RSI oversold + near lower band
        if (deviation_pct <= -self.margin_of_safety_pct
                and rsi_val <= self.rsi_oversold
                and price <= bb_lower):
            conf = min(1.0, (abs(deviation_pct) / 5.0 + (self.rsi_oversold - rsi_val) / 30.0) / 2)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.BUY, confidence=round(conf, 3),
                reasoning=(f"Undervalued: price {deviation_pct:+.2f}% below SMA200, "
                           f"RSI={rsi_val:.1f} oversold, at lower Bollinger"),
                indicators=indicators, weight=self.default_weight,
            )

        # overvalued: price well above SMA200 + RSI overbought + near upper band
        if (deviation_pct >= self.margin_of_safety_pct
                and rsi_val >= self.rsi_overbought
                and price >= bb_upper):
            conf = min(1.0, (deviation_pct / 5.0 + (rsi_val - self.rsi_overbought) / 30.0) / 2)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.SELL, confidence=round(conf, 3),
                reasoning=(f"Overvalued: price {deviation_pct:+.2f}% above SMA200, "
                           f"RSI={rsi_val:.1f} overbought, at upper Bollinger"),
                indicators=indicators, weight=self.default_weight,
            )

        return AgentSignal(
            agent_name=self.name, symbol=snapshot.symbol,
            action=Action.HOLD, confidence=0.0,
            reasoning=f"No margin of safety (dev={deviation_pct:+.2f}%, RSI={rsi_val:.1f})",
            indicators=indicators, weight=self.default_weight,
        )
