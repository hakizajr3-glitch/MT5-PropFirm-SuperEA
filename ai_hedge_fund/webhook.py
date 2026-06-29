"""TradingView webhook receiver.

Listens for TradingView alert webhooks and converts them into agent-compatible
signals that feed into the AI Hedge Fund pipeline. Registers as a Flask
blueprint so it plugs into the existing SHROUDAGE dashboard.

TradingView alert message format (JSON):
{
    "symbol": "EURUSD",
    "action": "buy",          // buy, sell, close
    "price": 1.0850,
    "timeframe": "1H",
    "strategy": "EMA_Cross",  // optional label
    "comment": "EMA20 crossed above EMA50"
}

Endpoint: POST /webhook/tradingview
Auth: simple token in the ``Authorization: Bearer <token>`` header.
"""

from __future__ import annotations

import hmac
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

logger = logging.getLogger("ai_hedge_fund.webhook")

webhook_bp = Blueprint("webhook", __name__, url_prefix="/webhook")

# In-memory store for recent webhook signals (last 100)
_MAX_HISTORY = 100
_webhook_signals: list[dict] = []
_lock = __import__("threading").Lock()


def _auth_ok() -> bool:
    """Validate the bearer token if WEBHOOK_SECRET is configured."""
    secret = os.getenv("WEBHOOK_SECRET", "")
    if not secret:
        return True   # no secret = open (development mode)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return hmac.compare_digest(auth[7:], secret)
    return False


def get_webhook_signals() -> list[dict]:
    with _lock:
        return list(_webhook_signals)


@webhook_bp.route("/tradingview", methods=["POST"])
def tradingview_alert():
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    if not data:
        # TradingView sometimes sends plain text
        text = request.get_data(as_text=True).strip()
        if text:
            data = {"raw": text}

    symbol = str(data.get("symbol", "UNKNOWN")).upper()
    action = str(data.get("action", "")).lower()
    raw_price = data.get("price")
    timeframe = data.get("timeframe", "")
    comment = data.get("comment", "")

    parsed_price = None
    if raw_price is not None:
        try:
            parsed_price = float(raw_price)
        except (ValueError, TypeError):
            return jsonify({"error": "invalid price value", "price": str(raw_price)}), 400

    signal_record = {
        "source": "tradingview",
        "symbol": symbol,
        "action": action,
        "price": parsed_price,
        "timeframe": timeframe,
        "comment": comment,
        "raw": data,
        "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timestamp": time.time(),
    }

    with _lock:
        _webhook_signals.append(signal_record)
        if len(_webhook_signals) > _MAX_HISTORY:
            _webhook_signals.pop(0)

    logger.info("TV webhook: %s %s @ %s — %s", action.upper(), symbol, parsed_price, comment)

    return jsonify({"ok": True, "received": signal_record}), 200


@webhook_bp.route("/signals", methods=["GET"])
def list_signals():
    """Return recent webhook signals (for dashboard display)."""
    return jsonify(get_webhook_signals())


@webhook_bp.route("/health", methods=["GET"])
def webhook_health():
    return jsonify({
        "ok": True,
        "signals_count": len(_webhook_signals),
        "webhook_secret_configured": bool(os.getenv("WEBHOOK_SECRET", "")),
    })
