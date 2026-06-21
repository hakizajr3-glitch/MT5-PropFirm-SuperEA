"""SHROUDAGE dashboard web server (Flask).

Run:
    python -m dashboard.app            # demo data (no credentials needed)
    SHROUD_LIVE=true python -m dashboard.app   # live TradeLocker account

Env:
    SHROUD_LIVE   "true" to use the live TradeLocker account (needs TL_* creds)
    SHROUD_MODE   DRY RUN | LIVE | SAFE MODE | HALTED  (requested mode label)
    SHROUD_SYMBOLS  comma list (default EURUSD,GBPUSD,XAUUSD,NAS100,US30,BTCUSD)
    DASH_HOST / DASH_PORT   bind address (default 0.0.0.0:8787)
    SHROUD_REFRESH_SECS  server-side cache TTL (default 5)
"""

from __future__ import annotations

import logging
import os
import threading
import time

from flask import Flask, jsonify, render_template

from .engine import ENGINE
from .providers import DEFAULT_SYMBOLS, DemoProvider, LiveProvider
from .state import DashboardConfig, build_state

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("shroudage.app")

app = Flask(__name__)

_lock = threading.Lock()
_cache = {"ts": 0.0, "state": None}
_provider = None


def _symbols() -> list[str]:
    raw = os.getenv("SHROUD_SYMBOLS", "")
    if raw.strip():
        return [s.strip().upper() for s in raw.split(",") if s.strip()]
    return list(DEFAULT_SYMBOLS)


def _make_provider():
    live = os.getenv("SHROUD_LIVE", "").lower() in ("1", "true", "yes", "on")
    symbols = _symbols()
    if live:
        try:
            from tradelocker_bot.config import BotConfig
            cfg = BotConfig.from_env()
            logger.info("Starting LIVE provider (TradeLocker)")
            return LiveProvider(cfg, symbols=symbols)
        except Exception as exc:
            logger.error("Live provider unavailable (%s); falling back to demo", exc)
    logger.info("Starting DEMO provider (synthetic data)")
    return DemoProvider(symbols=symbols)


def get_provider():
    global _provider
    if _provider is None:
        _provider = _make_provider()
    return _provider


def _invalidate_cache() -> None:
    with _lock:
        _cache.update(ts=0.0, state=None)


def get_state() -> dict:
    ttl = float(os.getenv("SHROUD_REFRESH_SECS", "5"))
    now = time.time()
    with _lock:
        if _cache["state"] is not None and now - _cache["ts"] < ttl:
            return _cache["state"]
        cfg = DashboardConfig.from_env()
        if get_provider().mode == "LIVE" and cfg.mode == "DRY RUN":
            cfg.mode = "LIVE"
        state = build_state(get_provider(), cfg, engine=ENGINE.status())
        _cache.update(ts=now, state=state)
        return state


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify(get_state())


@app.route("/api/start", methods=["POST"])
def api_start():
    status = ENGINE.start()
    _invalidate_cache()
    logger.info("Engine start requested via dashboard")
    return jsonify({"ok": True, "engine": status})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    status = ENGINE.stop()
    _invalidate_cache()
    logger.info("Engine stop requested via dashboard")
    return jsonify({"ok": True, "engine": status})


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True})


def main():
    host = os.getenv("DASH_HOST", "0.0.0.0")
    port = int(os.getenv("DASH_PORT", "8787"))
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
