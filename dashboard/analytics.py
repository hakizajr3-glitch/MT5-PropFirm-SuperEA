"""Market analytics for the SHROUDAGE agent layer.

Pure functions (no network) so they can be unit tested. They reuse the bot's
own indicators (`tradelocker_bot.strategy`) and add ADX + Bollinger Bands plus
a regime classifier and the Trend / Range agent decision rules from the
SHROUDAGE spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from tradelocker_bot import strategy as strat

# Decision constants reuse the strategy's BUY/SELL/NONE.
BUY, SELL, WAIT = strat.BUY, strat.SELL, strat.NONE

# Regime labels
TRENDING = "TRENDING"
RANGING = "RANGING"
HIGH_VOL = "HIGH VOLATILITY"
LOW_VOL = "LOW VOLATILITY"
NO_TRADE = "NO TRADE"


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ADX. Expects columns high, low, close."""
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move.clip(lower=0.0)
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move.clip(lower=0.0)

    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    alpha = 1.0 / period
    atr_s = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_s
    minus_di = 100.0 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_s
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0):
    """Return (middle, upper, lower) Bollinger Bands."""
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    return mid, mid + num_std * sd, mid - num_std * sd


def _clip01(x: float) -> float:
    if np.isnan(x):
        return 0.0
    return float(max(0.0, min(1.0, x)))


@dataclass
class SymbolAnalysis:
    symbol: str
    ok: bool = True
    error: str = ""
    price: float = float("nan")
    regime: str = NO_TRADE
    trend_score: float = 0.0
    momentum_score: float = 0.0
    volatility_score: float = 0.0
    liquidity_score: float = 0.0
    confidence_score: float = 0.0
    adx: float = float("nan")
    rsi: float = float("nan")
    atr: float = float("nan")
    atr_pct: float = float("nan")
    ema_fast: float = float("nan")
    ema_slow: float = float("nan")
    spread: float = float("nan")
    trend_decision: int = WAIT
    range_decision: int = WAIT
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["trend_decision"] = _decision_label(self.trend_decision)
        d["range_decision"] = _decision_label(self.range_decision)
        return d


def _decision_label(d: int) -> str:
    return {BUY: "BUY", SELL: "SELL", WAIT: "WAIT"}[d]


def analyze_symbol(
    symbol: str,
    df: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
    rsi_period: int = 14,
    atr_period: int = 14,
    adx_period: int = 14,
    spread: float = float("nan"),
) -> SymbolAnalysis:
    """Classify market regime and produce Trend / Range agent decisions.

    `df` is oldest->newest OHLC with columns open, high, low, close (volume
    optional). Returns a `SymbolAnalysis`.
    """
    need = max(slow, rsi_period, atr_period, adx_period, 20) + 2
    if df is None or len(df) < need:
        return SymbolAnalysis(symbol=symbol, ok=False,
                              error=f"need >= {need} bars, got {0 if df is None else len(df)}")

    close = df["close"]
    ema_fast = strat.ema(close, fast)
    ema_slow = strat.ema(close, slow)
    rsi_s = strat.rsi(close, rsi_period)
    atr_s = strat.atr(df, atr_period)
    adx_s = adx(df, adx_period)
    _, bb_up, bb_low = bollinger(close, 20, 2.0)

    price = float(close.iloc[-1])
    a = SymbolAnalysis(symbol=symbol, price=price)
    a.ema_fast = float(ema_fast.iloc[-1])
    a.ema_slow = float(ema_slow.iloc[-1])
    a.rsi = float(rsi_s.iloc[-1])
    a.atr = float(atr_s.iloc[-1])
    a.adx = float(adx_s.iloc[-1])
    a.atr_pct = (a.atr / price * 100.0) if price else float("nan")
    a.spread = spread

    # ---- scores (0..1) ----
    a.trend_score = _clip01((a.adx - 10.0) / 40.0)              # adx 10->50 maps 0->1
    a.momentum_score = _clip01(abs(a.rsi - 50.0) / 50.0)        # distance from neutral
    # volatility: ~0.5% atr is calm, ~3% is hot
    a.volatility_score = _clip01((a.atr_pct - 0.3) / 2.7)
    if "volume" in df.columns and df["volume"].tail(20).abs().sum() > 0:
        v = df["volume"].astype(float)
        recent, base = v.tail(5).mean(), v.tail(20).mean()
        a.liquidity_score = _clip01(recent / base / 2.0) if base else 0.5
    else:
        a.liquidity_score = 0.5

    # ---- regime ----
    if a.adx >= 25:
        a.regime = TRENDING
    elif a.adx < 20:
        a.regime = RANGING
    elif a.atr_pct >= 2.0:
        a.regime = HIGH_VOL
    else:
        a.regime = LOW_VOL
    if a.atr_pct >= 3.0:
        a.regime = HIGH_VOL

    # confidence: trend regimes lean on trend+momentum; ranges on mean-reversion
    if a.regime == TRENDING:
        a.confidence_score = round(0.6 * a.trend_score + 0.4 * a.momentum_score, 3)
    elif a.regime == RANGING:
        a.confidence_score = round(0.5 * (1 - a.trend_score) + 0.5 * a.momentum_score, 3)
    else:
        a.confidence_score = round(0.3 * a.trend_score + 0.2 * a.momentum_score, 3)

    # ---- Trend Agent (spec rules; HTF EMA50 proxied by same-series EMA slow) ----
    f1, f2 = a.ema_fast, float(ema_fast.iloc[-2])
    s1, s2 = a.ema_slow, float(ema_slow.iloc[-2])
    cross_up = f2 <= s2 and f1 > s1
    cross_down = f2 >= s2 and f1 < s1
    if cross_up and a.rsi > 55 and a.adx > 25 and price > a.ema_slow:
        a.trend_decision = BUY
        a.reasons.append("Trend: EMA cross up + RSI>55 + ADX>25 + price>EMA50")
    elif cross_down and a.rsi < 45 and a.adx > 25 and price < a.ema_slow:
        a.trend_decision = SELL
        a.reasons.append("Trend: EMA cross down + RSI<45 + ADX>25 + price<EMA50")
    else:
        a.trend_decision = WAIT

    # ---- Range Agent (spec rules) ----
    up, low_ = float(bb_up.iloc[-1]), float(bb_low.iloc[-1])
    if a.adx < 20:
        if a.rsi < 30 and price <= low_:
            a.range_decision = BUY
            a.reasons.append("Range: RSI<30 + price at lower band")
        elif a.rsi > 70 and price >= up:
            a.range_decision = SELL
            a.reasons.append("Range: RSI>70 + price at upper band")
        else:
            a.range_decision = WAIT
    else:
        a.range_decision = WAIT

    if not a.reasons:
        a.reasons.append("No confirmed setup — WAIT")
    return a
