# Strategy Specifications

This document defines the exact entry/exit rules implemented by both the MT5
Expert Advisor (`PropFirm_SuperEA.mq5`) and the TradeLocker bot
(`tradelocker_bot/`).

## Indicators
- **EMA fast** — default period 20, on close price.
- **EMA slow** — default period 50, on close price.
- **RSI** — default period 14, on close price (optional filter).
- **ATR** — default period 14, used for stop placement and sizing.

All signals are evaluated on **closed bars only** (the most recent completed
bar and the one before it), so they do not repaint.

## Entry Rules
A position is opened when, on the just-closed bar:

1. **Buy:** the fast EMA crosses **above** the slow EMA
   (`fast[-2] <= slow[-2]` and `fast[-1] > slow[-1]`), **and**
   (if the RSI filter is on) RSI ≥ `RSIBuyMin` (default 50).
2. **Sell:** the fast EMA crosses **below** the slow EMA
   (`fast[-2] >= slow[-2]` and `fast[-1] < slow[-1]`), **and**
   (if the RSI filter is on) RSI ≤ `RSISellMax` (default 50).
3. Entry is allowed only if: within the trading session, spread is acceptable,
   and the number of open positions is below the configured maximum.

## Exit Rules
1. **Stop loss:** entry ∓ `SL_ATR × ATR` (default 1.5 × ATR).
2. **Take profit:** entry ± `TP_ATR × ATR` (default 2.5 × ATR).
3. **Break-even:** once price moves a configured amount in profit, the stop is
   moved to entry (plus a small locked buffer).
4. **Trailing stop:** once price moves further in profit, the stop trails behind
   price at a configured distance.
5. **Forced exit:** all positions are closed if a prop-firm risk limit is
   breached (see Risk Management).

## Risk Management
- **Per-trade risk:** position size is computed so the distance to the stop loss
  equals `RiskPercent` of balance (default 1%). A fixed-size mode is also
  available.
- **Daily loss limit:** when the day's loss reaches `MaxDailyLossPct` of the
  day-start equity (default 5%), new entries stop for the day and (optionally)
  open positions are closed. The baseline resets at the start of each new day.
- **Max total drawdown:** when equity falls `MaxTotalDDPct` from its peak
  (default 10%), trading halts and (optionally) positions are closed.
- **Session filter:** trading is restricted to configured hours and weekdays.
- **Spread filter:** entries are skipped when the spread is too wide (MT5).

## Notes
- The two implementations are kept behaviourally identical. The MT5 EA expresses
  break-even/trailing distances in **points**; the TradeLocker bot expresses
  them as **ATR multiples** (so they are instrument-agnostic). Tune them to your
  instrument.
- Always validate parameter changes with a backtest and on a demo/challenge
  account before going live.
