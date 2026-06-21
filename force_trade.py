"""Force a BUY on XAUUSD.R — run this when market is open."""
import sys, os, math
sys.path.insert(0, '/Users/innocekaiser/MT5-PropFirm-SuperEA')
from dotenv import load_dotenv
load_dotenv('/Users/innocekaiser/MT5-PropFirm-SuperEA/tradelocker_bot/.env')

from tradelocker_bot.config import BotConfig
from tradelocker_bot.bot import TradeLockerBot
from tradelocker_bot.strategy import compute_signal, BUY, SELL, NONE, ema, atr

cfg = BotConfig.from_env()
bot = TradeLockerBot(cfg)
bot.connect()

bars = bot.get_bars()
close = bars["close"].iloc[-1]
atr_val = float(atr(bars, cfg.strategy.atr_period).iloc[-1])

sl_dist = atr_val * cfg.strategy.sl_atr
tp_dist = atr_val * cfg.strategy.tp_atr
sl = close - sl_dist
tp = close + tp_dist

balance = bot.get_balance()
loss_per_qty = sl_dist * cfg.contract_size
qty = max(0.01, math.floor((balance * cfg.risk.risk_percent / 100.0 / loss_per_qty) / 0.01) * 0.01)
qty = min(qty, 100.0)

print(f"XAUUSD.R close={close:.2f} ATR={atr_val:.2f}")
print(f"BUY {qty:.2f} lots | SL={sl:.2f} TP={tp:.2f}")
print(f"Risk: ${qty * loss_per_qty:.2f} | Reward: ${qty * tp_dist * cfg.contract_size:.2f}")

if cfg.dry_run:
    print("DRY RUN — not sent")
    sys.exit(0)

try:
    order_id = bot.api.create_order(
        bot.instrument_id, quantity=qty, side="buy", type_="market",
        stop_loss=round(sl, 5), stop_loss_type="absolute",
        take_profit=round(tp, 5), take_profit_type="absolute",
    )
    print(f"✅ Order submitted! id={order_id}")
except Exception as e:
    print(f"❌ Failed: {e}")
