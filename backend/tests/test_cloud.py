"""Chế độ cloud: nhiều tài khoản, API key mã hóa theo user, hàng đợi việc cho agent."""
import dataclasses
import os

for _k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
    os.environ[_k] = ""

import time

import pytest
from fastapi.testclient import TestClient

from feedlens import ai, api, auth, config, crypto
from feedlens.ai import registry
from feedlens.config import _normalize_db_url
from feedlens.db import Database

SECRET = "s" * 40
POSTS = [{"platform": "facebook", "source": "g", "text": "Tuyển Python dev remote, lương 30tr"},
         {"platform": "facebook", "source": "g", "text": "Thanh lý xe máy giá rẻ"}]


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    original_db = api.app.state.db

    def make(**over):
        s = dataclasses.replace(config.settings, **{"mode": "cloud", "secret": SECRET, "allow_signup": True, **over})
        for mod in (auth, api, crypto, registry):
            monkeypatch.setattr(mod, "settings", s)
        api.app.state.db = Database(f"sqlite:///{(tmp_path / 'c.db').as_posix()}")
        api._attempts.clear()
        registry._MODEL_CACHE.clear()
        return TestClient(api.app)

    yield make
    api.app.state.db = original_db


def _signup(c, email="a@x.io", pw="password1") -> dict:
    r = c.post("/api/auth/register", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _agent(c, h) -> dict:
    return {"Authorization": f"Bearer {c.post('/api/agent/token', headers=h).json()['token']}"}


def _wait(c, h, run_id, until=("done", "error")):
    for _ in range(100):
        r = c.get(f"/api/runs/{run_id}", headers=h).json()
        if r["status"] in until:
            return r
        time.sleep(0.03)
    return r


def test_db_url_normalized():
    assert _normalize_db_url("postgres://u:p@h:5432/d") == "postgresql+psycopg://u:p@h:5432/d"
    assert _normalize_db_url("postgresql://u@h/d") == "postgresql+psycopg://u@h/d"
    assert _normalize_db_url("sqlite:///x.db") == "sqlite:///x.db"


def test_password_hash_and_encryption(monkeypatch):
    monkeypatch.setattr(crypto, "settings", dataclasses.replace(config.settings, secret=SECRET))
    h = crypto.hash_password("hunter22")
    assert crypto.verify_password("hunter22", h) and not crypto.verify_password("nope", h)
    enc = crypto.encrypt("sk-secret-123")
    assert "sk-secret" not in enc and crypto.decrypt(enc) == "sk-secret-123"
    monkeypatch.setattr(crypto, "settings", dataclasses.replace(config.settings, secret="t" * 40))
    assert crypto.decrypt(enc) is None  # đổi secret -> key cũ không đọc được, không crash


def test_register_login_and_lockout(cloud):
    c = cloud()
    assert c.get("/api/runs").status_code == 401
    h = _signup(c)
    assert c.get("/api/auth/me", headers=h).json()["email"] == "a@x.io"
    assert c.post("/api/auth/register", json={"email": "A@x.io", "password": "password1"}).status_code == 409
    assert c.post("/api/auth/register", json={"email": "bad", "password": "password1"}).status_code == 400
    assert c.post("/api/auth/register", json={"email": "b@x.io", "password": "short"}).status_code == 400
    assert c.post("/api/auth/login", json={"email": "a@x.io", "password": "wrong"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "a@x.io", "password": "password1"}).status_code == 200
    for _ in range(api.LOGIN_MAX_FAILS):
        c.post("/api/auth/login", json={"email": "a@x.io", "password": "wrong"})
    assert c.post("/api/auth/login", json={"email": "a@x.io", "password": "password1"}).status_code == 429


def test_signup_can_be_closed(cloud):
    c = cloud(allow_signup=False)
    assert c.post("/api/auth/register", json={"email": "a@x.io", "password": "password1"}).status_code == 403
    assert c.get("/api/meta").json()["signup_open"] is False


def test_fails_closed_without_secret(cloud):
    c = cloud(secret="")
    assert c.get("/api/runs").status_code == 503
    assert "FEEDLENS_SECRET" in c.get("/api/meta").json()["config_error"]


def test_expired_token_rejected(cloud, monkeypatch):
    c = cloud()
    h = _signup(c)
    monkeypatch.setattr(time, "time", lambda: 10**12)
    assert c.get("/api/runs", headers=h).status_code == 401


class StubProvider(ai.AIProvider):
    info = ai.ProviderInfo("gemini", "Gemini", "GEMINI_API_KEY", "GEMINI_MODEL", "gemini-x", "")

    def complete_json(self, *a, **k):
        raise AssertionError("không gọi AI trong test này")

    def list_models(self):
        if self.api_key != "good-key-1234":
            raise RuntimeError("API key not valid")
        return ["gemini-x", "gemini-y"]


def test_api_keys_are_per_user_encrypted_and_masked(cloud, monkeypatch):
    monkeypatch.setitem(registry.PROVIDERS, "gemini", StubProvider)
    monkeypatch.setitem(api.PROVIDERS, "gemini", StubProvider)
    monkeypatch.setenv("GEMINI_API_KEY", "owner-env-key")  # cloud KHÔNG được dùng key của chủ server
    c = cloud()
    a, b = _signup(c, "a@x.io"), _signup(c, "b@x.io")
    st = {p["key"]: p for p in c.get("/api/ai/providers", headers=a).json()}
    assert st["gemini"]["configured"] is False

    assert c.put("/api/ai/keys/gemini", headers=a, json={"api_key": "bad-key-0000"}).status_code == 400
    r = c.put("/api/ai/keys/gemini", headers=a, json={"api_key": "good-key-1234"})
    assert r.status_code == 200 and r.json()["models"] == ["gemini-x", "gemini-y"]

    st = {p["key"]: p for p in c.get("/api/ai/providers", headers=a).json()}
    assert st["gemini"]["configured"] and st["gemini"]["hint"] == "…1234"
    assert "good-key" not in c.get("/api/ai/providers", headers=a).text
    row = api.app.state.db.list_keys(1)[0]
    assert "good-key" not in row.ciphertext

    assert c.get("/api/ai/models/gemini", headers=a).json()["models"] == ["gemini-x", "gemini-y"]
    assert c.get("/api/ai/models/gemini", headers=b).status_code == 400  # user B chưa có key
    assert c.post("/api/runs", headers=b, json={"platform": "facebook", "ai_provider": "gemini"}).status_code == 400
    assert c.delete("/api/ai/keys/gemini", headers=a).status_code == 200
    assert c.get("/api/ai/models/gemini", headers=a).status_code == 400


def test_default_model_follows_available_list():
    from feedlens.ai import pick_default
    # model mặc định đã bị khai tử -> chọn bản "flash" mới nhất còn dùng được, tránh lite/preview
    models = ["gemini-omni-flash-preview", "gemini-4-argon", "gemini-3.8-pro", "gemini-3.8-flash-lite",
              "gemini-3.8-flash", "gemini-3.10-flash-image", "gemini-3.5-flash", "gemini-2.5-flash"]
    assert pick_default("gemini", models) == "gemini-3.8-flash"
    assert pick_default("gemini", ["gemini-3.7-flash", "gemini-3.10-flash"]) == "gemini-3.10-flash"
    assert pick_default("gemini", ["gemini-x-pro"]) == "gemini-x-pro"
    assert pick_default("gemini", []) == "gemini-3.5-flash-lite"
    # The default is followed by a Flash fallback from a different release.
    from feedlens.ai.registry import default_candidates
    assert default_candidates("gemini", models + ["gemini-3.5-flash-lite"])[:3] == \
        ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]


