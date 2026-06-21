"""Data providers for the dashboard.

`DemoProvider` produces deterministic synthetic data so the dashboard renders
with no credentials (and so tests run offline). `LiveProvider` reads the real
TradeLocker account, positions, price history and trade history. Both expose the
same interface consumed by `dashboard.state.build_state`.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("shroudage.providers")

DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD", "NAS100", "US30", "BTCUSD"]


class BaseProvider:
    mode = "DEMO"
    name = "demo"

    def __init__(self, symbols: list[str] | None = None):
        self.symbols = symbols or list(DEFAULT_SYMBOLS)
        self.errors: dict[str, str] = {}

    def get_account(self) -> dict:
        raise NotImplementedError

    def get_positions(self) -> list[dict]:
        raise NotImplementedError

    def get_bars(self, symbol: str) -> Optional[pd.DataFrame]:
        raise NotImplementedError

    def get_spread(self, symbol: str) -> float:
        return float("nan")

    def get_closed_trades(self) -> list[dict]:
        return []


# --------------------------------------------------------------------------- #
# Demo provider
# --------------------------------------------------------------------------- #
class DemoProvider(BaseProvider):
    mode = "DEMO"
    name = "synthetic-demo"

    # base price + drift per symbol to create varied regimes
    _SPEC = {
        "EURUSD": (1.08, 0.0002, 0.004),
        "GBPUSD": (1.27, 0.0006, 0.006),
        "XAUUSD": (2350.0, 1.5, 18.0),
        "NAS100": (18500.0, 12.0, 160.0),
        "US30": (39000.0, 9.0, 220.0),
        "BTCUSD": (64000.0, 60.0, 1500.0),
    }

    def __init__(self, symbols: list[str] | None = None, seed: int = 7):
        super().__init__(symbols)
        self._seed = seed
        self._bars: dict[str, pd.DataFrame] = {}

    def _gen(self, symbol: str) -> pd.DataFrame:
        if symbol in self._bars:
            return self._bars[symbol]
        base, drift, vol = self._SPEC.get(symbol, (100.0, 0.05, 1.0))
        rng = np.random.default_rng(abs(hash((symbol, self._seed))) % (2**32))
        n = 320
        # alternate trend/range phases for visual variety
        steps = rng.normal(0, vol, n)
        trend = np.sin(np.linspace(0, 6, n)) * drift * 40
        closes = base + np.cumsum(steps) + trend
        closes = np.maximum(closes, base * 0.2)
        highs = closes + np.abs(rng.normal(0, vol * 0.6, n))
        lows = closes - np.abs(rng.normal(0, vol * 0.6, n))
        opens = np.concatenate([[closes[0]], closes[:-1]])
        volume = rng.integers(800, 5000, n).astype(float)
        df = pd.DataFrame({"open": opens, "high": highs, "low": lows,
                           "close": closes, "volume": volume})
        self._bars[symbol] = df
        return df

    def get_bars(self, symbol: str) -> Optional[pd.DataFrame]:
        return self._gen(symbol)

    def get_spread(self, symbol: str) -> float:
        base = self._SPEC.get(symbol, (100.0, 0, 0))[0]
        return round(base * 0.00008, 5)

    def get_account(self) -> dict:
        bal = 9633.77
        open_pnl = round(sum(p["pnl"] for p in self.get_positions()), 2)
        return {
            "balance": bal,
            "equity": round(bal + open_pnl, 2),
            "open_pnl": open_pnl,
            "daily_pnl": -61.86,
            "closed_pnl": -61.86,
            "monthly_pnl": 142.40,
            "total_revenue": 142.40,
            "currency": "USD",
            "day_start_equity": bal + 61.86,
            "peak_equity": bal + 320.0,
        }

    def get_positions(self) -> list[dict]:
        return [
            {"platform": "TradeLocker", "symbol": "XAUUSD", "side": "buy",
             "entry": 2348.5, "price": 2353.1, "sl": 2330.0, "tp": 2390.0,
             "qty": 0.01, "pnl": 4.6, "risk_pct": 0.5, "confidence": 0.62,
             "agent": "Trend Agent"},
            {"platform": "TradeLocker", "symbol": "GBPUSD", "side": "sell",
             "entry": 1.2740, "price": 1.2731, "sl": 1.2775, "tp": 1.2650,
             "qty": 0.02, "pnl": 1.8, "risk_pct": 0.4, "confidence": 0.55,
             "agent": "Range Agent"},
        ]

    def get_closed_trades(self) -> list[dict]:
        rng = np.random.default_rng(self._seed)
        out = []
        for i in range(28):
            win = rng.random() < 0.58
            pnl = float(rng.uniform(20, 90)) if win else -float(rng.uniform(15, 55))
            out.append({"pnl": round(pnl, 2), "rr": round(abs(pnl) / 30.0, 2),
                        "symbol": rng.choice(self.symbols)})
        return out


# --------------------------------------------------------------------------- #
# Live provider
# --------------------------------------------------------------------------- #
class LiveProvider(BaseProvider):
    mode = "LIVE"
    name = "tradelocker"

    def __init__(self, cfg, symbols: list[str] | None = None):
        super().__init__(symbols)
        self.cfg = cfg
        self.api = None
        self._iid: dict[str, Optional[int]] = {}
        self._connect()

    def _connect(self) -> None:
        from tradelocker import TLAPI  # lazy import
        c = self.cfg.credentials
        kwargs = dict(environment=c.environment, username=c.username,
                      password=c.password, server=c.server)
        try:
            if c.account_id:
                try:
                    self.api = TLAPI(acc_num=int(c.account_id), **kwargs)
                except (ValueError, TypeError):
                    self.api = TLAPI(account_id=int(c.account_id), **kwargs)
            else:
                self.api = TLAPI(**kwargs)
        except Exception as exc:  # pragma: no cover - network
            self.errors["connection"] = str(exc)
            logger.error("Live connect failed: %s", exc)
            self.api = None

    def _instrument_id(self, symbol: str) -> Optional[int]:
        if symbol in self._iid:
            return self._iid[symbol]
        iid = None
        if self.api is not None:
            for name in (symbol, f"{symbol}.R", f"{symbol}.r", symbol.replace("USD", "USD.R")):
                try:
                    iid = self.api.get_instrument_id_from_symbol_name(name)
                except Exception:  # pragma: no cover - network
                    iid = None
                if iid is not None:
                    break
        self._iid[symbol] = iid
        return iid

    def get_bars(self, symbol: str) -> Optional[pd.DataFrame]:
        if self.api is None:
            return None
        iid = self._instrument_id(symbol)
        if iid is None:
            self.errors[f"bars:{symbol}"] = "symbol not found"
            return None
        try:
            df = self.api.get_price_history(iid, resolution="1D", lookback_period="400D")
        except Exception as exc:  # pragma: no cover - network
            self.errors[f"bars:{symbol}"] = str(exc)
            return None
        if df is None or len(df) == 0:
            return None
        df = df.rename(columns={"o": "open", "h": "high", "l": "low",
                                "c": "close", "v": "volume"})
        keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
        return df[keep].astype(float).reset_index(drop=True)

    def get_spread(self, symbol: str) -> float:
        if self.api is None:
            return float("nan")
        iid = self._instrument_id(symbol)
        if iid is None:
            return float("nan")
        try:
            ask = self.api.get_latest_asking_price(iid)
            bid = self.api.get_latest_bid_price(iid)
            return round(float(ask) - float(bid), 6)
        except Exception:  # pragma: no cover - network
            return float("nan")

    def get_account(self) -> dict:
        if self.api is None:
            return {}
        try:
            st = self.api.get_account_state()
        except Exception as exc:  # pragma: no cover - network
            self.errors["account"] = str(exc)
            return {}
        bal = float(st.get("balance", 0.0))
        eq = float(st.get("projectedBalance", bal))
        return {
            "balance": round(bal, 2),
            "equity": round(eq, 2),
            "open_pnl": round(float(st.get("openNetPnL", 0.0)), 2),
            "daily_pnl": round(float(st.get("todayNet", 0.0)), 2),
            "closed_pnl": round(float(st.get("todayNet", 0.0)), 2),
            "monthly_pnl": None,
            "total_revenue": None,
            "currency": "USD",
            "day_start_equity": round(eq - float(st.get("todayNet", 0.0)), 2),
            "peak_equity": round(eq, 2),
            "positions_count": int(st.get("positionsCount", 0)),
        }

    def get_positions(self) -> list[dict]:
        if self.api is None:
            return []
        try:
            df = self.api.get_all_positions()
        except Exception as exc:  # pragma: no cover - network
            self.errors["positions"] = str(exc)
            return []
        if df is None or df.empty:
            return []
        out = []
        for _, r in df.iterrows():
            out.append({
                "platform": "TradeLocker",
                "symbol": str(r.get("tradableInstrumentId", "")),
                "side": r.get("side", ""),
                "entry": float(r.get("avgPrice", 0.0) or 0.0),
                "price": float("nan"),
                "sl": None,
                "tp": None,
                "qty": float(r.get("qty", 0.0) or 0.0),
                "pnl": float(r.get("unrealizedPl", 0.0) or 0.0),
                "risk_pct": None,
                "confidence": None,
                "agent": "Execution Agent",
            })
        return out

    def get_closed_trades(self) -> list[dict]:
        if self.api is None:
            return []
        for getter in ("get_all_executions", "get_orders_history", "get_all_orders"):
            fn = getattr(self.api, getter, None)
            if fn is None:
                continue
            try:
                df = fn()
            except Exception:  # pragma: no cover - network
                continue
            if df is None or getattr(df, "empty", True):
                continue
            pnl_col = next((c for c in ("pnl", "netPnL", "realizedPl", "profit")
                            if c in df.columns), None)
            if pnl_col is None:
                continue
            return [{"pnl": float(v)} for v in df[pnl_col].tolist() if v is not None]
        return []
