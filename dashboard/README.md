# SHROUDAGE Dashboard

A read-only web control panel for this repo's TradeLocker bot. It reuses the
bot's **real** strategy and risk code (`tradelocker_bot/`) so what you see on the
dashboard matches what the bot actually trades — no separate, drifting copy of
the logic.

## What it shows

- **System status** — DRY RUN / LIVE / SAFE MODE / HALTED (risk breaches force SAFE MODE).
- **Account** — balance, equity, open / daily / closed PnL (live from TradeLocker).
- **Performance** — win rate, profit factor, avg RR, Sharpe, max drawdown, net PnL.
- **Risk & prop limits** — daily-loss-used and drawdown-used gauges against the
  SHROUDAGE limits (0.5% risk/trade, 1% hard cap, 3% daily, 8% max DD).
- **Open positions** — symbol, side, entry, SL/TP, qty, PnL, responsible agent.
- **Market view & scanner** — per symbol regime (TRENDING / RANGING / HIGH-LOW
  VOLATILITY) with trend / momentum / volatility / confidence scores, plus the
  **Trend Agent** and **Range Agent** decisions, computed from real price data
  with EMA20/50, RSI14, ADX14, ATR14 and Bollinger Bands.
- **Agent network** — RUNNING / WAITING / OFFLINE / ERROR for every agent.

## Run

```bash
pip install -r tradelocker_bot/requirements.txt -r dashboard/requirements.txt

# Demo data (no credentials needed) — great for a first look:
python -m dashboard.app
# open http://localhost:8787

# Live, against your TradeLocker account (reads TL_* from .env / environment):
SHROUD_LIVE=true python -m dashboard.app
```

## Configuration (environment variables)

| Var | Default | Meaning |
|---|---|---|
| `SHROUD_LIVE` | `false` | `true` → read the live TradeLocker account (needs `TL_*`) |
| `SHROUD_MODE` | `DRY RUN` | Requested mode label (`LIVE`, `SAFE MODE`, `HALTED`) |
| `SHROUD_SYMBOLS` | `EURUSD,GBPUSD,XAUUSD,NAS100,US30,BTCUSD` | Symbols to scan |
| `SHROUD_RISK_PER_TRADE` | `0.5` | Risk per trade % shown on the risk panel |
| `SHROUD_RISK_MAX` | `1.0` | Hard risk cap % |
| `SHROUD_DAILY_LOSS` | `3.0` | Daily loss limit % (breach → SAFE MODE) |
| `SHROUD_MAX_DD` | `8.0` | Max drawdown % (breach → SAFE MODE) |
| `SHROUD_NEWS_FEED` | _(unset)_ | Set when an economic-calendar feed is wired in |
| `SHROUD_LLM` | _(unset)_ | Set when an LLM is wired in for reflection/learning |
| `DASH_HOST` / `DASH_PORT` | `0.0.0.0` / `8787` | Bind address |

The `TL_*` credentials are the same ones the bot uses — see
`tradelocker_bot/.env.example`.

## Honesty about scope

This dashboard is a **monitoring / decision-support** layer. It does not place
orders itself — execution stays in `tradelocker_bot`. The **News**, **Reflection**
and **Learning** agents require an economic-calendar feed and an LLM respectively;
until those are configured they are shown as `OFFLINE` with a clear reason rather
than displaying fabricated data. Everything else (account, performance, positions,
market regime, risk) is computed from real data.
