"""Historical backtester for the PropFirm SuperEA strategy.

Runs the *same* entry/exit rules as the live bot (`strategy.py`) over real
historical OHLC data and reports honest performance metrics: win rate, profit
factor, total return, max drawdown and trade count.

Position sizing is risk-based: every trade risks a fixed % of current equity, so
a stop-out loses exactly that % (currency-agnostic). Transaction cost is modelled
as a per-side spread in basis points.

Approximations (documented so results aren't oversold):
- Uses end-of-day (daily) bars by default. Intraday behaviour will differ.
- Entries fill at the next bar's open after a signal bar.
- If a bar's range touches both stop and target, the **stop** is assumed hit
  first (pessimistic).
- Break-even / trailing stops are updated once per bar (on close).

Usage:
    python -m tradelocker_bot.backtest                      # default instruments
    python -m tradelocker_bot.backtest --tickers EURUSD=X GC=F --start 2015-01-01
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import strategy as strat
from .config import StrategyConfig


@dataclass
class BacktestParams:
    risk_percent: float = 1.0
    start_equity: float = 100_000.0
    cost_bps_per_side: float = 1.0      # spread/commission per side, basis points of price
    max_total_dd_pct: float = 0.0       # 0 = disabled; else halt trading past this DD
    use_breakeven: bool = True
    be_trigger_atr: float = 1.0
    be_lock_atr: float = 0.1
    use_trailing: bool = True
    trail_start_atr: float = 1.5
    trail_step_atr: float = 1.0


@dataclass
class Trade:
    side: int
    entry_idx: int
    exit_idx: int
    entry: float
    exit: float
    qty: float
    pnl: float
    r_multiple: float
    reason: str


@dataclass
class BacktestResult:
    ticker: str
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=pd.Series)
    start: str = ""
    end: str = ""

    # ---- metrics ----
    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> list[Trade]:
        return [t for t in self.trades if t.pnl > 0]

    @property
    def losses(self) -> list[Trade]:
        return [t for t in self.trades if t.pnl <= 0]

    @property
    def win_rate(self) -> float:
        return 100.0 * len(self.wins) / self.n_trades if self.n_trades else 0.0

    @property
    def gross_profit(self) -> float:
        return sum(t.pnl for t in self.wins)

    @property
    def gross_loss(self) -> float:
        return -sum(t.pnl for t in self.losses)

    @property
    def profit_factor(self) -> float:
        gl = self.gross_loss
        return (self.gross_profit / gl) if gl > 0 else float("inf")

    @property
    def total_return_pct(self) -> float:
        if self.equity_curve.empty:
            return 0.0
        return 100.0 * (self.equity_curve.iloc[-1] / self.equity_curve.iloc[0] - 1.0)

    @property
    def max_drawdown_pct(self) -> float:
        if self.equity_curve.empty:
            return 0.0
        eq = self.equity_curve
        dd = (eq - eq.cummax()) / eq.cummax()
        return float(-dd.min() * 100.0)

    @property
    def expectancy_r(self) -> float:
        if not self.n_trades:
            return 0.0
        return float(np.mean([t.r_multiple for t in self.trades]))


def load_data(ticker: str, start: str | None, end: str | None) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(ticker, start=start, end=end, interval="1d",
                      progress=False, auto_adjust=False)
    if raw.empty:
        raise RuntimeError(f"No data returned for {ticker}")
    # yfinance may return a column MultiIndex (field, ticker); flatten it.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw.rename(columns={"Open": "open", "High": "high",
                             "Low": "low", "Close": "close"})
    df = df[["open", "high", "low", "close"]].dropna().reset_index(drop=True)
    return df


def run_backtest(df: pd.DataFrame, scfg: StrategyConfig,
                 params: BacktestParams, ticker: str = "") -> BacktestResult:
    fast = strat.ema(df["close"], scfg.fast_ema).to_numpy()
    slow = strat.ema(df["close"], scfg.slow_ema).to_numpy()
    rsi = strat.rsi(df["close"], scfg.rsi_period).to_numpy()
    atr = strat.atr(df, scfg.atr_period).to_numpy()
    op = df["open"].to_numpy()
    hi = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    cl = df["close"].to_numpy()
    n = len(df)

    warmup = max(scfg.slow_ema, scfg.atr_period, scfg.rsi_period) + 2
    equity = params.start_equity
    eq_points = [equity]
    trades: list[Trade] = []
    cost = params.cost_bps_per_side / 10_000.0

    # open position state
    in_pos = False
    side = 0
    entry = sl = tp = qty = 0.0
    risk_at_entry = 0.0
    entry_idx = 0
    halted = False

    def signal_at(i: int) -> int:
        if np.isnan(fast[i]) or np.isnan(slow[i]) or np.isnan(fast[i - 1]):
            return strat.NONE
        up = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]
        dn = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]
        if scfg.use_rsi_filter and not np.isnan(rsi[i]):
            if up and rsi[i] < scfg.rsi_buy_min:
                up = False
            if dn and rsi[i] > scfg.rsi_sell_max:
                dn = False
        return strat.BUY if up else strat.SELL if dn else strat.NONE

    def close_trade(exit_price: float, j: int, reason: str) -> None:
        nonlocal equity, in_pos
        gross = qty * (exit_price - entry) if side == strat.BUY else qty * (entry - exit_price)
        fees = qty * cost * (entry + exit_price)
        pnl = gross - fees
        equity += pnl
        r = pnl / risk_at_entry if risk_at_entry > 0 else 0.0
        trades.append(Trade(side, entry_idx, j, entry, exit_price, qty, pnl, r, reason))
        in_pos = False

    for i in range(warmup, n - 1):
        # ---- manage an open position on bar i ----
        if in_pos:
            exited = False
            if side == strat.BUY:
                if lo[i] <= sl:
                    close_trade(sl, i, "stop")
                    exited = True
                elif hi[i] >= tp:
                    close_trade(tp, i, "target")
                    exited = True
            else:
                if hi[i] >= sl:
                    close_trade(sl, i, "stop")
                    exited = True
                elif lo[i] <= tp:
                    close_trade(tp, i, "target")
                    exited = True

            if not exited:
                a = atr[i] if not np.isnan(atr[i]) else 0.0
                if a > 0:
                    profit = (cl[i] - entry) if side == strat.BUY else (entry - cl[i])
                    if side == strat.BUY:
                        if params.use_breakeven and profit >= params.be_trigger_atr * a:
                            sl = max(sl, entry + params.be_lock_atr * a)
                        if params.use_trailing and profit >= params.trail_start_atr * a:
                            sl = max(sl, cl[i] - params.trail_step_atr * a)
                    else:
                        if params.use_breakeven and profit >= params.be_trigger_atr * a:
                            sl = min(sl, entry - params.be_lock_atr * a)
                        if params.use_trailing and profit >= params.trail_start_atr * a:
                            sl = min(sl, cl[i] + params.trail_step_atr * a)

        eq_points.append(equity)

        if params.max_total_dd_pct > 0:
            peak = max(eq_points)
            if (peak - equity) / peak * 100.0 >= params.max_total_dd_pct:
                halted = True

        # ---- look for a new entry (signal on bar i, fill at open of i+1) ----
        if not in_pos and not halted:
            sig = signal_at(i)
            a = atr[i]
            if sig != strat.NONE and not np.isnan(a) and a > 0:
                entry = op[i + 1]
                sl, tp = strat.stop_levels(sig, entry, a, scfg.sl_atr, scfg.tp_atr)
                sl_dist = abs(entry - sl)
                if sl_dist > 0:
                    risk_at_entry = equity * params.risk_percent / 100.0
                    qty = risk_at_entry / sl_dist
                    side = sig
                    entry_idx = i + 1
                    in_pos = True

    result = BacktestResult(ticker=ticker, trades=trades,
                            equity_curve=pd.Series(eq_points))
    return result


def format_report(results: list[BacktestResult], params: BacktestParams) -> str:
    lines = []
    lines.append("| Instrument | Trades | Win % | Profit factor | Total return % | Max DD % | Expectancy (R) |")
    lines.append("|------------|--------|-------|---------------|----------------|----------|----------------|")
    for r in results:
        pf = "inf" if r.profit_factor == float("inf") else f"{r.profit_factor:.2f}"
        lines.append(
            f"| {r.ticker} | {r.n_trades} | {r.win_rate:.1f} | {pf} | "
            f"{r.total_return_pct:.1f} | {r.max_drawdown_pct:.1f} | {r.expectancy_r:.2f} |"
        )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Backtest the PropFirm SuperEA strategy.")
    p.add_argument("--tickers", nargs="+",
                   default=["EURUSD=X", "GBPUSD=X", "GC=F"],
                   help="Yahoo Finance tickers (GC=F = gold futures, proxy for XAUUSD).")
    p.add_argument("--start", default="2010-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--risk", type=float, default=1.0, help="Risk %% per trade")
    p.add_argument("--fast", type=int, default=20)
    p.add_argument("--slow", type=int, default=50)
    p.add_argument("--no-rsi", action="store_true")
    args = p.parse_args()

    scfg = StrategyConfig(fast_ema=args.fast, slow_ema=args.slow,
                          use_rsi_filter=not args.no_rsi)
    params = BacktestParams(risk_percent=args.risk)

    results = []
    for t in args.tickers:
        df = load_data(t, args.start, args.end)
        res = run_backtest(df, scfg, params, ticker=t)
        results.append(res)
        print(f"{t}: {res.n_trades} trades, win {res.win_rate:.1f}%, "
              f"PF {res.profit_factor:.2f}, return {res.total_return_pct:.1f}%, "
              f"maxDD {res.max_drawdown_pct:.1f}%")

    print()
    print(format_report(results, params))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
