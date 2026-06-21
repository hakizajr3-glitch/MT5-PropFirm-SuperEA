import numpy as np
import pandas as pd

from dashboard import analytics


def _trend_df(n=120, start=100.0, step=0.6):
    close = start + np.arange(n) * step
    high = close + 0.3
    low = close - 0.3
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})


def _flat_df(n=200, level=100.0, amp=0.6):
    # tight high-frequency oscillation -> balanced +DM/-DM -> low ADX
    rng = np.random.default_rng(1)
    idx = np.arange(n)
    close = level + np.sin(idx * 1.6) * amp + rng.normal(0, 0.05, n)
    high = close + 0.05
    low = close - 0.05
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})


def test_insufficient_data():
    df = _trend_df(n=10)
    a = analytics.analyze_symbol("X", df)
    assert not a.ok


def test_strong_uptrend_is_trending_high_adx():
    a = analytics.analyze_symbol("UP", _trend_df())
    assert a.ok
    assert a.adx > 25
    assert a.regime == analytics.TRENDING
    assert a.trend_score > 0.3


def test_flat_market_is_ranging_low_adx():
    a = analytics.analyze_symbol("FLAT", _flat_df())
    assert a.ok
    assert a.adx < 20
    assert a.regime == analytics.RANGING


def test_adx_and_bollinger_shapes():
    df = _trend_df()
    assert len(analytics.adx(df, 14)) == len(df)
    mid, up, low = analytics.bollinger(df["close"], 20, 2.0)
    assert (up.dropna() >= mid.dropna()).all()
    assert (low.dropna() <= mid.dropna()).all()


def test_decision_labels_serialise():
    a = analytics.analyze_symbol("UP", _trend_df())
    d = a.as_dict()
    assert d["trend_decision"] in ("BUY", "SELL", "WAIT")
    assert d["range_decision"] in ("BUY", "SELL", "WAIT")
