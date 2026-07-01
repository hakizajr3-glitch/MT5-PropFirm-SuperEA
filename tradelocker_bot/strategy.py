"""Strategy logic: EMA crossover trend entries with RSI filter and ATR sizing.

Enhanced v4.0 adds: ADX trend-strength filter, MACD momentum confirmation,
EMA-200 higher-timeframe alignment, volatility regime filter, and a
signal-strength score that drives adaptive position sizing.

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


# ────────────────────────────────────────────────────────────────────
# Core indicators
# ────────────────────────────────────────────────────────────────────

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


# ────────────────────────────────────────────────────────────────────
# Enhanced indicators (v4.0)
# ────────────────────────────────────────────────────────────────────

def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index — measures trend strength (0-100).

    ADX > 20-25 indicates a trending market; below that is ranging/choppy.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
                        index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
                         index=df.index)

    atr_s = atr(df, period)
    smooth_plus = plus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    smooth_minus = minus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    plus_di = 100.0 * smooth_plus / atr_s.replace(0.0, np.nan)
    minus_di = 100.0 * smooth_minus / atr_s.replace(0.0, np.nan)

    di_sum = plus_di + minus_di
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum.replace(0.0, np.nan)
    return dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26,
         signal_period: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, histogram."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def volatility_ratio(df: pd.DataFrame, atr_period: int = 14,
                     lookback: int = 50) -> pd.Series:
    """Current ATR / average ATR over a longer lookback.

    Ratio near 1.0 = normal volatility.
    Ratio < 0.5 = unusually quiet (false breakouts likely).
    Ratio > 2.0 = unusually volatile (risk of wild swings).
    """
    atr_s = atr(df, atr_period)
    atr_avg = atr_s.rolling(window=lookback, min_periods=lookback).mean()
    return atr_s / atr_avg.replace(0.0, np.nan)


# ────────────────────────────────────────────────────────────────────
# Signal results
# ────────────────────────────────────────────────────────────────────

@dataclass
class SignalResult:
    signal: int            # BUY / SELL / NONE
    atr: float             # ATR of last closed bar
    close: float           # close of last closed bar
    fast: float
    slow: float
    rsi: float
    strength: int = 100    # signal strength 0-100 (v4.0)
    adx: float = 0.0       # ADX value (v4.0)
    macd_hist: float = 0.0 # MACD histogram (v4.0)


def compute_signal(df: pd.DataFrame, cfg) -> SignalResult:
    """Compute a trade signal from closed bars.

    `df` must be sorted oldest->newest with columns: open, high, low, close.
    The last row is treated as the most recent *closed* bar.
    `cfg` is a StrategyConfig (or any object with the same attributes).

    Enhanced in v4.0: when the config has enhanced-filter attributes
    (use_adx_filter, use_macd_filter, etc.) the signal is gated by additional
    confirmations and a strength score (0-100) is returned. Old configs
    without these attributes behave exactly as before (backward compatible).
    """
    min_bars = max(cfg.slow_ema, cfg.atr_period, cfg.rsi_period) + 2
    if len(df) < min_bars:
        return SignalResult(NONE, float("nan"), float("nan"),
                            float("nan"), float("nan"), float("nan"))

    fast_s = ema(df["close"], cfg.fast_ema)
    slow_s = ema(df["close"], cfg.slow_ema)
    atr_s = atr(df, cfg.atr_period)
    rsi_s = rsi(df["close"], cfg.rsi_period)

    f1, f2 = fast_s.iloc[-1], fast_s.iloc[-2]
    s1, s2 = slow_s.iloc[-1], slow_s.iloc[-2]

    cross_up = f2 <= s2 and f1 > s1
    cross_down = f2 >= s2 and f1 < s1

    last_rsi = float(rsi_s.iloc[-1])
    if cfg.use_rsi_filter and not np.isnan(last_rsi):
        if cross_up and last_rsi < cfg.rsi_buy_min:
            cross_up = False
        if cross_down and last_rsi > cfg.rsi_sell_max:
            cross_down = False

    signal = BUY if cross_up else SELL if cross_down else NONE

    last_atr = float(atr_s.iloc[-1])
    last_close = float(df["close"].iloc[-1])

    # ── Enhanced filters (v4.0) ──────────────────────────────────
    strength = 100
    adx_val = 0.0
    macd_hist_val = 0.0

    use_adx = getattr(cfg, "use_adx_filter", False)
    use_macd_f = getattr(cfg, "use_macd_filter", False)
    use_ema200 = getattr(cfg, "use_ema200_filter", False)
    use_vol = getattr(cfg, "use_volatility_filter", False)

    if signal != NONE and (use_adx or use_macd_f or use_ema200 or use_vol):
        confirmations = 0
        total_checks = 0

        # 1) ADX trend-strength filter
        if use_adx:
            total_checks += 1
            adx_period = getattr(cfg, "adx_period", 14)
            adx_min = getattr(cfg, "adx_min", 20.0)
            adx_s = adx(df, adx_period)
            adx_val = float(adx_s.iloc[-1]) if not np.isnan(adx_s.iloc[-1]) else 0.0
            if adx_val >= adx_min:
                confirmations += 1
            else:
                signal = NONE  # hard filter: no trend = no trade

        # 2) MACD momentum confirmation
        if use_macd_f and signal != NONE:
            total_checks += 1
            macd_fast = getattr(cfg, "macd_fast", 12)
            macd_slow_p = getattr(cfg, "macd_slow", 26)
            macd_signal_p = getattr(cfg, "macd_signal", 9)
            _, _, hist_s = macd(df["close"], macd_fast, macd_slow_p, macd_signal_p)
            macd_hist_val = float(hist_s.iloc[-1]) if not np.isnan(hist_s.iloc[-1]) else 0.0
            if (signal == BUY and macd_hist_val > 0) or \
               (signal == SELL and macd_hist_val < 0):
                confirmations += 1
            else:
                signal = NONE  # histogram must agree with direction

        # 3) EMA-200 trend alignment (higher timeframe proxy)
        if use_ema200 and signal != NONE:
            total_checks += 1
            ema200_period = getattr(cfg, "ema200_period", 200)
            if len(df) < ema200_period + 2:
                signal = NONE  # insufficient bars for EMA200
            else:
                ema200_s = ema(df["close"], ema200_period)
                ema200_val = float(ema200_s.iloc[-1])
                if (signal == BUY and last_close > ema200_val) or \
                   (signal == SELL and last_close < ema200_val):
                    confirmations += 1
                else:
                    signal = NONE  # price must be on correct side of EMA200

        # 4) Volatility regime filter
        if use_vol and signal != NONE:
            total_checks += 1
            vol_lookback = getattr(cfg, "vol_lookback", 50)
            vol_min = getattr(cfg, "vol_min", 0.5)
            vol_max = getattr(cfg, "vol_max", 2.5)
            if len(df) < vol_lookback + cfg.atr_period:
                signal = NONE  # insufficient bars for volatility ratio
            else:
                vol_r = volatility_ratio(df, cfg.atr_period, vol_lookback)
                vol_val = float(vol_r.iloc[-1])
                if np.isnan(vol_val):
                    signal = NONE  # NaN volatility = reject
                elif vol_min <= vol_val <= vol_max:
                    confirmations += 1
                else:
                    signal = NONE  # volatility too extreme

        # Strength score: base 40 + 15 per confirmation (max 100)
        if total_checks > 0 and signal != NONE:
            strength = min(100, 40 + int(60 * confirmations / total_checks))
        elif signal == NONE:
            strength = 0

    return SignalResult(
        signal=signal,
        atr=last_atr,
        close=last_close,
        fast=float(f1),
        slow=float(s1),
        rsi=last_rsi,
        strength=strength,
        adx=adx_val,
        macd_hist=macd_hist_val,
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
