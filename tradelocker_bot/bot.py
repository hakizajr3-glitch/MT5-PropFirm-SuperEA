"""Main TradeLocker bot loop.

Wires the pure strategy/risk logic to the TradeLocker REST API via the official
`tradelocker` Python SDK. The SDK is imported lazily so the rest of the package
(strategy, risk, config) can be imported and unit-tested without it installed.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd

from .config import BotConfig
from .risk import RiskManager
from . import strategy as strat

logger = logging.getLogger("tradelocker_bot")


def _first(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


class TradeLockerBot:
    def __init__(self, cfg: BotConfig):
        self.cfg = cfg
        self.api = None
        self.instrument_id = None
        self.risk = RiskManager(cfg.risk, state_path=cfg.state_file)
        self._last_bar_ts: int | None = None
        self._cached_bars: pd.DataFrame = pd.DataFrame()

    # ---- connection --------------------------------------------------
    def connect(self) -> None:
        try:
            from tradelocker import TLAPI  # lazy import
        except ImportError as exc:  # pragma: no cover - requires the SDK
            raise RuntimeError(
                "The 'tradelocker' package is required. Install with: "
                "pip install -r tradelocker_bot/requirements.txt"
            ) from exc

        c = self.cfg.credentials
        kwargs = dict(
            environment=c.environment,
            username=c.username,
            password=c.password,
            server=c.server,
        )
        if c.account_id:
            kwargs["acc_num"] = c.account_id
        self.api = TLAPI(**kwargs)

        self.instrument_id = self.api.get_instrument_id_from_symbol_name(
            self.cfg.strategy.symbol
        )
        if self.instrument_id is None:
            raise RuntimeError(f"Unknown symbol on TradeLocker: {self.cfg.strategy.symbol}")
        logger.info("Connected. %s -> instrument_id=%s",
                    self.cfg.strategy.symbol, self.instrument_id)

    # ---- account helpers --------------------------------------------
    def get_equity(self) -> float:
        state = self.api.get_account_state()
        if isinstance(state, dict):
            return float(_first(state, "projectedBalance", "balance",
                                "equity", "cashBalance", default=0.0))
        # Some SDK versions return a pandas Series/DataFrame
        try:
            return float(state.get("projectedBalance", state.get("balance", 0.0)))
        except AttributeError:
            return 0.0

    def get_balance(self) -> float:
        state = self.api.get_account_state()
        if isinstance(state, dict):
            return float(_first(state, "balance", "projectedBalance",
                                "cashBalance", default=0.0))
        try:
            return float(state.get("balance", 0.0))
        except AttributeError:
            return 0.0

    def get_bars(self) -> pd.DataFrame:
        s = self.cfg.strategy
        hist = self.api.get_price_history(
            self.instrument_id,
            resolution=s.resolution,
            lookback_period=s.lookback,
        )
        df = pd.DataFrame(hist)
        # TradeLocker history columns: t,o,h,l,c,v
        rename = {"o": "open", "h": "high", "l": "low", "c": "close", "t": "time"}
        df = df.rename(columns=rename)
        for col in ("open", "high", "low", "close"):
            if col not in df.columns:
                raise RuntimeError(f"price history missing column '{col}': {list(df.columns)}")
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    def own_positions(self) -> pd.DataFrame:
        positions = self.api.get_all_positions()
        df = pd.DataFrame(positions)
        if df.empty:
            return df
        # Filter to our instrument when the column exists.
        for col in ("tradableInstrumentId", "instrumentId"):
            if col in df.columns:
                df = df[df[col] == self.instrument_id]
                break
        return df.reset_index(drop=True)

    # ---- order helpers ----------------------------------------------
    def _close_all(self, reason: str) -> None:
        df = self.own_positions()
        if df.empty:
            return
        logger.warning("Closing %d position(s): %s", len(df), reason)
        for _, row in df.iterrows():
            pid = _first(row.to_dict(), "id", "positionId")
            if pid is None:
                continue
            if self.cfg.dry_run:
                logger.info("[dry-run] would close position %s", pid)
                continue
            try:
                self.api.close_position(int(pid))
            except Exception as exc:  # pragma: no cover - network
                logger.error("Failed to close position %s: %s", pid, exc)

    def _place_order(self, signal: int, entry: float, sl: float, tp: float, qty: float) -> None:
        side = "buy" if signal == strat.BUY else "sell"
        logger.info("Signal %s qty=%.4f entry=%.5f SL=%.5f TP=%.5f",
                    side.upper(), qty, entry, sl, tp)
        if self.cfg.dry_run:
            logger.info("[dry-run] order not sent")
            return
        try:
            order_id = self.api.create_order(
                self.instrument_id,
                quantity=qty,
                side=side,
                type_="market",
                stop_loss=round(sl, 5),
                stop_loss_type="absolute",
                take_profit=round(tp, 5),
                take_profit_type="absolute",
            )
            logger.info("Order submitted: id=%s", order_id)
        except Exception as exc:  # pragma: no cover - network
            logger.error("create_order failed: %s", exc)

    def _manage_exits(self, atr_value: float) -> None:
        e = self.cfg.exits
        if not (e.use_breakeven or e.use_trailing) or atr_value <= 0:
            return
        df = self.own_positions()
        if df.empty:
            return
        for _, row in df.iterrows():
            r = row.to_dict()
            pid = _first(r, "id", "positionId")
            side = str(_first(r, "side", default="")).lower()
            entry = float(_first(r, "avgPrice", "openPrice", default=0.0) or 0.0)
            cur_sl = _first(r, "stopLoss", "sl")
            cur_sl = float(cur_sl) if cur_sl not in (None, "", 0) else None
            if pid is None or entry <= 0:
                continue

            bars = self._cached_bars
            last = float(bars["close"].iloc[-1])
            is_buy = side == "buy"
            profit = (last - entry) if is_buy else (entry - last)

            new_sl = cur_sl
            if e.use_breakeven and profit >= e.be_trigger_atr * atr_value:
                be = entry + e.be_lock_atr * atr_value if is_buy else entry - e.be_lock_atr * atr_value
                new_sl = be if new_sl is None else (max(new_sl, be) if is_buy else min(new_sl, be))
            if e.use_trailing and profit >= e.trail_start_atr * atr_value:
                trail = last - e.trail_step_atr * atr_value if is_buy else last + e.trail_step_atr * atr_value
                new_sl = trail if new_sl is None else (max(new_sl, trail) if is_buy else min(new_sl, trail))

            improved = new_sl is not None and (cur_sl is None or
                       (is_buy and new_sl > cur_sl) or (not is_buy and new_sl < cur_sl))
            if not improved:
                continue
            if self.cfg.dry_run:
                logger.info("[dry-run] would modify %s SL -> %.5f", pid, new_sl)
                continue
            try:
                self.api.modify_position(int(pid), stop_loss=round(new_sl, 5))
                logger.info("Trailed position %s SL -> %.5f", pid, new_sl)
            except Exception as exc:  # pragma: no cover - network
                logger.error("modify_position failed for %s: %s", pid, exc)

    # ---- main loop ---------------------------------------------------
    def run_once(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)

        equity = self.get_equity()
        self.risk.on_equity_update(equity, now)
        status = self.risk.check_limits(equity)

        bars = self.get_bars()
        self._cached_bars = bars
        sig = strat.compute_signal(bars, self.cfg.strategy)

        if status.locked:
            logger.warning("Trading locked: %s", "; ".join(status.reasons) or "limit reached")
            if (self.risk.state.daily_locked and self.cfg.risk.close_on_daily_stop) or \
               (self.risk.state.total_locked and self.cfg.risk.close_on_total_stop):
                self._close_all("risk limit reached")
            return

        # manage existing trades every cycle
        self._manage_exits(sig.atr)

        # new entries only on a freshly closed bar
        bar_ts = int(bars["time"].iloc[-1]) if "time" in bars.columns else len(bars)
        new_bar = bar_ts != self._last_bar_ts
        self._last_bar_ts = bar_ts
        if not new_bar:
            return

        if not self.risk.in_session(now):
            return

        if len(self.own_positions()) >= self.cfg.risk.max_open_positions:
            return

        if sig.signal == strat.NONE or sig.atr <= 0:
            return

        sl, tp = strat.stop_levels(sig.signal, sig.close, sig.atr,
                                   self.cfg.strategy.sl_atr, self.cfg.strategy.tp_atr)
        sl_dist = abs(sig.close - sl)
        qty = self.risk.position_size(
            balance=self.get_balance(),
            sl_distance_price=sl_dist,
            money_per_price_per_qty=self.cfg.contract_size,
        )
        if qty <= 0:
            logger.warning("Computed quantity 0 - skipping entry")
            return
        self._place_order(sig.signal, sig.close, sl, tp, qty)

    def run(self) -> None:
        self.connect()
        logger.info("Bot started. poll=%ss dry_run=%s", self.cfg.poll_seconds, self.cfg.dry_run)
        while True:
            try:
                self.run_once()
            except Exception as exc:  # pragma: no cover - resilience
                logger.exception("run_once error: %s", exc)
            time.sleep(self.cfg.poll_seconds)
