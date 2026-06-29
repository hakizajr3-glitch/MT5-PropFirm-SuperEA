"""Configuration for the AI Hedge Fund module.

Reads from environment variables, with sensible defaults for a $1,000 prop-firm
account where capital preservation is the top priority.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .risk_manager import RiskLimits


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class HedgeFundConfig:
    """Top-level config for the AI Hedge Fund."""

    # symbols to scan
    symbols: list[str] | None = None

    # risk limits (prop-firm friendly defaults for small accounts)
    risk_limits: RiskLimits | None = None

    # ATR-based stops
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 2.5
    contract_size: float = 100_000.0

    # timing
    poll_seconds: int = 30
    bar_resolution: str = "1H"
    bar_lookback: str = "30D"

    # execution
    dry_run: bool = True
    auto_execute: bool = False   # if True, send orders automatically; if False, just log

    @classmethod
    def from_env(cls) -> "HedgeFundConfig":
        symbols_raw = _env("HF_SYMBOLS", "EURUSD,GBPUSD,XAUUSD")
        symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]

        risk_limits = RiskLimits(
            max_risk_per_trade_pct=_env_float("HF_MAX_RISK_PER_TRADE", 1.0),
            max_daily_loss_pct=_env_float("HF_MAX_DAILY_LOSS", 5.0),
            max_total_dd_pct=_env_float("HF_MAX_TOTAL_DD", 10.0),
            max_open_positions=_env_int("HF_MAX_OPEN_POSITIONS", 3),
            max_portfolio_heat_pct=_env_float("HF_MAX_PORTFOLIO_HEAT", 6.0),
            min_consensus_confidence=_env_float("HF_MIN_CONFIDENCE", 0.4),
            min_agents_agree=_env_int("HF_MIN_AGENTS_AGREE", 3),
        )

        return cls(
            symbols=symbols,
            risk_limits=risk_limits,
            sl_atr_mult=_env_float("HF_SL_ATR", 1.5),
            tp_atr_mult=_env_float("HF_TP_ATR", 2.5),
            contract_size=_env_float("HF_CONTRACT_SIZE", 100_000.0),
            poll_seconds=_env_int("HF_POLL_SECONDS", 30),
            bar_resolution=_env("HF_RESOLUTION", "1H"),
            bar_lookback=_env("HF_LOOKBACK", "30D"),
            dry_run=_env_bool("HF_DRY_RUN", True),
            auto_execute=_env_bool("HF_AUTO_EXECUTE", False),
        )
