"""Strategy logic: EMA crossover trend entries with RSI filter and ATR sizing.

These functions are pure (no network / SDK dependency) so they can be unit
tested in isolation. They mirror the logic of the MT5 EA `GetSignal()` /
ATR-based stop placement.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

BUY = 1
SELL = -1
NONE = 0


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss is 0 the market only went up -> RSI 100.
    out = out.where(avg_loss != 0.0, 100.0)
    return out


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Wilder's ATR. Expects columns high, low, close."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


@dataclass
class SignalResult:
    signal: int            # BUY / SELL / NONE
    atr: float             # ATR of last closed bar
    close: float           # close of last closed bar
    fast: float
    slow: float
    rsi: float


def compute_signal(df: pd.DataFrame, cfg) -> SignalResult:
    """Compute a trade signal from closed bars.

    `df` must be sorted oldest->newest with columns: open, high, low, close.
    The last row is treated as the most recent *closed* bar.
    `cfg` is a StrategyConfig (or any object with the same attributes).
    """
    if len(df) < max(cfg.slow_ema, cfg.atr_period, cfg.rsi_period) + 2:
        return SignalResult(NONE, float("nan"), float("nan"),
                            float("nan"), float("nan"), float("nan"))

    fast = ema(df["close"], cfg.fast_ema)
    slow = ema(df["close"], cfg.slow_ema)
    atr_s = atr(df, cfg.atr_period)
    rsi_s = rsi(df["close"], cfg.rsi_period)

    f1, f2 = fast.iloc[-1], fast.iloc[-2]
    s1, s2 = slow.iloc[-1], slow.iloc[-2]

    cross_up = f2 <= s2 and f1 > s1
    cross_down = f2 >= s2 and f1 < s1

    last_rsi = float(rsi_s.iloc[-1])
    if cfg.use_rsi_filter and not np.isnan(last_rsi):
        if cross_up and last_rsi < cfg.rsi_buy_min:
            cross_up = False
        if cross_down and last_rsi > cfg.rsi_sell_max:
            cross_down = False

    signal = BUY if cross_up else SELL if cross_down else NONE

    return SignalResult(
        signal=signal,
        atr=float(atr_s.iloc[-1]),
        close=float(df["close"].iloc[-1]),
        fast=float(f1),
        slow=float(s1),
        rsi=last_rsi,
    )


def stop_levels(signal: int, entry: float, atr_value: float,
                sl_atr: float, tp_atr: float) -> tuple[float, float]:
    """Return (stop_loss, take_profit) prices for a market entry."""
    sl_dist = atr_value * sl_atr
    tp_dist = atr_value * tp_atr
    if signal == BUY:
        return entry - sl_dist, entry + tp_dist
    if signal == SELL:
        return entry + sl_dist, entry - tp_dist
    raise ValueError("stop_levels requires a BUY or SELL signal")
