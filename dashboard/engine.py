"""Autonomous trading engine controller for the dashboard.

The dashboard's Start/Stop buttons drive a single :class:`TradeEngine`. When
started it runs the autonomous trading loop in a background thread:

    connect -> scan markets -> compute signal -> open/manage/close trades

In LIVE mode (``SHROUD_LIVE=true`` with valid ``TL_*`` credentials) it runs the
real :class:`tradelocker_bot.bot.TradeLockerBot` loop and places real orders on
the connected TradeLocker account. Without live credentials it runs a DEMO loop
that scans on the same cadence but never sends orders, so the control flow is
fully exercisable without a broker connection.

Risk SAFE MODE still overrides everything: the underlying bot's
:class:`RiskManager` refuses entries (and closes out) when a limit is breached,
even while the engine is "started".
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone

logger = logging.getLogger("shroudage.engine")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_live() -> bool:
    return os.getenv("SHROUD_LIVE", "").lower() in ("1", "true", "yes", "on")


class TradeEngine:
    """Thread-backed controller for the autonomous trading loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._mode = "DEMO"
        self._started_at: str | None = None
        self._stopped_at: str | None = None
        self._last_cycle_at: str | None = None
        self._cycles = 0
        self._last_action = "idle"
        self._last_error: str | None = None

    # ---- public control ---------------------------------------------
    def start(self) -> dict:
        with self._lock:
            if self._running:
                return self._status_locked()
            self._stop.clear()
            self._running = True
            self._mode = "LIVE" if _is_live() else "DEMO"
            self._started_at = _now()
            self._stopped_at = None
            self._cycles = 0
            self._last_error = None
            self._last_action = "starting"
            self._thread = threading.Thread(
                target=self._run_loop, name="shroudage-engine", daemon=True
            )
            self._thread.start()
            logger.info("Engine started (mode=%s)", self._mode)
            return self._status_locked()

    def stop(self) -> dict:
        with self._lock:
            if not self._running and self._thread is None:
                self._last_action = "stopped"
                return self._status_locked()
            self._stop.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=10.0)
        with self._lock:
            self._running = False
            self._thread = None
            self._stopped_at = _now()
            self._last_action = "stopped"
            logger.info("Engine stopped after %d cycle(s)", self._cycles)
            return self._status_locked()

    def status(self) -> dict:
        with self._lock:
            return self._status_locked()

    # ---- internal ----------------------------------------------------
    def _status_locked(self) -> dict:
        return {
            "running": self._running,
            "mode": self._mode,
            "started_at": self._started_at,
            "stopped_at": self._stopped_at,
            "last_cycle_at": self._last_cycle_at,
            "cycles": self._cycles,
            "last_action": self._last_action,
            "last_error": self._last_error,
        }

    def _poll_seconds(self) -> float:
        try:
            return float(os.getenv("TL_POLL_SECONDS", "30"))
        except ValueError:
            return 30.0

    def _run_loop(self) -> None:
        if self._mode == "LIVE":
            self._run_live()
        else:
            self._run_demo()

    def _run_live(self) -> None:
        try:
            from tradelocker_bot.bot import TradeLockerBot
            from tradelocker_bot.config import BotConfig

            cfg = BotConfig.from_env()
            bot = TradeLockerBot(cfg)
            bot.connect()
        except Exception as exc:  # connection / config failure
            logger.exception("Engine failed to start live bot: %s", exc)
            with self._lock:
                self._last_error = str(exc)
                self._last_action = "connect failed"
                self._running = False
                self._stopped_at = _now()
            return

        with self._lock:
            self._last_action = "connected; scanning"
        poll = self._poll_seconds()
        while not self._stop.is_set():
            try:
                bot.run_once()
                with self._lock:
                    self._cycles += 1
                    self._last_cycle_at = _now()
                    self._last_action = "scanned market / managed trades"
                    self._last_error = None
            except Exception as exc:  # resilience: keep looping
                logger.exception("Engine live cycle error: %s", exc)
                with self._lock:
                    self._last_error = str(exc)
                    self._last_action = "cycle error"
            self._stop.wait(poll)

    def _run_demo(self) -> None:
        with self._lock:
            self._last_action = "scanning (demo — no live orders)"
        # Demo cadence is faster so the UI shows visible cycle progress.
        poll = min(self._poll_seconds(), 5.0)
        while not self._stop.is_set():
            with self._lock:
                self._cycles += 1
                self._last_cycle_at = _now()
                self._last_action = "scanning (demo — no live orders)"
            self._stop.wait(poll)


# Process-wide singleton used by the Flask app.
ENGINE = TradeEngine()