def test_default_model_env_override(monkeypatch):
    from feedlens.ai import pick_default
    monkeypatch.setenv("GEMINI_MODEL", "gemini-custom")
    assert pick_default("gemini", ["gemini-3.8-flash"]) == "gemini-custom"


def test_gemini_default_can_finish_when_newest_flash_models_are_unavailable(monkeypatch):
    from feedlens.ai.limits import Limits
    from feedlens.ai.registry import resolve_models
    from feedlens.ai.scheduler import Candidate, QuotaScheduler
    from tests.test_ai_quota import Clock, Provider

    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr("feedlens.ai.registry.list_models", lambda *a: [
        "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash",
    ])
    models = resolve_models(1, "gemini", "fake", None)
    clock = Clock()
    calls = []

    def provider(model):
        client = Provider(model, clock)
        def complete(*args):
            calls.append(model)
            if model == "gemini-3.5-flash":
                return {"ok": True}
            raise RuntimeError("503 UNAVAILABLE")
        client.complete_json = complete
        return client

    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, jitter=lambda delay: delay,
                               default_limits=lambda *a: Limits())
    assert scheduler.complete_json([Candidate(1, provider(model)) for model in models], "", "", {}) == {"ok": True}
    assert calls == ["gemini-3.5-flash-lite", "gemini-3.5-flash"]
    assert clock.value == 0 and len(models) == 3
    assert resolve_models(1, "gemini", "fake", "gemini-3.8-flash") == ["gemini-3.8-flash"]


