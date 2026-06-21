"""Configuration for the TradeLocker bot.

Values are read from environment variables (optionally loaded from a `.env`
file). See `.env.example` for the full list and documentation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get(name: str, default: str | None = None) -> str:
    val = os.getenv(name, default)
    if val is None:
        raise ValueError(f"Missing required environment variable: {name}")
    return val


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


@dataclass
class Credentials:
    """TradeLocker API credentials and target account."""

    environment: str  # e.g. https://demo.tradelocker.com or https://live.tradelocker.com
    username: str
    password: str
    server: str
    account_id: str = ""  # optional; if empty the first account is used

    @classmethod
    def from_env(cls) -> "Credentials":
        return cls(
            environment=_get("TL_ENVIRONMENT", "https://demo.tradelocker.com"),
            username=_get("TL_USERNAME"),
            password=_get("TL_PASSWORD"),
            server=_get("TL_SERVER"),
            account_id=os.getenv("TL_ACCOUNT_ID", ""),
        )


@dataclass
class StrategyConfig:
    symbol: str = "EURUSD"
    resolution: str = "1H"          # TradeLocker bar resolution (1m,5m,15m,1H,4H,1D,...)
    lookback: str = "30D"           # history window to pull for indicators
    fast_ema: int = 20
    slow_ema: int = 50
    atr_period: int = 14
    sl_atr: float = 1.5
    tp_atr: float = 2.5
    use_rsi_filter: bool = True
    rsi_period: int = 14
    rsi_buy_min: float = 50.0
    rsi_sell_max: float = 50.0

    @classmethod
    def from_env(cls) -> "StrategyConfig":
        return cls(
            symbol=os.getenv("TL_SYMBOL", "EURUSD"),
            resolution=os.getenv("TL_RESOLUTION", "1H"),
            lookback=os.getenv("TL_LOOKBACK", "30D"),
            fast_ema=_get_int("TL_FAST_EMA", 20),
            slow_ema=_get_int("TL_SLOW_EMA", 50),
            atr_period=_get_int("TL_ATR_PERIOD", 14),
            sl_atr=_get_float("TL_SL_ATR", 1.5),
            tp_atr=_get_float("TL_TP_ATR", 2.5),
            use_rsi_filter=_get_bool("TL_USE_RSI", True),
            rsi_period=_get_int("TL_RSI_PERIOD", 14),
            rsi_buy_min=_get_float("TL_RSI_BUY_MIN", 50.0),
            rsi_sell_max=_get_float("TL_RSI_SELL_MAX", 50.0),
        )


@dataclass
class RiskConfig:
    use_risk_percent: bool = True
    risk_percent: float = 1.0
    fixed_quantity: float = 0.10
    max_open_positions: int = 1
    max_daily_loss_pct: float = 5.0
    max_total_dd_pct: float = 10.0
    close_on_daily_stop: bool = True
    close_on_total_stop: bool = True
    # Session filter (server/UTC hours)
    use_session: bool = True
    start_hour: int = 7
    end_hour: int = 20
    trade_monday: bool = True
    trade_friday: bool = True

    @classmethod
    def from_env(cls) -> "RiskConfig":
        return cls(
            use_risk_percent=_get_bool("TL_USE_RISK_PERCENT", True),
            risk_percent=_get_float("TL_RISK_PERCENT", 1.0),
            fixed_quantity=_get_float("TL_FIXED_QTY", 0.10),
            max_open_positions=_get_int("TL_MAX_OPEN", 1),
            max_daily_loss_pct=_get_float("TL_MAX_DAILY_LOSS_PCT", 5.0),
            max_total_dd_pct=_get_float("TL_MAX_TOTAL_DD_PCT", 10.0),
            close_on_daily_stop=_get_bool("TL_CLOSE_ON_DAILY_STOP", True),
            close_on_total_stop=_get_bool("TL_CLOSE_ON_TOTAL_STOP", True),
            use_session=_get_bool("TL_USE_SESSION", True),
            start_hour=_get_int("TL_START_HOUR", 7),
            end_hour=_get_int("TL_END_HOUR", 20),
            trade_monday=_get_bool("TL_TRADE_MONDAY", True),
            trade_friday=_get_bool("TL_TRADE_FRIDAY", True),
        )


@dataclass
class ExitConfig:
    """Break-even and trailing stop, expressed as multiples of ATR so they are
    instrument-agnostic (no point/tick conversions needed)."""

    use_breakeven: bool = True
    be_trigger_atr: float = 1.0   # move to break-even after price moves this x ATR in profit
    be_lock_atr: float = 0.1      # lock this x ATR beyond entry
    use_trailing: bool = True
    trail_start_atr: float = 1.5  # start trailing after this x ATR in profit
    trail_step_atr: float = 1.0   # trail this x ATR behind price

    @classmethod
    def from_env(cls) -> "ExitConfig":
        return cls(
            use_breakeven=_get_bool("TL_USE_BREAKEVEN", True),
            be_trigger_atr=_get_float("TL_BE_TRIGGER_ATR", 1.0),
            be_lock_atr=_get_float("TL_BE_LOCK_ATR", 0.1),
            use_trailing=_get_bool("TL_USE_TRAILING", True),
            trail_start_atr=_get_float("TL_TRAIL_START_ATR", 1.5),
            trail_step_atr=_get_float("TL_TRAIL_STEP_ATR", 1.0),
        )


@dataclass
class BotConfig:
    credentials: Credentials = field(default_factory=Credentials.from_env)
    strategy: StrategyConfig = field(default_factory=StrategyConfig.from_env)
    risk: RiskConfig = field(default_factory=RiskConfig.from_env)
    exits: ExitConfig = field(default_factory=ExitConfig.from_env)
    contract_size: float = 100000.0  # money/price/qty fallback for risk sizing
    poll_seconds: int = 30
    state_file: str = ".tl_bot_state.json"
    dry_run: bool = False  # if True, never sends live orders

    @classmethod
    def from_env(cls) -> "BotConfig":
        return cls(
            credentials=Credentials.from_env(),
            strategy=StrategyConfig.from_env(),
            risk=RiskConfig.from_env(),
            exits=ExitConfig.from_env(),
            contract_size=_get_float("TL_CONTRACT_SIZE", 100000.0),
            poll_seconds=_get_int("TL_POLL_SECONDS", 30),
            state_file=os.getenv("TL_STATE_FILE", ".tl_bot_state.json"),
            dry_run=_get_bool("TL_DRY_RUN", False),
        )
