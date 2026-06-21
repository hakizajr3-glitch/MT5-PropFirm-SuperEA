"""Performance metrics computed from a list of closed trades.

Pure functions so they unit test without any network. A "trade" is a dict with
at least a numeric ``pnl``; optional ``rr`` (realized reward:risk) improves the
average-RR figure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Performance:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0          # %
    loss_rate: float = 0.0         # %
    profit_factor: float = 0.0     # gross win / gross loss
    avg_rr: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_pnl: float = 0.0
    max_drawdown: float = 0.0      # currency, on realized equity curve
    max_drawdown_pct: float = 0.0  # % of starting equity
    sharpe: float = 0.0            # per-trade Sharpe (unannualised)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def compute_performance(trades: list[dict], starting_equity: float = 0.0) -> Performance:
    p = Performance()
    if not trades:
        return p

    pnls = [float(t.get("pnl", 0.0)) for t in trades]
    rrs = [float(t["rr"]) for t in trades if t.get("rr") is not None]

    p.trades = len(pnls)
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    p.wins = len(wins)
    p.losses = len(losses)
    p.win_rate = round(100.0 * p.wins / p.trades, 2)
    p.loss_rate = round(100.0 * p.losses / p.trades, 2)
    p.gross_profit = round(sum(wins), 2)
    p.gross_loss = round(abs(sum(losses)), 2)
    p.net_pnl = round(sum(pnls), 2)
    p.profit_factor = round(p.gross_profit / p.gross_loss, 2) if p.gross_loss > 0 else (
        float("inf") if p.gross_profit > 0 else 0.0)
    p.avg_rr = round(sum(rrs) / len(rrs), 2) if rrs else 0.0

    # realized equity curve -> max drawdown
    equity = starting_equity
    peak = starting_equity if starting_equity > 0 else 0.0
    max_dd = 0.0
    for x in pnls:
        equity += x
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    p.max_drawdown = round(max_dd, 2)
    p.max_drawdown_pct = round(100.0 * max_dd / starting_equity, 2) if starting_equity > 0 else 0.0

    # per-trade Sharpe (mean/std of pnl); informational, not annualised
    if len(pnls) > 1:
        mean = sum(pnls) / len(pnls)
        var = sum((x - mean) ** 2 for x in pnls) / (len(pnls) - 1)
        std = math.sqrt(var)
        p.sharpe = round(mean / std, 2) if std > 0 else 0.0
    return p
