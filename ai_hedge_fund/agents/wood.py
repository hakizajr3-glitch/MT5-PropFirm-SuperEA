"""Cathie Wood Agent — growth / innovation momentum.

Philosophy: early entry into strong trends. Looks for MACD crossover with
expanding histogram, trend acceleration (fast EMA pulling away from slow),
and willingness to enter before the crowd.  Higher risk tolerance.
"""

from __future__ import annotations

from tradelocker_bot.strategy import ema as calc_ema, rsi as calc_rsi

from .base import Action, AgentSignal, BaseAgent, MarketSnapshot


def _macd(close, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


class WoodAgent(BaseAgent):
    name = "Cathie Wood"
    philosophy = "Growth momentum: early trend entry, MACD acceleration"
    default_weight = 0.8  # lower weight — higher risk tolerance means less reliability

    def analyze(self, snapshot: MarketSnapshot) -> AgentSignal:
        df = snapshot.bars
        if len(df) < 52:
            return self._hold(snapshot, "Insufficient bars for momentum check")

        close = df["close"]
        price = float(close.iloc[-1])

        ema20 = calc_ema(close, 20)
        ema50 = calc_ema(close, 50)
        rsi_val = float(calc_rsi(close, 14).iloc[-1])
        macd_line, signal_line, histogram = _macd(close)

        macd_val = float(macd_line.iloc[-1])
        sig_val = float(signal_line.iloc[-1])
        hist_val = float(histogram.iloc[-1])
        hist_prev = float(histogram.iloc[-2])

        # trend acceleration: gap between fast and slow EMA widening
        ema_gap = float(ema20.iloc[-1]) - float(ema50.iloc[-1])
        ema_gap_prev = float(ema20.iloc[-2]) - float(ema50.iloc[-2])
        accelerating = abs(ema_gap) > abs(ema_gap_prev)

        # MACD crossover detection
        macd_cross_up = float(macd_line.iloc[-2]) <= float(signal_line.iloc[-2]) and macd_val > sig_val
        macd_cross_down = float(macd_line.iloc[-2]) >= float(signal_line.iloc[-2]) and macd_val < sig_val

        indicators = {
            "macd": round(macd_val, 5), "macd_signal": round(sig_val, 5),
            "macd_hist": round(hist_val, 5), "rsi": round(rsi_val, 2),
            "ema_gap": round(ema_gap, 5), "accelerating": accelerating,
            "macd_cross_up": macd_cross_up, "macd_cross_down": macd_cross_down,
        }

        # bullish: MACD cross up OR (momentum building + acceleration)
        if macd_cross_up and rsi_val > 40:
            conf = round(min(1.0, 0.6 + 0.2 * int(accelerating) + 0.1 * (rsi_val / 100)), 3)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.BUY, confidence=conf,
                reasoning=f"MACD cross up, RSI={rsi_val:.1f}, trend {'accelerating' if accelerating else 'steady'}",
                indicators=indicators, weight=self.default_weight,
            )

        if ema_gap > 0 and accelerating and hist_val > 0 and hist_val > hist_prev and rsi_val > 50:
            conf = round(min(0.85, 0.45 + 0.2 * int(hist_val > hist_prev) + 0.1 * (rsi_val / 100)), 3)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.BUY, confidence=conf,
                reasoning=f"Momentum building: EMA gap widening, MACD histogram expanding, RSI={rsi_val:.1f}",
                indicators=indicators, weight=self.default_weight,
            )

        # bearish
        if macd_cross_down and rsi_val < 60:
            conf = round(min(1.0, 0.6 + 0.2 * int(accelerating) + 0.1 * (1 - rsi_val / 100)), 3)
            return AgentSignal(
                agent_name=self.name, symbol=snapshot.symbol,
                action=Action.SELL, confidence=conf,
                reasoning=f"MACD cross down, RSI={rsi_val:.1f}, trend {'accelerating' if accelerating else 'steady'}",
                indicators=indicators, weight=self.default_weight,
            )

        return AgentSignal(
            agent_name=self.name, symbol=snapshot.symbol,
            action=Action.HOLD, confidence=0.0,
            reasoning=f"No momentum signal (MACD hist={hist_val:.5f}, RSI={rsi_val:.1f})",
            indicators=indicators, weight=self.default_weight,
        )