def test_agent_queue_end_to_end_and_isolation(cloud):
    c = cloud()
    a, b = _signup(c, "a@x.io"), _signup(c, "b@x.io")
    ag = _agent(c, a)
    assert c.get("/api/agent/next", headers=a).status_code == 403  # token web không dùng cho agent
    assert c.get("/api/auth/me", headers=a).json()["agent"]["online"] is False
    assert c.get("/api/agent/next", headers=ag).json() == {"job": None}
    assert c.get("/api/auth/me", headers=a).json()["agent"]["online"] is True

    req = {"platform": "facebook", "source_type": "group", "sources": ["g"], "count": 5,
           "job_mode": True, "keywords": ["python"], "ai_provider": "offline"}
    run_id = c.post("/api/runs", headers=a, json=req).json()["id"]
    assert c.get(f"/api/runs/{run_id}", headers=a).json()["status"] == "pending"
    assert c.get(f"/api/runs/{run_id}", headers=b).status_code == 404       # B không thấy lượt của A
    assert c.get("/api/runs", headers=b).json() == []

    job = c.get("/api/agent/next", headers=ag).json()["job"]
    assert job["id"] == run_id and job["request"]["sources"] == ["g"]
    assert c.get("/api/agent/next", headers=ag).json() == {"job": None}     # không nhận trùng
    assert c.post(f"/api/agent/runs/{run_id}/progress", headers=ag,
                  json={"done": 1, "target": 5, "message": "1/5"}).status_code == 200
    assert c.get(f"/api/runs/{run_id}", headers=a).json()["progress"]["message"] == "1/5"
    assert c.post(f"/api/agent/runs/{run_id}/posts", headers=ag, json={"posts": POSTS}).status_code == 200

    r = _wait(c, a, run_id)
    assert r["status"] == "done", r["error"]
    assert r["collected"] == 2 and any(p["job"] for p in r["posts"])
    assert c.post(f"/api/agent/runs/{run_id}/posts", headers=ag, json={"posts": POSTS}).status_code == 409
    assert c.get(f"/api/runs/{run_id}/export?fmt=csv", headers=a).status_code == 200
    assert c.delete(f"/api/runs/{run_id}", headers=b).status_code == 404
    assert c.delete(f"/api/runs/{run_id}", headers=a).status_code == 200


def test_agent_reports_failure_and_token_rotation(cloud):
    c = cloud()
    a = _signup(c)
    ag = _agent(c, a)
    run_id = c.post("/api/runs", headers=a, json={"platform": "x", "ai_provider": "offline"}).json()["id"]
    c.get("/api/agent/next", headers=ag)
    c.post(f"/api/agent/runs/{run_id}/fail", headers=ag, json={"error": "selector hỏng"})
    r = c.get(f"/api/runs/{run_id}", headers=a).json()
    assert r["status"] == "error" and "selector hỏng" in r["error"]

    new = _agent(c, a)
    assert c.get("/api/agent/next", headers=ag).status_code == 401           # token cũ hết hiệu lực
    assert c.get("/api/agent/next", headers=new).status_code == 200


def test_cloud_blocks_browser_endpoints_and_push_ingest(cloud):
    c = cloud()
    a = _signup(c)
    assert c.post("/api/platforms/facebook/login", headers=a).status_code == 409
    assert c.get("/api/platforms", headers=a).json() == []
    ag = _agent(c, a)
    body = {"request": {"platform": "facebook", "ai_provider": "offline"}, "posts": POSTS}
    run_id = c.post("/api/ingest", headers=ag, json=body).json()["id"]
    assert _wait(c, a, run_id)["status"] == "done"
    assert c.post("/api/ingest", headers=ag, json={**body, "posts": []}).status_code == 422


def test_preferences_saved_per_user(cloud):
    c = cloud()
    a, b = _signup(c, "a@x.io"), _signup(c, "b@x.io")
    assert c.get("/api/preferences", headers=a).json() == {}
    prefs = {"composer": {"platform": "facebook", "count": 60},
             "groups": {"facebook": [{"url": "https://www.facebook.com/groups/vieclamit", "enabled": True}]}}
    assert c.put("/api/preferences", headers=a, json=prefs).status_code == 200
    assert c.get("/api/preferences", headers=a).json() == prefs
    assert c.get("/api/preferences", headers=b).json() == {}
    assert c.put("/api/preferences", headers=a, json=[1, 2]).status_code == 400
    assert c.put("/api/preferences", headers=a, content=b"x" * 70_000).status_code == 413
    assert c.get("/api/preferences").status_code == 401


