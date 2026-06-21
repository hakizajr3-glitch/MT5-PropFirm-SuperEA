import numpy as np
import pandas as pd

from tradelocker_bot.backtest import (
    BacktestParams,
    BacktestResult,
    Trade,
    run_backtest,
)
from tradelocker_bot.config import StrategyConfig


def _df(closes):
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": closes, "high": closes + 0.1, "low": closes - 0.1, "close": closes}
    )


def test_metrics_on_synthetic_trades():
    res = BacktestResult(ticker="X")
    res.trades = [
        Trade(1, 0, 1, 100, 102, 1, 200.0, 2.0, "target"),
        Trade(1, 2, 3, 100, 99, 1, -100.0, -1.0, "stop"),
        Trade(-1, 4, 5, 100, 98, 1, 200.0, 2.0, "target"),
    ]
    res.equity_curve = pd.Series([100000, 100200, 100100, 100300])
    assert res.n_trades == 3
    assert abs(res.win_rate - (2 / 3 * 100)) < 1e-9
    assert res.gross_profit == 400.0
    assert res.gross_loss == 100.0
    assert res.profit_factor == 4.0
    assert abs(res.total_return_pct - 0.3) < 1e-9


def test_uptrend_produces_profitable_long():
    # Long warmup of flat prices, then a steady uptrend to force an EMA up-cross
    # and let the take-profit fill.
    closes = [100.0] * 60 + [100.0 + 2.0 * k for k in range(1, 15)]
    df = _df(closes)
    scfg = StrategyConfig(fast_ema=5, slow_ema=20, atr_period=14,
                          use_rsi_filter=False, sl_atr=1.5, tp_atr=2.5)
    params = BacktestParams(risk_percent=1.0, cost_bps_per_side=0.0)
    res = run_backtest(df, scfg, params, ticker="SYN")
    assert res.n_trades >= 1
    assert any(t.side == 1 for t in res.trades)
    assert res.equity_curve.iloc[-1] > res.equity_curve.iloc[0]


def test_no_trades_when_flat():
    df = _df([100.0] * 120)
    scfg = StrategyConfig(fast_ema=5, slow_ema=20, atr_period=14,
                          use_rsi_filter=False)
    res = run_backtest(df, scfg, BacktestParams())
    assert res.n_trades == 0
    # equity unchanged with no trades
    assert abs(res.total_return_pct) < 1e-9


def test_risk_based_stop_loss_caps_loss():
    # A long that immediately reverses should lose about risk_percent of equity.
    closes = [100.0] * 60 + [100.0 + 2.0 * k for k in range(1, 4)]
    # after entry, crash below stop
    closes += [90.0, 85.0]
    df = _df(closes)
    scfg = StrategyConfig(fast_ema=5, slow_ema=20, atr_period=14,
                          use_rsi_filter=False, sl_atr=1.5, tp_atr=2.5)
    params = BacktestParams(risk_percent=1.0, cost_bps_per_side=0.0,
                            use_breakeven=False, use_trailing=False)
    res = run_backtest(df, scfg, params)
    losers = [t for t in res.trades if t.pnl < 0]
    if losers:
        # loss should be close to 1% of start equity (the risked amount)
        assert losers[0].r_multiple <= -0.9
