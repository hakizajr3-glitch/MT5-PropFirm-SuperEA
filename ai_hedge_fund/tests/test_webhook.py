"""Tests for the TradingView webhook receiver."""

from __future__ import annotations

import json
import os
import pytest

import ai_hedge_fund.webhook as webhook_module
from dashboard.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    webhook_module._webhook_signals.clear()
    with app.test_client() as c:
        yield c
    webhook_module._webhook_signals.clear()


class TestWebhook:
    def test_health(self, client):
        resp = client.get("/webhook/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True

    def test_tradingview_alert(self, client):
        payload = {
            "symbol": "EURUSD",
            "action": "buy",
            "price": 1.085,
            "timeframe": "1H",
            "comment": "EMA cross up",
        }
        resp = client.post("/webhook/tradingview",
                           data=json.dumps(payload),
                           content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["received"]["symbol"] == "EURUSD"
        assert data["received"]["action"] == "buy"

    def test_signals_list(self, client):
        # post a signal first
        client.post("/webhook/tradingview",
                    data=json.dumps({"symbol": "XAUUSD", "action": "sell"}),
                    content_type="application/json")
        resp = client.get("/webhook/signals")
        assert resp.status_code == 200
        signals = resp.get_json()
        assert any(s["symbol"] == "XAUUSD" for s in signals)

    def test_plain_text_alert(self, client):
        resp = client.post("/webhook/tradingview",
                           data="BUY GBPUSD",
                           content_type="text/plain")
        assert resp.status_code == 200

    def test_invalid_price_returns_400(self, client):
        payload = {"symbol": "EURUSD", "action": "buy", "price": "not-a-number"}
        resp = client.post("/webhook/tradingview",
                           data=json.dumps(payload),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_auth_blocks_without_token(self, client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", "mysecret123")
        payload = {"symbol": "EURUSD", "action": "buy"}
        resp = client.post("/webhook/tradingview",
                           data=json.dumps(payload),
                           content_type="application/json")
        assert resp.status_code == 401

    def test_auth_wrong_token(self, client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", "mysecret123")
        payload = {"symbol": "EURUSD", "action": "buy"}
        resp = client.post("/webhook/tradingview",
                           data=json.dumps(payload),
                           content_type="application/json",
                           headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_auth_correct_token(self, client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", "mysecret123")
        payload = {"symbol": "EURUSD", "action": "buy"}
        resp = client.post("/webhook/tradingview",
                           data=json.dumps(payload),
                           content_type="application/json",
                           headers={"Authorization": "Bearer mysecret123"})
        assert resp.status_code == 200