def test_ui_error_codes_preserve_legacy_details(cloud):
    c = cloud()
    wrong = c.post("/api/auth/login", json={"email": "nobody@x.io", "password": "wrong"})
    assert wrong.status_code == 401
    assert wrong.json() == {"detail": "Sai email hoặc mật khẩu.", "code": "error.invalid_credentials"}
    assert c.get("/api/runs").json()["code"] == "error.session_expired"
    h = _signup(c)
    missing = c.get("/api/runs/999", headers=h)
    assert missing.status_code == 404
    assert missing.json()["code"] == "error.run_missing"
    invalid = c.post("/api/runs", headers=h, json={"platform": "unsupported"})
    assert invalid.status_code == 422 and isinstance(invalid.json()["detail"], list)
    assert invalid.json()["code"] == "error.validation"


def test_ui_progress_and_failures_keep_diagnostics_with_codes(cloud):
    c = cloud()
    h = _signup(c)
    run_id = c.post("/api/runs", headers=h, json={"platform": "facebook", "ai_provider": "offline"}).json()["id"]
    pending = c.get(f"/api/runs/{run_id}", headers=h).json()
    assert pending["progress"]["message_code"] == "progress.pending"
    assert pending["progress"]["message"]
    api.PROGRESS[run_id] = {"phase": "scraping", "done": 2, "target": 10, "message": "Đang chờ xác minh đăng nhập"}
    assert c.get(f"/api/runs/{run_id}", headers=h).json()["progress"]["message_code"] == "progress.verification"
    api.app.state.db.update_run(run_id, status="error", error="Cookie đã hết hiệu lực")
    failed = c.get(f"/api/runs/{run_id}", headers=h).json()
    assert failed["error_code"] == "error.cookie_invalid"
    assert failed["error"] == "Cookie đã hết hiệu lực"
    assert c.get("/api/runs", headers=h).json()[0]["error_code"] == "error.cookie_invalid"


def test_ui_cookie_and_configuration_codes_are_additive(cloud):
    c = cloud(server_scrape=True)
    h = _signup(c)
    saved = c.put("/api/sessions/facebook", headers=h, json={"cookies": "c_user=123456; xs=secret-cookie"})
    assert saved.status_code == 200
    assert saved.json()["status_message_code"] == "ck.statusUnchecked"
    api.app.state.db.set_session_status(1, "facebook", "invalid", "Phiên đã hết hạn")
    session = c.get("/api/sessions", headers=h).json()[0]
    assert session["status_message_code"] == "ck.statusInvalid"
    assert session["status_message"] == "Phiên đã hết hạn"
    missing = c.post("/api/runs", headers=h, json={"platform": "x", "runner": "server", "ai_provider": "offline"})
    assert missing.json()["code"] == "error.cookie_missing"
    c = cloud(secret="")
    meta = c.get("/api/meta").json()
    assert meta["config_error_code"] == "error.config" and "FEEDLENS_SECRET" in meta["config_error"]


@pytest.mark.parametrize("status", [400, 404, 500])
def test_unknown_errors_use_request_context_except_stored_run_failures(cloud, monkeypatch, status):
    c = cloud()
    h = _signup(c)

    def unavailable(*args):
        raise api.HTTPException(status, "Unexpected provider response")

    monkeypatch.setattr(api, "provider_status", unavailable)
    response = c.get("/api/ai/providers", headers=h)
    assert response.status_code == status
    assert response.json() == {"code": "error.request_failed", "detail": "Unexpected provider response"}
    run_id = c.post("/api/runs", headers=h, json={"platform": "facebook", "ai_provider": "offline"}).json()["id"]
    api.app.state.db.update_run(run_id, status="error", error="Unexpected provider response")
    assert c.get(f"/api/runs/{run_id}", headers=h).json()["error_code"] == "error.run_failed"
    assert c.get("/api/runs", headers=h).json()[0]["error_code"] == "error.run_failed"


def test_local_platform_session_is_unknown_until_explicit_check(cloud, tmp_path, monkeypatch):
    client = cloud(mode="local")
    monkeypatch.setattr(api, "_session_cache", {})
    monkeypatch.setattr(api, "_login_state", {})
    monkeypatch.setattr(api, "_session_started", True)  # Startup worker is covered separately; inspect manual checks here.
    monkeypatch.setattr(api.browser, "profile_dir", lambda platform: tmp_path / platform)
    (tmp_path / "facebook").mkdir()
    monkeypatch.setattr(api.browser, "check_session", lambda platform: platform == "facebook")
    platforms = {p["key"]: p for p in client.get("/api/platforms").json()}
    assert platforms["facebook"]["has_profile"] is True
    assert all(p["logged_in"] is None for p in platforms.values())
    assert client.post("/api/platforms/facebook/check").json()["logged_in"] is True
    assert client.post("/api/platforms/linkedin/check").json()["logged_in"] is False
    platforms = {p["key"]: p for p in client.get("/api/platforms").json()}
    assert platforms["facebook"]["logged_in"] is True
    assert platforms["linkedin"]["logged_in"] is False
    assert platforms["reddit"]["logged_in"] is None
