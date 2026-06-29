"""Run the AI Hedge Fund as a standalone loop or integrate with the dashboard engine.

Usage:
    # Standalone (dry-run with demo data by default):
    python -m ai_hedge_fund.run

    # Live with TradeLocker:
    HF_DRY_RUN=false python -m ai_hedge_fund.run
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd

from .agents.base import MarketSnapshot
from .config import HedgeFundConfig
from .executor import TradeLockerExecutor
from .orchestrator import Orchestrator

logger = logging.getLogger("ai_hedge_fund")


class HedgeFundRunner:
    """Top-level runner for the AI Hedge Fund."""

    def __init__(self, cfg: HedgeFundConfig | None = None):
        self.cfg = cfg or HedgeFundConfig.from_env()
        self.orchestrator = Orchestrator(
            risk_limits=self.cfg.risk_limits,
            sl_atr_mult=self.cfg.sl_atr_mult,
            tp_atr_mult=self.cfg.tp_atr_mult,
            contract_size=self.cfg.contract_size,
        )
        self.executor = TradeLockerExecutor(dry_run=self.cfg.dry_run)
        self.api = None
        self._last_report: dict | None = None

    def connect_live(self) -> None:
        """Connect to TradeLocker for live data and execution."""
        try:
            from tradelocker import TLAPI
            from tradelocker_bot.config import BotConfig

            bot_cfg = BotConfig.from_env()
            c = bot_cfg.credentials
            kwargs = dict(environment=c.environment, username=c.username,
                          password=c.password, server=c.server)
            if c.account_id:
                try:
                    self.api = TLAPI(acc_num=int(c.account_id), **kwargs)
                except (ValueError, TypeError):
                    self.api = TLAPI(account_id=int(c.account_id), **kwargs)
            else:
                self.api = TLAPI(**kwargs)
            self.executor.connect(self.api)
            logger.info("Connected to TradeLocker for AI Hedge Fund")
        except Exception as exc:
            logger.error("Failed to connect to TradeLocker: %s", exc)
            self.api = None

    def _fetch_bars(self, symbol: str) -> pd.DataFrame | None:
        """Fetch OHLCV bars from TradeLocker."""
        if self.api is None:
            return None
        for name in (symbol, f"{symbol}.R", f"{symbol}.r"):
            try:
                iid = self.api.get_instrument_id_from_symbol_name(name)
            except Exception:
                iid = None
            if iid is not None:
                break
        if iid is None:
            logger.warning("Symbol %s not found on TradeLocker", symbol)
            return None
        try:
            hist = self.api.get_price_history(
                iid, resolution=self.cfg.bar_resolution,
                lookback_period=self.cfg.bar_lookback,
            )
        except Exception as exc:
            logger.error("Failed to fetch bars for %s: %s", symbol, exc)
            return None
        df = pd.DataFrame(hist)
        rename = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "t": "time"}
        df = df.rename(columns=rename)
        for col in ("open", "high", "low", "close"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    def _get_account_state(self) -> dict:
        if self.api is None:
            return {"balance": 1000.0, "equity": 1000.0, "day_start_equity": 1000.0,
                    "peak_equity": 1000.0, "open_pnl": 0.0, "positions_count": 0}
        try:
            st = self.api.get_account_state()
            bal = float(st.get("balance", 0))
            eq = float(st.get("projectedBalance", bal))
            return {
                "balance": bal,
                "equity": eq,
                "day_start_equity": eq - float(st.get("todayNet", 0)),
                "peak_equity": eq,
                "open_pnl": float(st.get("openNetPnL", 0)),
                "positions_count": int(st.get("positionsCount", 0)),
            }
        except Exception as exc:
            logger.error("Failed to get account state: %s", exc)
            return {"balance": 0, "equity": 0, "day_start_equity": 0,
                    "peak_equity": 0, "open_pnl": 0, "positions_count": 0}

    def run_once(self) -> dict:
        """Execute one full cycle of the AI Hedge Fund pipeline."""
        account = self._get_account_state()

        snapshots = []
        for symbol in (self.cfg.symbols or []):
            bars = self._fetch_bars(symbol)
            if bars is not None and len(bars) >= 52:
                snapshots.append(MarketSnapshot(
                    symbol=symbol, bars=bars,
                    timeframe=self.cfg.bar_resolution,
                ))
            else:
                logger.warning("Skipping %s: insufficient data", symbol)

        if not snapshots:
            logger.info("No symbols with sufficient data — skipping cycle")
            self._last_report = {"results": [], "orders": []}
            return self._last_report

        report = self.orchestrator.run_cycle(
            snapshots=snapshots,
            equity=account["equity"],
            balance=account["balance"],
            day_start_equity=account["day_start_equity"],
            peak_equity=account["peak_equity"],
            current_daily_pnl=account.get("open_pnl", 0),
            open_position_count=account.get("positions_count", 0),
        )

        # execute if auto_execute is on
        if self.cfg.auto_execute and report.orders:
            results = self.executor.execute_batch(report.orders)
            for r in results:
                if r.success:
                    logger.info("Order executed: %s %s (id=%s, dry_run=%s)",
                                r.action, r.symbol, r.order_id, r.dry_run)
                else:
                    logger.error("Order failed: %s %s — %s", r.action, r.symbol, r.error)

        self._last_report = report.as_dict()
        return self._last_report

    def run(self) -> None:
        """Main loop — connect and poll."""
        if not self.cfg.dry_run:
            self.connect_live()
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(name)s %(message)s")
        logger.info("AI Hedge Fund started. symbols=%s dry_run=%s auto_execute=%s poll=%ds",
                     self.cfg.symbols, self.cfg.dry_run, self.cfg.auto_execute,
                     self.cfg.poll_seconds)
        while True:
            try:
                self.run_once()
            except Exception as exc:
                logger.exception("Cycle error: %s", exc)
            time.sleep(self.cfg.poll_seconds)

    @property
    def last_report(self) -> dict | None:
        return self._last_report


def main():
    runner = HedgeFundRunner()
    runner.run()


if __name__ == "__main__":
    main()
