"""Fetch XAUUSD.R daily data and compute EMA crossover signal."""
import sys, os
sys.path.insert(0, '/Users/innocekaiser/MT5-PropFirm-SuperEA')
from dotenv import load_dotenv
load_dotenv('/Users/innocekaiser/MT5-PropFirm-SuperEA/tradelocker_bot/.env')

from tradelocker_bot.config import BotConfig
from tradelocker_bot.strategy import compute_signal, BUY, SELL, NONE, ema
from tradelocker_bot.bot import TradeLockerBot

cfg = BotConfig.from_env()
s = cfg.strategy
print(f"Config: symbol={s.symbol} fast_ema={s.fast_ema} slow_ema={s.slow_ema} resolution={s.resolution}")
print(f"RSI filter: use={s.use_rsi_filter} buy_min={s.rsi_buy_min} sell_max={s.rsi_sell_max}")
print()

bot = TradeLockerBot(cfg)
bot.connect()

bars = bot.get_bars()
print(f"Got {len(bars)} bars, last close={bars['close'].iloc[-1]:.2f}")
print()

sig = compute_signal(bars, s)

signal_text = {NONE: "NONE", BUY: "BUY", SELL: "SELL"}[sig.signal]
print(f"Signal: {signal_text}")
print(f"Close: {sig.close:.2f}")
print(f"ATR: {sig.atr:.2f}")
print(f"Fast EMA ({s.fast_ema}): {sig.fast:.2f}")
print(f"Slow EMA ({s.slow_ema}): {sig.slow:.2f}")
print(f"RSI: {sig.rsi:.2f}")
print()

fast_s = ema(bars["close"], s.fast_ema)
slow_s = ema(bars["close"], s.slow_ema)
print("Last 5 bars (close, fast_ema, slow_ema):")
for i in range(-5, 0):
    c = bars["close"].iloc[i]
    f = fast_s.iloc[i]
    sl = slow_s.iloc[i]
    print(f"  close={c:.2f} fast={f:.2f} slow={sl:.2f} fast>slow={f>sl}")
