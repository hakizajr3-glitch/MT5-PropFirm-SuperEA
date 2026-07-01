# Strategy Specifications

This document defines the exact entry/exit rules implemented by both the MT5
Expert Advisor (`PropFirm_SuperEA.mq5`) and the TradeLocker bot
(`tradelocker_bot/`).

## Indicators (core)
- **EMA fast** — default period 20, on close price.
- **EMA slow** — default period 50, on close price.
- **RSI** — default period 14, on close price (optional filter).
- **ATR** — default period 14, used for stop placement and sizing.

## Enhanced Indicators (v4.0)
All optional; disabled by default for backward compatibility.

- **ADX** — Average Directional Index (period 14). Measures trend strength
  (0-100). When enabled, trades are only taken when ADX >= `ADXMin` (default
  20), filtering out ranging/choppy markets.
- **MACD** — histogram (12/26/9). When enabled, the MACD histogram must agree
  with trade direction (positive for buys, negative for sells).
- **EMA 200** — long-term trend alignment. When enabled, buys require price
  above EMA(200), sells require price below.
- **Volatility ratio** — current ATR / average ATR over a lookback window.
  When enabled, trades are rejected if volatility is abnormally low (< 0.5x)
  or high (> 2.5x).

All signals are evaluated on **closed bars only** (the most recent completed
bar and the one before it), so they do not repaint.

## Entry Rules
A position is opened when, on the just-closed bar:

1. **Buy:** the fast EMA crosses **above** the slow EMA
   (`fast[-2] <= slow[-2]` and `fast[-1] > slow[-1]`), **and**
   (if the RSI filter is on) RSI >= `RSIBuyMin` (default 50).
2. **Sell:** the fast EMA crosses **below** the slow EMA
   (`fast[-2] >= slow[-2]` and `fast[-1] < slow[-1]`), **and**
   (if the RSI filter is on) RSI <= `RSISellMax` (default 50).
3. **v4.0 enhanced gates** (each independently toggleable):
   - ADX must be >= `ADXMin`
   - MACD histogram must agree with direction
   - Price must be on correct side of EMA(200)
   - Volatility ratio must be within `[VolMin, VolMax]`
4. Entry is allowed only if: within the trading session, spread is acceptable,
   and the number of open positions is below the configured maximum.

A **signal strength score** (0-100) is computed from how many enhanced filters
confirm the signal. This score feeds into adaptive position sizing (v4.0).

## Exit Rules
1. **Stop loss:** entry +/- `SL_ATR x ATR` (default 1.5 x ATR).
2. **Take profit:** entry +/- `TP_ATR x ATR` (default 2.5 x ATR).
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
- **Adaptive sizing (v4.0):** when enabled, risk % scales between a min and max
  based on signal strength. Full-confirmation signals risk more; weak signals
  risk less.
- **DD cushion (v4.0):** when enabled, risk % is progressively reduced as
  drawdown approaches the maximum limit. Starts reducing at a configurable
  threshold (default 50% of DD budget used) and scales down to 25% of base
  risk at the limit.
- **Daily loss limit:** when the day's loss reaches `MaxDailyLossPct` of the
  day-start equity (default 5%), new entries stop for the day and (optionally)
  open positions are closed. The baseline resets at the start of each new day.
- **Max total drawdown:** when equity falls `MaxTotalDDPct` from its peak
  (default 10%), trading halts and (optionally) positions are closed.
- **Session filter:** trading is restricted to configured hours and weekdays.
- **Spread filter:** entries are skipped when the spread is too wide (MT5).

## Prop-Firm Profiles (v4.0)
Pre-configured risk profiles with safety buffers below the hard limits:

| Profile | Daily Loss | Total DD | Risk/Trade | Notes |
|---------|-----------|----------|------------|-------|
| **FTMO** | 4.5% (5% limit) | 9.0% (10% limit) | 1.0% | DD cushion on |
| **The5ers** | off | 5.0% (6% limit) | 0.75% | Tighter DD cushion (40%) |
| **The Funded Trader** | 4.5% | 9.0% | 1.0% | Same as FTMO profile |
| **TradeLocker Generic** | 4.5% | 9.0% | 1.0% | Default for TL-based firms |

## Notes
- The two implementations are kept behaviourally identical. The MT5 EA expresses
  break-even/trailing distances in **points**; the TradeLocker bot expresses
  them as **ATR multiples** (so they are instrument-agnostic). Tune them to your
  instrument.
- v4.0 enhanced filters are disabled by default. Existing configs work unchanged.
- Always validate parameter changes with a backtest and on a demo/challenge
  account before going live.
