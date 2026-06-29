"""Charlie Munger Agent — quality at fair price / multi-indicator confluence.

Philosophy: only act when multiple independent indicators converge on the same
conclusion.  Looks for RSI divergence (price making new highs/lows while RSI
doesn't), which signals exhaustion, and requires at least 3 confirming factors
before recommending a trade.  Contrarian on extreme readings.
"""

from __future__ import annotations

import numpy as np

from tradelocker_bot.strategy import atr as calc_atr, ema as calc_ema, rsi as calc_rsi
from dashboard.analytics import adx as calc_adx

from .base import Action, AgentSignal, BaseAgent, MarketSnapshot


class MungerAgent(BaseAgent):
    name = "Charlie Munger"
    philosophy = "Multi-indicator confluence: act only when evidence converges"
    default_weight = 1.1

    min_confirmations: int = 3

    def analyze(self, snapshot: MarketSnapshot) -> AgentSignal:
        df = snapshot.bars
        if len(df) < 60:
            return self._hold(snapshot, "Insufficient bars for confluence check")

        close = df["close"]
        high = df["high"]
        low = df["low"]
        price = float(close.iloc[-1])

        ema20 = calc_ema(close, 20)
        ema50 = calc_ema(close, 50)
        rsi_s = calc_rsi(close, 14)
        adx_s = calc_adx(df, 14)
        atr_s = calc_atr(df, 14)

        rsi_val = float(rsi_s.iloc[-1])
        adx_val = float(adx_s.iloc[-1])
        ema20_val = float(ema20.iloc[-1])
        ema50_val = float(ema50.iloc[-1])

        # RSI divergence detection (last 14 bars)
        lookback = min(14, len(df) - 1)
        price_slice = close.iloc[-lookback:]
        rsi_slice = rsi_s.iloc[-lookback:]

        bullish_div = (float(price_slice.iloc[-1]) <= float(price_slice.min())
                       and float(rsi_slice.iloc[-1]) > float(rsi_slice.min()) + 5)
        bearish_div = (float(price_slice.iloc[-1]) >= float(price_slice.max())
                       and float(rsi_slice.iloc[-1]) < float(rsi_slice.max()) - 5)

        indicators = {
            "ema20": round(ema20_val, 5), "ema50": round(ema50_val, 5),
            "rsi": round(rsi_val, 2), "adx": round(adx_val, 2),
            "bullish_divergence": bullish_div, "bearish_divergence": bearish_div,
        }

        # tally bullish confirmations
        bull_confirms = []
        if price > ema20_val:
            bull_confirms.append("price > EMA20")
        if ema20_val > ema50_val:
            bull_confirms.append("EMA20 > EMA50")
        if rsi_val > 50:
            bull_confirms.append(f"RSI={rsi_val:.0f} > 50")
        if adx_val > 20:
            bull_confirms.append(f"ADX={adx_val:.0f} trending")
        if bullish_div:
            bull_confirms.append("bullish RSI divergence")

        bear_confirms = []
        if price < ema20_val:
            bear_confirms.append("price < EMA20")
        if ema20_val < ema50_val:
            bear_confirms.append("EMA20 < EMA50")
        if rsi_val < 50:
            bear_confirms.append(f"RSI={rsi_val:.0f} < 50")
        if adx_val > 20:
            bear_confirms.append(f"ADX={adx_val:.0f} trending")
        if bearish_div:
            bear_confirms.append("bearish RSI divergence")

        if len(bull_confirms) >= self.min_confirmations:
            conf = round(min(1.0, len(bull_confirms) / 5.0), 3)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.BUY, confidence=conf,
                reasoning=f"Confluence BUY ({len(bull_confirms)}/5): {', '.join(bull_confirms)}",
                indicators=indicators, weight=self.default_weight,
            )

        if len(bear_confirms) >= self.min_confirmations:
            conf = round(min(1.0, len(bear_confirms) / 5.0), 3)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.SELL, confidence=conf,
                reasoning=f"Confluence SELL ({len(bear_confirms)}/5): {', '.join(bear_confirms)}",
                indicators=indicators, weight=self.default_weight,
            )

        return AgentSignal(
            agent_name=self.name, symbol=snapshot.symbol,
            action=Action.HOLD, confidence=0.0,
            reasoning=f"Insufficient confluence (bull={len(bull_confirms)}, bear={len(bear_confirms)}, need {self.min_confirmations})",
            indicators=indicators, weight=self.default_weight,
        )
