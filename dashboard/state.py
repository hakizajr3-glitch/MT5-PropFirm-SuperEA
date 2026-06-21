"""Assemble the full dashboard state consumed by the frontend.

`build_state(provider, cfg)` returns a JSON-serialisable dict covering every
panel in the SHROUDAGE spec: system status, account, performance, open
positions, market view, and the agent-network status board.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from . import analytics, metrics
from .providers import BaseProvider


@dataclass
class DashboardConfig:
    # SHROUDAGE risk constraints (capital preservation first).
    max_risk_per_trade_pct: float = 0.5
    max_risk_hard_pct: float = 1.0
    daily_loss_limit_pct: float = 3.0
    max_drawdown_pct: float = 8.0
    # operating mode: requested mode; SAFE MODE/HALTED can be forced by risk.
    mode: str = "DRY RUN"      # DRY RUN | LIVE | SAFE MODE | HALTED
    news_feed_configured: bool = False
    llm_configured: bool = False

    @classmethod
    def from_env(cls) -> "DashboardConfig":
        return cls(
            max_risk_per_trade_pct=float(os.getenv("SHROUD_RISK_PER_TRADE", "0.5")),
            max_risk_hard_pct=float(os.getenv("SHROUD_RISK_MAX", "1.0")),
            daily_loss_limit_pct=float(os.getenv("SHROUD_DAILY_LOSS", "3.0")),
            max_drawdown_pct=float(os.getenv("SHROUD_MAX_DD", "8.0")),
            mode=os.getenv("SHROUD_MODE", "DRY RUN").upper(),
            news_feed_configured=os.getenv("SHROUD_NEWS_FEED", "") not in ("", "0", "false"),
            llm_configured=os.getenv("SHROUD_LLM", "") not in ("", "0", "false"),
        )


def _safe(x):
    """JSON-safe: turn NaN/inf into None."""
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return _safe(obj)


def build_state(provider: BaseProvider, cfg: DashboardConfig) -> dict:
    account = provider.get_account()
    positions = provider.get_positions()
    closed = provider.get_closed_trades()

    start_eq = account.get("day_start_equity") or account.get("balance") or 0.0
    perf = metrics.compute_performance(closed, starting_equity=float(start_eq or 0.0))

    # ---- risk agent evaluation ----
    daily_used = 0.0
    if account.get("day_start_equity"):
        daily_used = max(0.0, (account["day_start_equity"] - account.get("equity", 0.0))
                         / account["day_start_equity"] * 100.0)
    dd_used = 0.0
    if account.get("peak_equity"):
        dd_used = max(0.0, (account["peak_equity"] - account.get("equity", 0.0))
                      / account["peak_equity"] * 100.0)

    risk_breaches = []
    if daily_used >= cfg.daily_loss_limit_pct:
        risk_breaches.append(f"Daily loss {daily_used:.2f}% ≥ {cfg.daily_loss_limit_pct:.2f}%")
    if dd_used >= cfg.max_drawdown_pct:
        risk_breaches.append(f"Drawdown {dd_used:.2f}% ≥ {cfg.max_drawdown_pct:.2f}%")

    # system status: risk overrides requested mode
    mode = cfg.mode
    if risk_breaches:
        mode = "SAFE MODE"

    # ---- market view / agents per symbol ----
    market = []
    scanned_ok = 0
    for sym in provider.symbols:
        df = provider.get_bars(sym)
        spread = provider.get_spread(sym)
        a = analytics.analyze_symbol(sym, df, spread=spread)
        if a.ok:
            scanned_ok += 1
        market.append(a.as_dict())

    any_buy_sell = any(m["trend_decision"] in ("BUY", "SELL")
                       or m["range_decision"] in ("BUY", "SELL") for m in market)

    # ---- agent status board ----
    def st(running: bool, busy: bool = False, offline: bool = False, error: bool = False):
        if error:
            return "ERROR"
        if offline:
            return "OFFLINE"
        if busy:
            return "RUNNING"
        return "RUNNING" if running else "WAITING"

    execution_status = "WAITING"
    if mode == "LIVE":
        execution_status = "RUNNING"
    elif mode in ("SAFE MODE", "HALTED"):
        execution_status = "WAITING"

    agents = [
        {"name": "Planner", "status": "RUNNING",
         "detail": "Allocating risk budget, delegating to agents"},
        {"name": "Market Scanner", "status": st(scanned_ok > 0, error=scanned_ok == 0),
         "detail": f"{scanned_ok}/{len(provider.symbols)} symbols analysed"},
        {"name": "Trend Agent", "status": "RUNNING",
         "detail": "EMA20/50 + RSI + ADX + ATR"},
        {"name": "Range Agent", "status": "RUNNING",
         "detail": "ADX<20 mean-reversion (RSI + Bollinger)"},
        {"name": "Volatility Agent", "status": "RUNNING",
         "detail": "ATR%/regime classification"},
        {"name": "News Agent",
         "status": st(False, offline=not cfg.news_feed_configured),
         "detail": "Economic-calendar feed " + ("connected" if cfg.news_feed_configured
                                                 else "not configured (set SHROUD_NEWS_FEED)")},
        {"name": "Risk Agent", "status": "SAFE MODE" if risk_breaches else "RUNNING",
         "detail": "; ".join(risk_breaches) if risk_breaches
                   else f"daily {daily_used:.2f}/{cfg.daily_loss_limit_pct}%, "
                        f"DD {dd_used:.2f}/{cfg.max_drawdown_pct}%"},
        {"name": "Execution Agent", "status": execution_status,
         "detail": f"mode={mode}; only executes approved plans"},
        {"name": "Journal Agent", "status": st(len(closed) > 0),
         "detail": f"{len(closed)} closed trades recorded"},
        {"name": "Reflection Agent",
         "status": st(False, offline=not cfg.llm_configured),
         "detail": "Per-trade review " + ("active" if cfg.llm_configured
                                          else "needs LLM (set SHROUD_LLM)")},
        {"name": "Learning Agent",
         "status": st(False, offline=not cfg.llm_configured),
         "detail": "Strategy adaptation " + ("active" if cfg.llm_configured
                                             else "needs LLM (set SHROUD_LLM)")},
    ]

    state = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"mode": provider.mode, "name": provider.name,
                   "errors": provider.errors},
        "system_status": mode,
        "decision": "TRADES PENDING" if any_buy_sell else "WAIT — no confirmed setup",
        "account": account,
        "performance": perf.as_dict(),
        "positions": positions,
        "risk": {
            "max_risk_per_trade_pct": cfg.max_risk_per_trade_pct,
            "max_risk_hard_pct": cfg.max_risk_hard_pct,
            "daily_loss_limit_pct": cfg.daily_loss_limit_pct,
            "max_drawdown_pct": cfg.max_drawdown_pct,
            "daily_loss_used_pct": round(daily_used, 2),
            "drawdown_used_pct": round(dd_used, 2),
            "breaches": risk_breaches,
            "safe_mode": bool(risk_breaches),
        },
        "market": market,
        "agents": agents,
    }
    return _clean(state)
