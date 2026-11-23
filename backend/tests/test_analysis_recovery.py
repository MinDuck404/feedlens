import re
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from feedlens import api, browser, pipeline
from feedlens.analyzer import CLASSIFY_SCHEMA, HeuristicAnalyzer, LLMAnalyzer
from feedlens.db import Database
from feedlens.messages import error_code
from feedlens.models import RawPost, RunRequest
from tests.test_cloud import cloud, _signup


def test_existing_database_adds_raw_storage_without_losing_runs(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    db = Database(url)
    rid = db.create_run(RunRequest(platform="facebook"))
    with db.engine.begin() as conn:
        conn.execute(text("ALTER TABLE runs DROP COLUMN raw_posts"))
    db.engine.dispose()
    upgraded = Database(url)
    raw = [RawPost(platform="facebook", source="feed", text="New raw storage")]
    upgraded.save_raw_posts(rid, raw)
    assert upgraded.get_run(rid)["request"]["platform"] == "facebook"
    assert upgraded.get_raw_posts(rid) == raw


def test_raw_and_successful_batches_survive_failure_and_retry_only_missing(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'recovery.db'}")
    req = RunRequest(platform="facebook", ai_provider="offline", only_new=True)
    rid = db.create_run(req)
    raw = [RawPost(platform="facebook", source="group", author="Author", text=f"Post {i}" + (" FAIL" if i == 2 else ""), url=f"https://example.test/posts/{i}") for i in range(6)]
    analyzer = LLMAnalyzer(SimpleNamespace(info=SimpleNamespace(name="Fake"), model="fake"))
    failed = [True]
    calls = []
    def structured(prompt, schema, effort):
        assert len(db.get_raw_posts(rid)) == 6  # Committed before any provider call.
        if schema is not CLASSIFY_SCHEMA:
            return {"overall": "Summary", "categories": [], "action_items": []}
        calls.append(prompt)
        if failed[0] and "FAIL" in prompt:
            raise RuntimeError("401 Unauthorized")
        return {"items": [{"id": int(i), "category": "news", "summary": "Read", "is_job": False, "job": {}}
                          for i in re.findall(r'<post id="(\d+)"', prompt)]}
    monkeypatch.setattr(analyzer, "_json_call", structured)
    monkeypatch.setattr("feedlens.analyzer.BATCH_SIZE", 2)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: analyzer)
    scrapes = []
    monkeypatch.setattr(pipeline, "scrape", lambda *args: scrapes.append(True) or raw)
    pipeline.execute_run(db, rid, req)
    assert db.get_run(rid)["status"] == "analysis_failed"
    completed = {p.fingerprint: p.id for p in db.get_posts(rid) if p.analyzed}
    assert len(completed) == 4
    assert sum(p.analyzed for p in db.get_posts(rid, include_raw=True)) == 4
    failed[0] = False
    calls.clear()
    pipeline.execute_analysis(db, rid, req, db.get_raw_posts(rid), None)
    assert len(calls) == 1 and "FAIL" in calls[0]
    assert len(scrapes) == 1
    assert db.get_run(rid)["status"] == "done" and db.get_run(rid)["error"] is None
    assert len(db.get_posts(rid)) == 6
    assert all(p.id == completed[p.fingerprint] for p in db.get_posts(rid) if p.fingerprint in completed)


def test_agent_raw_is_saved_even_if_analyzer_cannot_be_created(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'key.db'}")
    req = RunRequest(platform="facebook")
    rid = db.create_run(req)
    raw = [RawPost(platform="facebook", source="group", text="Saved before key lookup")]
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: (_ for _ in ()).throw(ValueError("Chưa có API key")))
    pipeline.execute_analysis(db, rid, req, raw, None)
    assert db.get_raw_posts(rid) == raw
    assert db.get_run(rid)["status"] == "analysis_failed"
    db.fail_interrupted()  # Terminal failure remains terminal.
    db.update_run(rid, status="analyzing")
    assert db.fail_interrupted() == 1
    assert db.get_run(rid)["status"] == "analysis_failed"


def test_digest_failure_retries_digest_without_classifying_again(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'digest.db'}")
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = db.create_run(req)
    raw = [RawPost(platform="facebook", source="feed", text="Python developer remote")]
    analyzer = HeuristicAnalyzer()
    digest = analyzer.digest
    monkeypatch.setattr(analyzer, "digest", lambda *a: (_ for _ in ()).throw(RuntimeError("503 unavailable")))
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a: analyzer)
    pipeline.execute_analysis(db, rid, req, raw, None)
    assert db.get_run(rid)["status"] == "analysis_failed"
    assert len(db.get_posts(rid)) == 1
    monkeypatch.setattr(analyzer, "classify", lambda *a: pytest.fail("Completed post classified again"))
    monkeypatch.setattr(analyzer, "digest", digest)
    pipeline.execute_analysis(db, rid, req, raw, None)
    assert db.get_run(rid)["status"] == "done"


