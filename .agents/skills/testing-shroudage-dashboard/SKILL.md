---
name: testing-shroudage-dashboard
description: Run and test the SHROUDAGE dashboard (Flask) end-to-end, including the Start/Stop trading engine and live TradeLocker mode. Use when verifying dashboard UI/API changes.
---

# Testing the SHROUDAGE dashboard

The dashboard (`dashboard/`) is a Flask app that reuses `tradelocker_bot/`'s real
strategy/risk code. It has a demo mode (synthetic data, no creds) and a live mode
(real TradeLocker account).

## Setup / run

```bash
cd MT5-PropFirm-SuperEA
python -m venv .venv && . .venv/bin/activate   # if not already present
pip install -r tradelocker_bot/requirements.txt -r dashboard/requirements.txt
python -m dashboard.app                          # demo mode, http://localhost:8787
```

- Unit tests + lint: `python -m pytest dashboard/tests tradelocker_bot -q` and
  `python -m pyflakes dashboard tradelocker_bot`.
- A different port: `DASH_PORT=8788 python -m dashboard.app`.
- Force SAFE MODE for testing: launch with a tiny limit, e.g.
  `SHROUD_MODE=LIVE SHROUD_DAILY_LOSS=0.1 python -m dashboard.app` — demo daily
  loss (~0.57%) then exceeds the limit and `system_status` becomes `SAFE MODE`.

## Endpoints (fast smoke test without the browser)

```bash
curl -s localhost:8787/healthz                       # {"ok": true}
curl -s -X POST localhost:8787/api/start | python3 -m json.tool   # engine.running -> true
curl -s localhost:8787/api/state | python3 -c 'import sys,json;print(json.load(sys.stdin)["engine"])'
curl -s -X POST localhost:8787/api/stop              # engine.running -> false
```

`/api/state` returns keys: account, agents, decision, engine, generated_at,
market, performance, positions, risk, source, system_status.

## Start/Stop trading engine (the buttons)

- Header buttons `#btn-start` / `#btn-stop` POST to `/api/start` / `/api/stop`.
- The engine (`dashboard/engine.py`, singleton `ENGINE`) runs a background thread.
  In **DEMO** mode it scans on cadence but places NO orders; in **LIVE** mode
  (`SHROUD_LIVE=true` + valid `TL_*`) it runs the real `TradeLockerBot` loop.
- What to assert in the UI:
  - Precondition: engine pill `STOPPED`, Start enabled, Stop disabled, Execution
    Agent `WAITING; engine STOPPED`.
  - After Start: pill `RUNNING`, Start disabled / Stop enabled, cycle counter
    increments over time, Execution Agent `RUNNING; engine RUNNING`.
  - After Stop: pill `STOPPED`, cycle counter freezes, buttons swap back.
  - Demo cycle cadence is `min(TL_POLL_SECONDS, 5s)`; set `TL_POLL_SECONDS=1` to
    speed up tests. UI auto-refreshes every 5s (`REFRESH_MS` in app.js).
- A broken impl would leave cycles at 0, not toggle button disabled-state, or
  leave Execution Agent WAITING — so cycle-increment + button-state are the
  high-signal checks.

## Live TradeLocker mode

- `SHROUD_LIVE=true` with `TL_ENVIRONMENT`, `TL_USERNAME`, `TL_PASSWORD`,
  `TL_SERVER`, `TL_ACCOUNT_ID`. Demo host is `https://demo.tradelocker.com`,
  account on GATESFX server.
- Known gotcha: login may fail with `Incorrect email or password` if the demo
  password was reset — the saved `TL_PASSWORD` secret then no longer matches.
  The dashboard degrades gracefully (records `source.errors`, no crash) rather
  than showing live data. If you need live data, request fresh creds from the user.
- `TL_ACCOUNT_ID` is the account `id` (e.g. 1997554), NOT the short `accNum`
  (which was `1`). The bot (`bot.connect()`) tries `acc_num=` first then falls
  back to `account_id=` — this fix is required for live login (was PR #4). If
  login fails with `acc_num '<id>' not found in all_accounts`, that fix is missing.
- **First live `/api/state` fetch is SLOW** (can be 30–90s) because it pulls price
  history for every symbol concurrently. To keep the browser responsive, launch
  with fewer symbols and a longer cache TTL, e.g.
  `SHROUD_SYMBOLS=XAUUSD,GBPUSD,EURUSD SHROUD_REFRESH_SECS=20`. Warm the cache
  with one `curl --max-time 90 localhost:8787/api/state` before opening the browser.
- To make the LIVE engine actually run gold cycles, also set the engine's trade
  config in the same env: `TL_SYMBOL=XAUUSD.R TL_RESOLUTION=1D TL_LOOKBACK=400D
  TL_FAST_EMA=20 TL_SLOW_EMA=100 TL_SL_ATR=2.0 TL_TP_ATR=4.0 TL_RISK_PERCENT=2.0
  TL_CONTRACT_SIZE=100 TL_DRY_RUN=false TL_POLL_SECONDS=12`.
- On a **daily** timeframe a new order only fires on a fresh EMA20/100 crossover
  at a new daily bar, so a short recording usually shows the engine RUNNING and
  managing the account but placing NO new order — that is correct, not a failure.
  Prove actual order placement separately via shell (place + close a 0.01 lot).
- After a VM/process restart, env vars and the running server are gone (relaunch
  needed) but saved secrets like `TL_PASSWORD` persist in the shell env — check
  `[ -n "$TL_PASSWORD" ]` before re-prompting the user.
- LIVE mode needs both PR #5 (dashboard) and PR #4 (account-selection fix) merged.

## Devin Secrets Needed
- `TL_USERNAME`, `TL_PASSWORD`, `TL_SERVER` (and optionally `TL_ACCOUNT_ID`,
  `TL_ENVIRONMENT`) — only for LIVE mode. Demo mode needs none.
