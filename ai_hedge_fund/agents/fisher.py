"""Phil Fisher Agent — growth quality / steady trend.

Philosophy: invest in assets showing consistent, low-volatility trends.
Measures trend quality via linear regression R-squared and the Choppiness
Index.  Only trades when price is trending smoothly — avoids choppy, noisy
markets.  Patient like Buffett but focused on growth consistency.
"""

from __future__ import annotations

import numpy as np

from tradelocker_bot.strategy import atr as calc_atr, ema as calc_ema, rsi as calc_rsi

from .base import Action, AgentSignal, BaseAgent, MarketSnapshot


def _linreg_r2(series, period: int = 20) -> float:
    """R-squared of a linear regression over the last `period` values."""
    y = series.iloc[-period:].values.astype(float)
    if len(y) < period or np.std(y) == 0:
        return 0.0
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    ss_res = np.sum((y - predicted) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    return float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0


def _choppiness(df, period: int = 14) -> float:
    """Choppiness Index: 100 * log10(sum(ATR_1) / (HH - LL)) / log10(period).
    High values (>61.8) = choppy; low values (<38.2) = trending."""
    if len(df) < period + 1:
        return 50.0
    high = df["high"].iloc[-period:]
    low = df["low"].iloc[-period:]
    close = df["close"]
    prev_close = close.shift(1)
    tr = np.maximum(high.values - low.values,
                    np.maximum(np.abs(high.values - close.shift(1).iloc[-period:].values),
                               np.abs(low.values - close.shift(1).iloc[-period:].values)))
    atr_sum = float(np.nansum(tr))
    hh = float(high.max())
    ll = float(low.min())
    rng = hh - ll
    if rng <= 0 or atr_sum <= 0:
        return 50.0
    return float(100.0 * np.log10(atr_sum / rng) / np.log10(period))


class FisherAgent(BaseAgent):
    name = "Phil Fisher"
    philosophy = "Growth quality: consistent trends, low choppiness, smooth price action"
    default_weight = 1.0

    r2_min: float = 0.6           # minimum trend quality
    chop_max: float = 45.0        # below this = clean trend

    def analyze(self, snapshot: MarketSnapshot) -> AgentSignal:
        df = snapshot.bars
        if len(df) < 52:
            return self._hold(snapshot, "Insufficient bars for trend quality check")

        close = df["close"]
        price = float(close.iloc[-1])

        ema20 = float(calc_ema(close, 20).iloc[-1])
        ema50 = float(calc_ema(close, 50).iloc[-1])
        rsi_val = float(calc_rsi(close, 14).iloc[-1])

        r2 = _linreg_r2(close, 20)
        chop = _choppiness(df, 14)

        # trend direction from linear regression slope
        y = close.iloc[-20:].values.astype(float)
        x = np.arange(len(y), dtype=float)
        slope = float(np.polyfit(x, y, 1)[0])

        indicators = {
            "r2": round(r2, 3), "choppiness": round(chop, 2),
            "slope": round(slope, 6), "ema20": round(ema20, 5),
            "ema50": round(ema50, 5), "rsi": round(rsi_val, 2),
        }

        is_quality = r2 >= self.r2_min and chop <= self.chop_max

        if is_quality and slope > 0 and price > ema20 > ema50:
            conf = round(min(1.0, 0.4 * r2 + 0.3 * (1 - chop / 100) + 0.2 * (rsi_val / 100) + 0.1), 3)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.BUY, confidence=conf,
                reasoning=f"Quality uptrend: R2={r2:.2f}, Chop={chop:.1f}, slope positive, price>EMA20>EMA50",
                indicators=indicators, weight=self.default_weight,
            )

        if is_quality and slope < 0 and price < ema20 < ema50:
            conf = round(min(1.0, 0.4 * r2 + 0.3 * (1 - chop / 100) + 0.2 * (1 - rsi_val / 100) + 0.1), 3)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.SELL, confidence=conf,
                reasoning=f"Quality downtrend: R2={r2:.2f}, Chop={chop:.1f}, slope negative, price<EMA20<EMA50",
                indicators=indicators, weight=self.default_weight,
            )

        return AgentSignal(
            agent_name=self.name, symbol=snapshot.symbol,
            action=Action.HOLD, confidence=0.0,
            reasoning=f"Trend not clean enough (R2={r2:.2f}, Chop={chop:.1f}, need R2>={self.r2_min} and Chop<={self.chop_max})",
            indicators=indicators, weight=self.default_weight,
        )
