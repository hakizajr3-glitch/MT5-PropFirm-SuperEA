# PropFirm SuperEA

A trend-following trading strategy with **prop-firm risk controls**, available
for **two platforms**:

| Platform | What it is | Where it lives |
|----------|------------|----------------|
| **MetaTrader 5** | An Expert Advisor (`.mq5`) you compile and attach to a chart | [`PropFirm_SuperEA.mq5`](PropFirm_SuperEA.mq5) |
| **TradeLocker** | A Python bot that trades via TradeLocker's REST API | [`tradelocker_bot/`](tradelocker_bot/) |

Both implementations share the **same strategy and the same prop-firm
guardrails**, so you can run whichever platform your broker / prop firm uses.

> **Why two codebases?** TradeLocker does **not** run MetaTrader Expert
> Advisors. MQL5 (`.mq5`) only runs inside MetaTrader 5. To trade on
> TradeLocker the strategy has to talk to TradeLocker's own API, which is what
> the Python bot does.

## The strategy

- **Trend entries:** EMA(20) crosses EMA(50) — buy on an up-cross, sell on a
  down-cross (evaluated on closed bars only, so no repainting).
- **Trend filter:** optional RSI(14) filter — only buy when RSI ≥ 50, only sell
  when RSI ≤ 50.
- **Volatility-based stops:** stop loss and take profit are placed at multiples
  of ATR(14) (default SL = 1.5×ATR, TP = 2.5×ATR).
- **Exit management:** automatic break-even and trailing stop.

See [STRATEGY_SPECS.md](STRATEGY_SPECS.md) for the full rules.

## Prop-firm guardrails

These are the rules that keep you inside a funded/challenge account's limits.
They are enforced **automatically** on both platforms:

- **Risk-% position sizing** — each trade risks a fixed % of balance (default 1%).
- **Daily loss limit** — stop trading (and optionally flatten) once the day's
  loss reaches a % of the day-start equity (default 5%).
- **Max total drawdown** — stop trading once equity falls a % from its peak
  (default 10%).
- **Max open positions**, **spread filter**, and a **session/time-of-day filter**.

Defaults match a common "5% daily / 10% total" prop-firm profile. Change them to
match your firm's exact rules — see [INPUT_GUIDE.md](INPUT_GUIDE.md).

> **Risk warning:** Automated trading carries substantial risk. The
> guardrails reduce but do not eliminate the chance of breaching a prop-firm
> rule (e.g. weekend gaps, slippage, broker outages). Always validate on a demo
> / challenge account first.

## Quick start

- **MetaTrader 5:** see [QUICK_START.md](QUICK_START.md#metatrader-5).
- **TradeLocker:** see [QUICK_START.md](QUICK_START.md#tradelocker) and
  [`tradelocker_bot/`](tradelocker_bot/).

## Backtesting

The included `BACKTESTING_RESULTS*.md` files are **illustrative templates**, not
verified results — run your own backtests in the MT5 Strategy Tester before
trading. See [BACKTESTING_GUIDE.md](BACKTESTING_GUIDE.md).

## License

MIT — see the repository for details.
