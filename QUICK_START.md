# Quick Start

Pick the platform your broker / prop firm uses.

## MetaTrader 5

**Prerequisites:** MetaTrader 5 installed, an MT5 trading account.

1. **Install the EA**
   - In MT5: `File` → `Open Data Folder`, then go to `MQL5/Experts/`.
   - Copy `PropFirm_SuperEA.mq5` into that folder.
2. **Compile**
   - Open MetaEditor (`Tools` → `MetaQuotes Language Editor`), open
     `PropFirm_SuperEA.mq5`, and press **Compile** (F7). It should compile with
     0 errors.
3. **Attach to a chart**
   - Back in MT5, open `Navigator` (Ctrl+N) → `Expert Advisors` →
     drag **PropFirm_SuperEA** onto a chart (e.g. EURUSD, H1).
   - In the dialog, allow **Algo Trading**, set your inputs, and click OK.
   - Make sure the **Algo Trading** toolbar button is enabled.
4. **Configure** the inputs to match your prop firm's rules — see
   [INPUT_GUIDE.md](INPUT_GUIDE.md). Defaults: 1% risk/trade, 5% daily loss
   limit, 10% max drawdown.
5. **Backtest first** in the Strategy Tester before live use — see
   [BACKTESTING_GUIDE.md](BACKTESTING_GUIDE.md).

## TradeLocker

**Prerequisites:** Python 3.10+, a TradeLocker account (demo first!).

1. **Install dependencies**
   ```bash
   cd tradelocker_bot
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Configure**
   ```bash
   cp .env.example .env
   # edit .env: TL_USERNAME, TL_PASSWORD, TL_SERVER, TL_SYMBOL, risk limits, ...
   ```
   Keep `TL_ENVIRONMENT=https://demo.tradelocker.com` and `TL_DRY_RUN=true`
   while testing.
3. **Run**
   ```bash
   cd ..                       # repo root
   python -m tradelocker_bot.run
   ```
   In dry-run mode it logs the signals and orders it *would* send without
   placing them. When you're satisfied, set `TL_DRY_RUN=false` (and only switch
   to the live host once validated on demo).
4. **Run the tests** (optional):
   ```bash
   pip install pytest
   python -m pytest tradelocker_bot/tests -q
   ```

See [INPUT_GUIDE.md](INPUT_GUIDE.md) for every setting and
[STRATEGY_SPECS.md](STRATEGY_SPECS.md) for the strategy rules.

> **Always validate on a demo / challenge account before risking real or funded
> capital.**
