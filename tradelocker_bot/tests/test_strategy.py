import numpy as np
import pandas as pd

from tradelocker_bot import strategy as strat
from tradelocker_bot.config import StrategyConfig


def _df_from_closes(closes):
    closes = np.asarray(closes, dtype=float)
    high = closes + 0.5
    low = closes - 0.5
    return pd.DataFrame(
        {"open": closes, "high": high, "low": low, "close": closes}
    )


def test_ema_matches_pandas_ewm():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = strat.ema(s, 3)
    assert abs(out.iloc[-1] - s.ewm(span=3, adjust=False).mean().iloc[-1]) < 1e-9


def test_rsi_all_gains_is_100():
    closes = pd.Series(np.arange(1, 40, dtype=float))
    out = strat.rsi(closes, 14)
    assert out.iloc[-1] == 100.0


def test_atr_positive():
    df = _df_from_closes(np.linspace(1, 100, 60))
    out = strat.atr(df, 14)
    assert out.iloc[-1] > 0


def test_signal_buy_on_upcross():
    # Flat (fast == slow) then a jump on the final bar makes fast cross above slow.
    closes = [100.0] * 60 + [200.0]
    df = _df_from_closes(closes)
    cfg = StrategyConfig(fast_ema=5, slow_ema=20, atr_period=14,
                         use_rsi_filter=False)
    res = strat.compute_signal(df, cfg)
    assert res.signal == strat.BUY
    assert res.atr > 0


def test_signal_sell_on_downcross():
    closes = [100.0] * 60 + [20.0]
    df = _df_from_closes(closes)
    cfg = StrategyConfig(fast_ema=5, slow_ema=20, atr_period=14,
                         use_rsi_filter=False)
    res = strat.compute_signal(df, cfg)
    assert res.signal == strat.SELL


def test_rsi_filter_blocks_buy():
    closes = [100.0] * 60 + [200.0]
    df = _df_from_closes(closes)
    # Require RSI >= 200 (impossible) so the buy is filtered out.
    cfg = StrategyConfig(fast_ema=5, slow_ema=20, atr_period=14,
                         use_rsi_filter=True, rsi_buy_min=200.0)
    res = strat.compute_signal(df, cfg)
    assert res.signal == strat.NONE


def test_not_enough_data_returns_none():
    df = _df_from_closes([1, 2, 3])
    cfg = StrategyConfig()
    assert strat.compute_signal(df, cfg).signal == strat.NONE


def test_stop_levels_buy_and_sell():
    sl, tp = strat.stop_levels(strat.BUY, entry=100.0, atr_value=2.0,
                               sl_atr=1.5, tp_atr=2.5)
    assert sl == 100.0 - 3.0 and tp == 100.0 + 5.0
    sl, tp = strat.stop_levels(strat.SELL, entry=100.0, atr_value=2.0,
                               sl_atr=1.5, tp_atr=2.5)
    assert sl == 100.0 + 3.0 and tp == 100.0 - 5.0
