"""Bill Ackman Agent — activist momentum / breakout.

Philosophy: aggressive entries on strong momentum breakouts.  Looks for price
breaking above/below recent highs/lows with high ADX and expanding MACD
histogram.  Ackman takes concentrated, high-conviction positions.
"""

from __future__ import annotations

from tradelocker_bot.strategy import atr as calc_atr, ema as calc_ema
from dashboard.analytics import adx as calc_adx

from .base import Action, AgentSignal, BaseAgent, MarketSnapshot


def _macd(close, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


class AckmanAgent(BaseAgent):
    name = "Bill Ackman"
    philosophy = "Activist momentum: breakout detection, concentrated conviction"
    default_weight = 0.9

    breakout_period: int = 20
    adx_min: float = 25.0

    def analyze(self, snapshot: MarketSnapshot) -> AgentSignal:
        df = snapshot.bars
        if len(df) < 30:
            return self._hold(snapshot, "Insufficient bars for breakout detection")

        close = df["close"]
        high = df["high"]
        low = df["low"]
        price = float(close.iloc[-1])

        # breakout levels
        period_high = float(high.iloc[-self.breakout_period - 1:-1].max())
        period_low = float(low.iloc[-self.breakout_period - 1:-1].min())

        adx_val = float(calc_adx(df, 14).iloc[-1])
        atr_val = float(calc_atr(df, 14).iloc[-1])
        macd_line, signal_line, histogram = _macd(close)
        hist_val = float(histogram.iloc[-1])
        hist_prev = float(histogram.iloc[-2])
        hist_expanding = abs(hist_val) > abs(hist_prev)

        indicators = {
            "period_high": round(period_high, 5),
            "period_low": round(period_low, 5),
            "adx": round(adx_val, 2),
            "macd_hist": round(hist_val, 5),
            "hist_expanding": hist_expanding,
        }

        # bullish breakout: price above recent high + strong trend + MACD expanding up
        if price > period_high and adx_val >= self.adx_min and hist_val > 0 and hist_expanding:
            breakout_strength = (price - period_high) / atr_val if atr_val > 0 else 0
            conf = round(min(1.0, 0.5 + 0.2 * min(breakout_strength, 2) + 0.15 * (adx_val / 50)), 3)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.BUY, confidence=conf,
                reasoning=(f"Bullish breakout above {period_high:.5f}, "
                           f"ADX={adx_val:.1f}, MACD expanding"),
                indicators=indicators, weight=self.default_weight,
            )

        # bearish breakout
        if price < period_low and adx_val >= self.adx_min and hist_val < 0 and hist_expanding:
            breakout_strength = (period_low - price) / atr_val if atr_val > 0 else 0
            conf = round(min(1.0, 0.5 + 0.2 * min(breakout_strength, 2) + 0.15 * (adx_val / 50)), 3)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.SELL, confidence=conf,
                reasoning=(f"Bearish breakout below {period_low:.5f}, "
                           f"ADX={adx_val:.1f}, MACD expanding"),
                indicators=indicators, weight=self.default_weight,
            )

        return AgentSignal(
            agent_name=self.name, symbol=snapshot.symbol,
            action=Action.HOLD, confidence=0.0,
            reasoning=f"No breakout (price in range {period_low:.5f}-{period_high:.5f}, ADX={adx_val:.1f})",
            indicators=indicators, weight=self.default_weight,
        )
