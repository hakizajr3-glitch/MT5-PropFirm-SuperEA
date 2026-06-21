"""Quick parameter optimization grid for EURUSD.

Usage: python -m tradelocker_bot.optimize
"""

import itertools
import sys

from .backtest import load_data, run_backtest, BacktestParams
from .config import StrategyConfig

df = load_data("EURUSD=X", "2010-01-01", None)
results = []

fasts = [5, 8, 10, 12, 15]
slows = [20, 24, 26, 30, 40, 50]
sl_atrs = [1.0, 1.5, 2.0, 2.5]
tp_atrs = [1.5, 2.0, 2.5, 3.0, 4.0]
rsis = [True, False]

total = len(fasts) * len(slows) * len(sl_atrs) * len(tp_atrs) * len(rsis)
done = 0

for f, s, sl, tp, rsi in itertools.product(fasts, slows, sl_atrs, tp_atrs, rsis):
    if s <= f + 5:
        continue
    scfg = StrategyConfig(
        fast_ema=f, slow_ema=s,
        sl_atr=sl, tp_atr=tp,
        use_rsi_filter=rsi,
    )
    params = BacktestParams()
    res = run_backtest(df, scfg, params, ticker="EURUSD=X")
    done += 1
    if done % 40 == 0:
        print(f"  ... {done}/{total}", file=sys.stderr)
    results.append((f, s, sl, tp, rsi, res))

def score(r):
    if r.n_trades < 15 or r.total_return_pct <= 0:
        return -9999
    pf = r.profit_factor if r.profit_factor != float("inf") else 10
    return pf * r.total_return_pct - r.max_drawdown_pct

results.sort(key=lambda x: score(x[-1]), reverse=True)

print(f"{'FAST':>4} {'SLOW':>4} {'SL':>4} {'TP':>4} {'RSI':>5} | {'Trades':>6} {'Win%':>5} {'PF':>5} {'Ret%':>6} {'DD%':>5} {'Score':>7}")
print("-" * 72)
for f, s, sl, tp, rsi, r in results[:30]:
    pf = f"{r.profit_factor:.2f}" if r.profit_factor != float("inf") else " inf"
    print(f"{f:>4} {s:>4} {sl:>4.1f} {tp:>4.1f} {str(rsi):>5} | {r.n_trades:>6} {r.win_rate:>5.1f} {pf:>5} {r.total_return_pct:>6.1f} {r.max_drawdown_pct:>5.1f} {score(r):>7.1f}")
