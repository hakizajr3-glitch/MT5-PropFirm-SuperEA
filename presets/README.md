# MT5 presets (`.set` files)

Optimized, prop-safe input sets for `PropFirm_SuperEA.mq5`. Backtested on daily
data (2010-2026) and validated out-of-sample. They keep max drawdown under the
10% prop-firm limit.

| File | Instrument | EMA | SL/TP ×ATR | Risk | Backtest PF / Win / MaxDD |
|------|------------|-----|------------|------|---------------------------|
| `XAUUSD_gold.set` | Gold / XAUUSD | 20/100 | 2.0 / 4.0 | 2.0% | ~2.0 / ~72% / ~6% |
| `GBPUSD.set` | GBPUSD | 15/100 | 1.0 / 4.0 | 1.5% | ~1.9 / ~58% / ~8% |

## How to load
1. Attach `PropFirm_SuperEA` to the matching chart (e.g. XAUUSD).
2. In the EA settings dialog, open the **Inputs** tab.
3. Click **Load**, choose the `.set` file, then **OK**.

> Tighten `InpMaxDailyLossPct` / `InpMaxTotalDDPct` to match your firm's exact
> rules, and always forward-test on a demo/challenge account first. These are
> daily-bar optimizations — confirm in the MT5 Strategy Tester for your broker.