def test_retry_api_exports_raw_and_checks_ownership_and_active_state(cloud, monkeypatch):
    client = cloud()
    a, b = _signup(client), _signup(client, "other@example.test")
    user_id = api.app.state.db.get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = api.db().create_run(req, user_id)
    raw = [RawPost(platform="facebook", source="group", author="Alice", text="Raw text still readable", url="https://example.test/post")]
    api.db().save_raw_posts(rid, raw)
    pipeline.fail_run(api.db(), rid, "401 Unauthorized")
    r = client.get(f"/api/runs/{rid}", headers=a).json()
    assert r["error_code"] == "error.ai_auth" and r["posts"][0]["analyzed"] is False
    for fmt in ("md", "json"):
        result = client.get(f"/api/runs/{rid}/export?fmt={fmt}", headers=a)
        assert result.status_code == 200
        assert all(s in result.text for s in ("Alice", "Raw text still readable", "https://example.test/post"))
    assert client.post(f"/api/runs/{rid}/analysis", headers=b, json={"ai_provider": "offline"}).status_code == 404
    calls = []
    monkeypatch.setattr(pipeline, "_spawn", lambda *a: calls.append(a))
    assert client.post(f"/api/runs/{rid}/analysis", headers=a, json={"ai_provider": "auto", "ai_model": "new-model"}).status_code == 200
    assert calls and calls[0][0] is pipeline.execute_analysis
    assert calls[0][4].ai_provider == "auto" and calls[0][4].ai_model == "new-model"
    assert client.post(f"/api/runs/{rid}/analysis", headers=a, json={"ai_provider": "offline"}).status_code == 409
    assert api.db().get_raw_posts(rid) == raw


@pytest.mark.parametrize("message,code", [("401 API key invalid", "ai_auth"), ("API key not valid", "ai_auth"),
    ("429 quota exceeded", "ai_quota"), ("503 unavailable", "ai_unavailable"), ("unexpected JSON", "analysis_failed")])
def test_analysis_error_codes(message, code):
    assert error_code(message, run_error=True, analysis_error=True) == f"error.{code}"


def test_startup_checks_are_sequential_cached_and_wait_for_scrape_lock(cloud, tmp_path, monkeypatch):
    client = cloud(mode="local")
    monkeypatch.setattr(api, "_session_cache", {})
    monkeypatch.setattr(api, "_session_checks", {})
    monkeypatch.setattr(api, "_session_started", False)
    monkeypatch.setattr(api.browser, "profile_dir", lambda p: tmp_path / p)
    for p in ("facebook", "linkedin"):
        (tmp_path / p).mkdir()
    calls = []
    def check(p):
        assert pipeline._platform_locks[p].locked()
        calls.append(p)
        return p == "facebook"
    monkeypatch.setattr(api.browser, "check_session", check)
    lock = pipeline._platform_locks["facebook"]
    lock.acquire()
    try:
        states = client.get("/api/platforms").json()
        assert not calls
        assert all(p["checking"] for p in states if p["has_profile"])
        assert all(p["logged_in"] is None for p in states)
    finally:
        lock.release()
    for _ in range(100):
        if not api._session_checks:
            break
        time.sleep(.01)
    states = {p["key"]: p for p in client.get("/api/platforms").json()}
    assert calls == ["facebook", "linkedin"]
    assert states["facebook"]["logged_in"] is True
    assert states["linkedin"]["logged_in"] is False
    client.get("/api/platforms")
    assert len(calls) == 2
    client.post("/api/platforms/facebook/check")
    assert calls == ["facebook", "linkedin", "facebook"]


def test_cloud_skips_startup_checks(cloud, monkeypatch):
    client = cloud()
    headers = _signup(client)
    monkeypatch.setattr(api, "_session_started", False)
    monkeypatch.setattr(api.browser, "check_session", lambda *a: pytest.fail("Cloud opened a profile"))
    assert client.get("/api/platforms", headers=headers).json() == []
    assert api._session_started is False


def test_session_check_headless_timeout_and_network_failure_is_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "profile_dir", lambda *a: tmp_path)
    class Page:
        url = "https://www.facebook.com/"
        def goto(self, url, **kwargs):
            assert kwargs["timeout"] == 15_000
            raise TimeoutError("offline")
    class Context:
        pages = [Page()]
        def cookies(self):
            return [{"name": "c_user", "domain": ".facebook.com"}]
    @contextmanager
    def context(platform, headless):
        assert headless is True
        yield Context()
    monkeypatch.setattr(browser, "open_context", context)
    assert browser.check_session("facebook") is None
