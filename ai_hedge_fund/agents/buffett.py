"""Warren Buffett Agent — quality trend following.

Philosophy: only trade strong, clean trends where EMAs are properly aligned
(20 > 50 > 200 for buys), ADX confirms strength, and volatility is contained.
Patient — waits for the perfect setup.
"""

from __future__ import annotations

from tradelocker_bot.strategy import atr as calc_atr, ema as calc_ema, rsi as calc_rsi
from dashboard.analytics import adx as calc_adx

from .base import Action, AgentSignal, BaseAgent, MarketSnapshot


class BuffettAgent(BaseAgent):
    name = "Warren Buffett"
    philosophy = "Quality trend following: clean trends, EMA alignment, patience"
    default_weight = 1.2  # slight premium for Buffett's track record

    adx_min: float = 25.0
    rsi_buy_range: tuple[float, float] = (45.0, 70.0)
    rsi_sell_range: tuple[float, float] = (30.0, 55.0)

    def analyze(self, snapshot: MarketSnapshot) -> AgentSignal:
        df = snapshot.bars
        if len(df) < 202:
            return self._hold(snapshot, "Insufficient bars for EMA alignment check")

        close = df["close"]
        price = float(close.iloc[-1])

        ema20 = float(calc_ema(close, 20).iloc[-1])
        ema50 = float(calc_ema(close, 50).iloc[-1])
        ema200 = float(calc_ema(close, 200).iloc[-1])
        adx_val = float(calc_adx(df, 14).iloc[-1])
        rsi_val = float(calc_rsi(close, 14).iloc[-1])
        atr_val = float(calc_atr(df, 14).iloc[-1])
        atr_pct = (atr_val / price * 100.0) if price > 0 else 0.0

        indicators = {
            "ema20": round(ema20, 5), "ema50": round(ema50, 5),
            "ema200": round(ema200, 5), "adx": round(adx_val, 2),
            "rsi": round(rsi_val, 2), "atr_pct": round(atr_pct, 3),
        }

        # bullish alignment: price > EMA20 > EMA50 > EMA200
        bull_aligned = price > ema20 > ema50 > ema200
        # bearish alignment: price < EMA20 < EMA50 < EMA200
        bear_aligned = price < ema20 < ema50 < ema200

        if bull_aligned and adx_val >= self.adx_min:
            rsi_ok = self.rsi_buy_range[0] <= rsi_val <= self.rsi_buy_range[1]
            if rsi_ok:
                strength = min(1.0, (adx_val - 20) / 30.0)
                alignment = min(1.0, (ema20 - ema200) / ema200 * 200)
                conf = round(0.5 * strength + 0.3 * alignment + 0.2 * (rsi_val / 100), 3)
                return AgentSignal(
                    agent_name=self.name, symbol=snapshot.symbol,
                    action=Action.BUY, confidence=min(conf, 0.95),
                    reasoning=(f"Quality uptrend: EMA aligned (20>{ema50:.5f}>200), "
                               f"ADX={adx_val:.1f}, RSI={rsi_val:.1f}"),
                    indicators=indicators, weight=self.default_weight,
                )

        if bear_aligned and adx_val >= self.adx_min:
            rsi_ok = self.rsi_sell_range[0] <= rsi_val <= self.rsi_sell_range[1]
            if rsi_ok:
                strength = min(1.0, (adx_val - 20) / 30.0)
                conf = round(0.5 * strength + 0.3 * (1 - rsi_val / 100) + 0.2, 3)
                return AgentSignal(
                    agent_name=self.name, symbol=snapshot.symbol,
                    action=Action.SELL, confidence=min(conf, 0.95),
                    reasoning=(f"Quality downtrend: EMA aligned (20<{ema50:.5f}<200), "
                               f"ADX={adx_val:.1f}, RSI={rsi_val:.1f}"),
                    indicators=indicators, weight=self.default_weight,
                )

        return AgentSignal(
            agent_name=self.name, symbol=snapshot.symbol,
            action=Action.HOLD, confidence=0.0,
            reasoning=f"No quality trend (aligned={bull_aligned or bear_aligned}, ADX={adx_val:.1f})",
            indicators=indicators, weight=self.default_weight,
        )
