"""Prop-firm risk management: daily-loss limit, max drawdown, session filter,
and risk-based position sizing.

State (day-start equity, peak equity) is persisted to a small JSON file so the
limits survive a restart within the same trading day, mirroring the MT5 EA's use
of global variables.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RiskState:
    day_key: int = -1            # YYYYMMDD
    day_start_equity: float = 0.0
    peak_equity: float = 0.0
    daily_locked: bool = False
    total_locked: bool = False


@dataclass
class LimitStatus:
    locked: bool
    daily_loss_pct: float
    total_dd_pct: float
    reasons: list[str] = field(default_factory=list)


def _day_key(now: datetime) -> int:
    return now.year * 10000 + now.month * 100 + now.day


class RiskManager:
    def __init__(self, cfg, state_path: str | None = None):
        self.cfg = cfg
        self.state_path = state_path
        self.state = RiskState()
        if state_path and os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self.state = RiskState(**data)
            except (OSError, ValueError, TypeError):
                self.state = RiskState()

    # ---- persistence -------------------------------------------------
    def _save(self) -> None:
        if not self.state_path:
            return
        try:
            with open(self.state_path, "w", encoding="utf-8") as fh:
                json.dump(self.state.__dict__, fh)
        except OSError:
            pass

    # ---- baselines ---------------------------------------------------
    def on_equity_update(self, equity: float, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        key = _day_key(now)
        if key != self.state.day_key:
            self.state.day_key = key
            self.state.day_start_equity = equity
            self.state.daily_locked = False
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity
        if self.state.peak_equity <= 0:
            self.state.peak_equity = equity
        self._save()

    # ---- limits ------------------------------------------------------
    def check_limits(self, equity: float) -> LimitStatus:
        cfg = self.cfg
        reasons: list[str] = []

        daily_loss_pct = 0.0
        if self.state.day_start_equity > 0:
            daily_loss_pct = (self.state.day_start_equity - equity) / self.state.day_start_equity * 100.0

        total_dd_pct = 0.0
        if self.state.peak_equity > 0:
            total_dd_pct = (self.state.peak_equity - equity) / self.state.peak_equity * 100.0

        if cfg.max_daily_loss_pct > 0 and daily_loss_pct >= cfg.max_daily_loss_pct:
            self.state.daily_locked = True
            reasons.append(
                f"daily loss {daily_loss_pct:.2f}% >= {cfg.max_daily_loss_pct:.2f}%"
            )
        if cfg.max_total_dd_pct > 0 and total_dd_pct >= cfg.max_total_dd_pct:
            self.state.total_locked = True
            reasons.append(
                f"total drawdown {total_dd_pct:.2f}% >= {cfg.max_total_dd_pct:.2f}%"
            )

        self._save()
        locked = self.state.daily_locked or self.state.total_locked
        return LimitStatus(locked, daily_loss_pct, total_dd_pct, reasons)

    # ---- session -----------------------------------------------------
    def in_session(self, now: datetime | None = None) -> bool:
        cfg = self.cfg
        if not cfg.use_session:
            return True
        now = now or datetime.now(timezone.utc)
        dow = now.isoweekday()  # Mon=1 .. Sun=7
        if dow >= 6:  # Sat/Sun
            return False
        if not cfg.trade_monday and dow == 1:
            return False
        if not cfg.trade_friday and dow == 5:
            return False
        hour = now.hour
        if cfg.start_hour <= cfg.end_hour:
            return cfg.start_hour <= hour < cfg.end_hour
        return hour >= cfg.start_hour or hour < cfg.end_hour

    # ---- sizing ------------------------------------------------------
    def _effective_risk_pct(self, signal_strength: int = 100) -> float:
        """Compute effective risk % after adaptive sizing and DD cushion.

        v4.0: scales risk based on signal strength (0-100) and proximity to
        drawdown limits.
        """
        cfg = self.cfg
        base_pct = cfg.risk_percent

        # Adaptive sizing: scale between min and max based on signal strength
        if getattr(cfg, "use_adaptive_sizing", False) and signal_strength < 100:
            min_pct = getattr(cfg, "adaptive_min_pct", 0.5)
            max_pct = getattr(cfg, "adaptive_max_pct", 2.0)
            ratio = signal_strength / 100.0
            base_pct = min_pct + (max_pct - min_pct) * ratio

        # DD cushion: reduce risk as drawdown grows
        if getattr(cfg, "use_dd_cushion", False) and self.state.peak_equity > 0:
            equity = self.state.peak_equity  # conservative: use last known
            dd_pct = 0.0
            if self.state.peak_equity > 0:
                dd_pct = max(0.0, (self.state.peak_equity - self.state.day_start_equity)
                             / self.state.peak_equity * 100.0)
            max_dd = cfg.max_total_dd_pct if cfg.max_total_dd_pct > 0 else 10.0
            dd_usage = dd_pct / max_dd * 100.0  # how much of the DD budget is used
            cushion_start = getattr(cfg, "dd_cushion_start", 50.0)
            if dd_usage >= cushion_start:
                # Linear reduction: at cushion_start% used -> full risk;
                # at 100% used -> 25% of risk
                scale = max(0.25, 1.0 - 0.75 * (dd_usage - cushion_start) / (100.0 - cushion_start))
                base_pct *= scale

        return max(0.01, base_pct)

    def position_size(
        self,
        balance: float,
        sl_distance_price: float,
        money_per_price_per_qty: float,
        min_qty: float = 0.01,
        max_qty: float = 100.0,
        qty_step: float = 0.01,
        signal_strength: int = 100,
    ) -> float:
        """Quantity to trade.

        `money_per_price_per_qty` = account-currency loss for a 1.0 price move
        on 1 unit of quantity (e.g. contract size). For a fixed-quantity config
        this is ignored.

        `signal_strength` (0-100): v4.0 adaptive sizing input. Higher values
        risk more when adaptive sizing is enabled.
        """
        cfg = self.cfg
        if not cfg.use_risk_percent:
            return _round_step(cfg.fixed_quantity, min_qty, max_qty, qty_step)

        if sl_distance_price <= 0 or money_per_price_per_qty <= 0 or balance <= 0:
            return _round_step(cfg.fixed_quantity, min_qty, max_qty, qty_step)

        effective_pct = self._effective_risk_pct(signal_strength)
        risk_money = balance * effective_pct / 100.0
        loss_per_qty = sl_distance_price * money_per_price_per_qty
        if loss_per_qty <= 0:
            return _round_step(cfg.fixed_quantity, min_qty, max_qty, qty_step)
        qty = risk_money / loss_per_qty
        return _round_step(qty, min_qty, max_qty, qty_step)


def _round_step(qty: float, min_qty: float, max_qty: float, step: float) -> float:
    if step <= 0:
        step = 0.01
    qty = math.floor(qty / step) * step
    if qty < min_qty:
        qty = min_qty
    if qty > max_qty:
        qty = max_qty
    # avoid float dust
    return round(qty, 8)
