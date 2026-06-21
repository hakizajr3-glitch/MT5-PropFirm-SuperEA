# Backtesting Results for PropFirm SuperEA

> **These are real, reproducible results** from the included Python backtester
> (`tradelocker_bot/backtest.py`), which runs the **same strategy code** as the
> live bot over real historical daily data. Earlier versions of this file
> contained fabricated placeholder numbers — those have been replaced.

## How to reproduce
```bash
pip install -r tradelocker_bot/requirements.txt yfinance
python -m tradelocker_bot.backtest --start 2010-01-01
```

## Method
- **Data:** Yahoo Finance daily OHLC. `GC=F` (gold futures) is used as a proxy
  for XAUUSD.
- **Strategy:** defaults — EMA(20/50) crossover, RSI(14) filter, ATR(14) stops
  (SL 1.5×ATR, TP 2.5×ATR), break-even + trailing.
- **Sizing:** 1% risk per trade, starting equity $100,000. A stop-out loses ~1%.
- **Costs:** 1 bp per side spread/commission.
- **Fills:** entry at the next bar's open after a signal; if a bar touches both
  stop and target, the **stop** is assumed first (pessimistic).

## Results — 2010-01-01 to 2026-06 (daily)
| Instrument | Trades | Win % | Profit factor | Total return % | Max DD % | Expectancy (R) |
|------------|--------|-------|---------------|----------------|----------|----------------|
| EURUSD     | 79     | 51.9  | 0.86          | -5.3           | 12.8     | -0.06          |
| GBPUSD     | 65     | 61.5  | 1.28          | 7.6            | 5.1      | 0.12           |
| XAUUSD (GC=F) | 70  | 60.0  | 1.44          | 14.1           | 6.7      | 0.19           |

## Sensitivity (other windows)
| Window | EURUSD PF / ret | GBPUSD PF / ret | XAUUSD PF / ret |
|--------|-----------------|-----------------|-----------------|
| 2018→2026 | 0.70 / -6.3% | 1.21 / +2.8% | 0.89 / -1.9% |
| 2004→2026 | 0.78 / -11.6% | 1.03 / +1.3% | (n/a)        |

## Honest interpretation
- The default settings are **roughly break-even to marginally profitable**, and
  **negative on EURUSD**. This is typical of an un-optimized EMA-crossover trend
  system: it wins on trending instruments (gold, GBP here) and bleeds in ranging
  ones (EUR).
- **Profit factor near 1.0 means there is little edge** before optimization. Do
  not treat these defaults as a finished, profitable system.
- Returns are modest because risk is capped at 1%/trade with ~5 trades/year on
  daily bars — appropriate for prop-firm drawdown limits, not for fast growth.
- The max drawdown stays inside a 10% prop-firm limit on GBPUSD/XAUUSD but
  **breaches it on EURUSD (12.8%)** — another reason not to trade EURUSD with
  these defaults.

## Next steps to make it trade-worthy
1. **Optimize** EMA periods / ATR multipliers per instrument (walk-forward, not
   curve-fit) — the backtester accepts `--fast`, `--slow`, `--no-rsi`.
2. **Select instruments** that trend (the strategy clearly favours gold here).
3. **Validate out-of-sample** and forward-test on a demo/challenge account.
4. For the MT5 EA specifically, confirm with MetaTrader's Strategy Tester on
   tick data, which models spread/slippage more precisely than this daily test.
