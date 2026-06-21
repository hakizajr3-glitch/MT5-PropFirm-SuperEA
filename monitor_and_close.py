"""Monitor all XAUUSD.R positions and close when combined PnL >= $5."""
import sys, os, time
sys.path.insert(0, '/Users/innocekaiser/MT5-PropFirm-SuperEA')
from dotenv import load_dotenv
load_dotenv('/Users/innocekaiser/MT5-PropFirm-SuperEA/tradelocker_bot/.env')

from tradelocker_bot.config import BotConfig
from tradelocker_bot.bot import TradeLockerBot
import pandas as pd

cfg = BotConfig.from_env()
TARGET_PROFIT = 5.0
XAU_INSTR_ID = 13676

print(f"Monitoring XAUUSD.R positions — close all when combined PnL >= ${TARGET_PROFIT}")

while True:
    try:
        bot = TradeLockerBot(cfg)
        bot.connect()

        raw = bot.api.get_all_positions()
        df = pd.DataFrame(raw)
        if df.empty:
            print("No positions — exiting")
            break

        xau_positions = [r for _, r in df.iterrows()
                         if r["tradableInstrumentId"] == XAU_INSTR_ID]

        if not xau_positions:
            print("No XAUUSD.R positions — exiting")
            break

        combined_pnl = sum(float(p["unrealizedPl"]) for p in xau_positions)
        print(f"  {len(xau_positions)} pos | Combined: ${combined_pnl:.2f}{' ✅' if combined_pnl >= TARGET_PROFIT else ''}")

        if combined_pnl >= TARGET_PROFIT:
            print(f"Target ${TARGET_PROFIT}! Closing {len(xau_positions)} positions...")
            for p in xau_positions:
                pid = p["id"]
                try:
                    bot.api.close_position(int(pid))
                    print(f"  Closed {pid}")
                except Exception as e:
                    print(f"  Failed {pid}: {e}")
            break

    except Exception as e:
        print(f"Error: {e}")

    time.sleep(10)
