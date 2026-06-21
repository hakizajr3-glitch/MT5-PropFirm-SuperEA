"""Entrypoint for the TradeLocker bot.

Usage:
    python -m tradelocker_bot.run

Loads configuration from environment variables (and a local `.env` if present),
then starts the trading loop. Set TL_DRY_RUN=true to run without sending orders.
"""

from __future__ import annotations

import logging
import os
import sys


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # Load .env from CWD if present.
    if os.path.exists(".env"):
        load_dotenv(".env")


def main() -> int:
    _load_dotenv()
    logging.basicConfig(
        level=os.getenv("TL_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from .config import BotConfig
    from .bot import TradeLockerBot

    try:
        cfg = BotConfig.from_env()
    except ValueError as exc:
        logging.error("Configuration error: %s", exc)
        logging.error("Copy tradelocker_bot/.env.example to .env and fill it in.")
        return 2

    bot = TradeLockerBot(cfg)
    try:
        bot.run()
    except KeyboardInterrupt:
        logging.info("Stopped by user.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
