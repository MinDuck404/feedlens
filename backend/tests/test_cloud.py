import dataclasses
import os

for _k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
    os.environ[_k] = ""

import time

import pytest
from fastapi.testclient import TestClient

from feedlens import api, auth, config
from feedlens.config import _normalize_db_url
from feedlens.db import Database

SECRET = "s" * 40


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    def make(**over):
        fields = {"mode": "cloud", "password": "pw-test", "secret": SECRET, "api_token": "agent-token", **over}
        s = dataclasses.replace(config.settings, **fields)
        monkeypatch.setattr(auth, "settings", s)
        monkeypatch.setattr(api, "settings", s)
        monkeypatch.setattr(api, "db", Database(f"sqlite:///{(tmp_path / 'c.db').as_posix()}"))
        api._failed_logins.clear()
        return TestClient(api.app)
    return make


def _login(c) -> dict:
    tok = c.post("/api/auth/login", json={"password": "pw-test"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_db_url_normalized():
    assert _normalize_db_url("postgres://u:p@h:5432/d") == "postgresql+psycopg://u:p@h:5432/d"
    assert _normalize_db_url("postgresql://u@h/d") == "postgresql+psycopg://u@h/d"
    assert _normalize_db_url("sqlite:///x.db") == "sqlite:///x.db"


def test_cloud_requires_auth(cloud):
    c = cloud()
    assert c.get("/api/health").status_code == 200
    m = c.get("/api/meta").json()
    assert m["mode"] == "cloud" and m["auth_required"] and m["config_error"] is None
    assert c.get("/api/runs").status_code == 401
    assert c.get("/api/runs", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert c.get("/api/runs", headers=_login(c)).status_code == 200
    assert c.get("/api/runs", headers={"Authorization": "Bearer agent-token"}).status_code == 200


def test_cloud_fails_closed_without_password(cloud):
    c = cloud(password="")
    assert c.get("/api/runs").status_code == 503
    assert c.post("/api/auth/login", json={"password": ""}).status_code == 503
    assert "FEEDLENS_PASSWORD" in c.get("/api/meta").json()["config_error"]


def test_login_rate_limited(cloud):
    c = cloud()
    for _ in range(api.LOGIN_MAX_FAILS):
        c.post("/api/auth/login", json={"password": "x"})
    assert c.post("/api/auth/login", json={"password": "pw-test"}).status_code == 429


def test_expired_token_rejected(cloud, monkeypatch):
    c = cloud()
    h = _login(c)
    monkeypatch.setattr(time, "time", lambda: 10**12)
    assert c.get("/api/runs", headers=h).status_code == 401


def test_cloud_blocks_browser_endpoints_and_accepts_ingest(cloud):
    c = cloud()
    h = {"Authorization": "Bearer agent-token"}
    assert c.post("/api/platforms/facebook/login", headers=h).status_code == 409
    assert c.post("/api/runs", headers=h, json={"platform": "facebook"}).status_code == 409
    assert c.get("/api/platforms", headers=h).json() == []

    body = {"request": {"platform": "facebook", "source_type": "group", "sources": ["g"],
                        "job_mode": True, "keywords": ["python"], "ai_provider": "offline"},
            "posts": [{"platform": "facebook", "source": "g", "text": "Tuyển Python dev remote, lương 30tr"},
                      {"platform": "facebook", "source": "g", "text": "Thanh lý xe máy giá rẻ"}]}
    run_id = c.post("/api/ingest", headers=h, json=body).json()["id"]
    for _ in range(50):
        r = c.get(f"/api/runs/{run_id}", headers=h).json()
        if r["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert r["status"] == "done", r["error"]
    assert r["collected"] == 2 and any(p["job"] for p in r["posts"])
    assert c.get(f"/api/runs/{run_id}/export?fmt=csv", headers=h).status_code == 200
    assert c.post("/api/ingest", headers=h, json={**body, "posts": []}).status_code == 422
