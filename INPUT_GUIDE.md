# Input / Parameter Guide

Parameters for both platforms. The MT5 column is the EA input name; the
TradeLocker column is the environment variable used by the Python bot
(see `tradelocker_bot/.env.example`).

## Strategy
| MT5 input | TradeLocker env | Default | Description |
|-----------|-----------------|---------|-------------|
| `InpFastEMA` | `TL_FAST_EMA` | 20 | Fast EMA period |
| `InpSlowEMA` | `TL_SLOW_EMA` | 50 | Slow EMA period (must be > fast) |
| `InpATRPeriod` | `TL_ATR_PERIOD` | 14 | ATR period |
| `InpSL_ATR` | `TL_SL_ATR` | 1.5 | Stop loss = ATR × this |
| `InpTP_ATR` | `TL_TP_ATR` | 2.5 | Take profit = ATR × this |
| `InpUseRSIFilter` | `TL_USE_RSI` | true | Enable RSI trend filter |
| `InpRSIPeriod` | `TL_RSI_PERIOD` | 14 | RSI period |
| `InpRSIBuyMin` | `TL_RSI_BUY_MIN` | 50 | Buy only if RSI ≥ this |
| `InpRSISellMax` | `TL_RSI_SELL_MAX` | 50 | Sell only if RSI ≤ this |

## Money / Risk
| MT5 input | TradeLocker env | Default | Description |
|-----------|-----------------|---------|-------------|
| `InpUseRiskPercent` | `TL_USE_RISK_PERCENT` | true | Size by risk % (else fixed) |
| `InpRiskPercent` | `TL_RISK_PERCENT` | 1.0 | Risk per trade (% of balance) |
| `InpFixedLot` | `TL_FIXED_QTY` | 0.10 | Fixed size when risk % is off |
| `InpMaxOpenPositions` | `TL_MAX_OPEN` | 1 | Max simultaneous positions |
| `InpMaxSpreadPoints` | (MT5 only) | 50 | Max spread in points (0 = off) |
| (auto from symbol) | `TL_CONTRACT_SIZE` | 100000 | Money per 1.0 price move per unit, used for sizing |

## Prop-firm guardrails
| MT5 input | TradeLocker env | Default | Description |
|-----------|-----------------|---------|-------------|
| `InpMaxDailyLossPct` | `TL_MAX_DAILY_LOSS_PCT` | 5.0 | Daily loss limit (% of day-start equity) |
| `InpMaxTotalDDPct` | `TL_MAX_TOTAL_DD_PCT` | 10.0 | Max total drawdown (% from peak equity) |
| `InpCloseOnDailyStop` | `TL_CLOSE_ON_DAILY_STOP` | true | Flatten when daily limit hit |
| `InpCloseOnTotalStop` | `TL_CLOSE_ON_TOTAL_STOP` | true | Flatten when total DD hit |

## Session filter (server / UTC hours)
| MT5 input | TradeLocker env | Default | Description |
|-----------|-----------------|---------|-------------|
| `InpUseSession` | `TL_USE_SESSION` | true | Restrict trading hours |
| `InpStartHour` | `TL_START_HOUR` | 7 | Session start hour |
| `InpEndHour` | `TL_END_HOUR` | 20 | Session end hour |
| `InpTradeMonday` | `TL_TRADE_MONDAY` | true | Allow Monday |
| `InpTradeFriday` | `TL_TRADE_FRIDAY` | true | Allow Friday |

## Exit management
| MT5 input | TradeLocker env | Default | Description |
|-----------|-----------------|---------|-------------|
| `InpUseBreakEven` | `TL_USE_BREAKEVEN` | true | Enable break-even |
| `InpBE_TriggerPoints` | `TL_BE_TRIGGER_ATR` | 150 pts / 1.0 ATR | Profit before break-even |
| `InpBE_LockPoints` | `TL_BE_LOCK_ATR` | 20 pts / 0.1 ATR | Buffer locked at break-even |
| `InpUseTrailing` | `TL_USE_TRAILING` | true | Enable trailing stop |
| `InpTrailStartPoints` | `TL_TRAIL_START_ATR` | 200 pts / 1.5 ATR | Profit before trailing starts |
| `InpTrailStepPoints` | `TL_TRAIL_STEP_ATR` | 100 pts / 1.0 ATR | Trailing distance |

> The MT5 EA measures break-even/trailing in **points**; the TradeLocker bot
> measures them in **ATR multiples**. Pick values appropriate to your
> instrument's volatility.

## Tuning tips
- **Match your prop firm exactly.** Set `MaxDailyLossPct` / `MaxTotalDDPct`
  slightly *tighter* than the firm's hard limits to leave a safety buffer.
- **Higher timeframes** (1H/4H) produce fewer, higher-quality signals and are
  generally safer for prop accounts than 1m/5m.
- **Backtest first.** Optimize EMA periods and ATR multipliers in the MT5
  Strategy Tester, then forward-test on demo before going live.
