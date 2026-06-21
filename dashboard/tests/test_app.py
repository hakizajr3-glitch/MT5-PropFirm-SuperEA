import importlib


def _client(monkeypatch):
    monkeypatch.delenv("SHROUD_LIVE", raising=False)
    monkeypatch.setenv("TL_POLL_SECONDS", "1")
    app_mod = importlib.import_module("dashboard.app")
    app_mod.app.config["TESTING"] = True
    return app_mod


def test_start_stop_endpoints(monkeypatch):
    app_mod = _client(monkeypatch)
    client = app_mod.app.test_client()
    try:
        r = client.post("/api/start")
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["engine"]["running"] is True

        # /api/state must reflect the running engine
        s = client.get("/api/state").get_json()
        assert s["engine"]["running"] is True

        r = client.post("/api/stop")
        body = r.get_json()
        assert body["engine"]["running"] is False

        s = client.get("/api/state").get_json()
        assert s["engine"]["running"] is False
    finally:
        app_mod.ENGINE.stop()


def test_healthz(monkeypatch):
    app_mod = _client(monkeypatch)
    client = app_mod.app.test_client()
    assert client.get("/healthz").get_json() == {"ok": True}
