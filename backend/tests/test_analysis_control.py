"""Run controls never spend quota for queued work after a stop request."""
import re
import threading
import time
from types import SimpleNamespace

import pytest

from feedlens import api, pipeline
from feedlens.ai.limits import Limits
from feedlens.ai.scheduler import Candidate, QuotaScheduler
from feedlens.analysis.llm import LLMAnalyzer
from feedlens.db import Database
from feedlens.models import RawPost, RunRequest
from tests.test_cloud import cloud, _signup


def test_scheduler_reports_actual_pair_and_interrupts_quota_wait():
    stop = threading.Event()
    states = []
    calls = []
    client = SimpleNamespace(info=SimpleNamespace(key="gemini", name="Gemini"), model="actual-model",
                             complete_json=lambda *a: calls.append(True) or {})
    scheduler = QuotaScheduler(default_limits=lambda *a: Limits(rpm=1))
    candidate = Candidate(1, client, key_label="Work key")
    scheduler.acquire([candidate], 1)

    def state(value):
        states.append(value)
        if value["state"] == "quota_wait":
            stop.set()

    with pytest.raises(Exception, match="stopped"):
        scheduler.complete_json([candidate], "", "", {}, stop_event=stop, on_state=state)
    assert not calls
    assert states[-1]["provider"] == "Gemini"
    assert states[-1]["model"] == "actual-model"
    assert states[-1]["key_label"] == "Work key"
    assert states[-1]["retry_at"] > time.time()


def test_stop_keeps_inflight_batch_and_resume_switches_only_unread(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'control.db'}")
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = db.create_run(req)
    raw = [RawPost(platform="facebook", source="feed", text=f"Different post {i}") for i in range(3)]
    entered, release = threading.Event(), threading.Event()
    calls = []
    def provider(model):
        def reply(system, prompt, schema, effort):
            calls.append((model, prompt))
            if "<post " not in prompt:
                return {"overall": "Summary", "categories": [], "action_items": []}
            if model == "old":
                entered.set()
                assert release.wait(5)
            return {"items": [{"id": int(i), "category": "news", "summary": "Read", "is_job": False}
                              for i in re.findall(r'<post id="(\d+)"', prompt)]}
        client = SimpleNamespace(info=SimpleNamespace(key="gemini", name="Gemini"), model=model, complete_json=reply)
        return LLMAnalyzer(client, scheduler=QuotaScheduler(default_limits=lambda *a: Limits(rpm=1) if model == "old" else Limits()))
    monkeypatch.setattr('feedlens.analysis.prompts.BATCH_SIZE', 1)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a: provider(a[1] or "old"))
    pipeline.start_analysis(db, rid, req, raw, None)
    assert entered.wait(5)
    assert pipeline.request_stop(rid)
    release.set()
    deadline = time.monotonic() + 5
    while db.get_run(rid)["status"] == "analyzing" and time.monotonic() < deadline:
        time.sleep(.01)
    assert db.get_run(rid)["status"] == "analysis_failed"
    assert sum(p.analyzed for p in db.get_posts(rid, include_raw=True)) == 1
    assert db.can_continue_analysis(rid)
    req.ai_model = "new"
    pipeline.execute_analysis(db, rid, req, raw, None)
    assert db.get_run(rid)["status"] == "done"
    assert sum(model == "old" for model, _ in calls) == 1
    assert all("Different post 0" not in prompt for model, prompt in calls if model == "new")


def test_stop_endpoint_authorization_conflict_and_change_model(cloud, monkeypatch):
    client = cloud()
    headers = _signup(client)
    other = _signup(client, "other@example.test")
    uid = api.db().get_user_by_email("a@x.io").id
    rid = api.db().create_run(RunRequest(platform="facebook", ai_provider="offline"), uid)
    url = f"/api/runs/{rid}/analysis/stop"
    assert client.post(url, headers=other).status_code == 404
    result = client.post(url, headers=headers)
    assert result.status_code == 409 and result.json()["code"] == "error.analysis_not_running"
    api.db().update_run(rid, status="analyzing")
    monkeypatch.setattr(api, "request_stop", lambda run_id, replacement=None: replacement.ai_model == "chosen")
    monkeypatch.setattr(api, "_check_ai", lambda *a: "gemini")
    result = client.post(url, headers=headers, json={"ai_provider": "gemini", "ai_model": "chosen"})
    assert result.status_code == 202 and result.json()["stopping"] is True


def test_change_model_interrupts_wait_and_automatically_resumes(cloud, monkeypatch):
    client = cloud()
    headers = _signup(client)
    uid = api.db().get_user_by_email("a@x.io").id
    db = api.db()
    req = RunRequest(platform="facebook", ai_provider="gemini", ai_model="waiting")
    rid = db.create_run(req, uid)
    waiting = threading.Event()
    calls = []
    def analyzer_for(*args):
        model = args[1]
        def reply(system, prompt, schema, effort):
            calls.append(model)
            if "<post " in prompt:
                return {"items": [{"id": 0, "category": "news", "summary": "Read", "is_job": False}]}
            return {"overall": "Summary", "categories": [], "action_items": []}
        provider = SimpleNamespace(info=SimpleNamespace(key="gemini", name="Gemini"), model=model, complete_json=reply)
        scheduler = QuotaScheduler(default_limits=lambda *a: Limits())
        candidate = Candidate(77, provider, key_label="Office")
        if model == "waiting":
            scheduler.blocked_until[candidate.pair] = scheduler.clock() + 3600
        analyzer = LLMAnalyzer(provider, scheduler=scheduler, candidates=[candidate])
        original = scheduler.acquire
        def acquire(*a, **kwargs):
            report = kwargs["on_state"]
            def state(value):
                report(value)
                waiting.set()
            return original(*a, **{**kwargs, "on_state": state})
        monkeypatch.setattr(scheduler, "acquire", acquire)
        return analyzer
    monkeypatch.setattr(pipeline, "get_analyzer", analyzer_for)
    monkeypatch.setattr(api, "_check_ai", lambda *a: "gemini")
    raw = [RawPost(platform="facebook", source="feed", text="Raw content available during AI wait")]
    pipeline.start_analysis(db, rid, req, raw, uid)
    assert waiting.wait(5)
    detail = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert detail["progress"]["ai"]["state"] == "quota_wait"
    assert detail["progress"]["ai"]["key_label"] == "Office"
    assert detail["posts"][0]["analyzed"] is False
    for fmt in ("json", "md"):
        assert "Raw content available" in client.get(f"/api/runs/{rid}/export?fmt={fmt}", headers=headers).text
    result = client.post(f"/api/runs/{rid}/analysis/stop", headers=headers,
                         json={"ai_provider": "gemini", "ai_model": "replacement"})
    assert result.status_code == 202
    deadline = time.monotonic() + 5
    while db.get_run(rid)["status"] != "done" and time.monotonic() < deadline:
        time.sleep(.01)
    assert db.get_run(rid)["status"] == "done"
    assert db.get_run(rid)["request"]["ai_model"] == "replacement"
    assert calls == ["replacement", "replacement"]
    assert db.get_posts(rid)[0].analyzed_by == "Gemini (replacement)"


def test_daily_exhaustion_is_terminal_and_explicit():
    provider = SimpleNamespace(info=SimpleNamespace(key="gemini", name="Gemini"), model="daily")
    scheduler = QuotaScheduler(default_limits=lambda *a: Limits(rpd=0))
    states = []
    with pytest.raises(Exception, match="quota exhausted"):
        scheduler.complete_json([Candidate(1, provider)], "", "", {}, on_state=states.append)
    assert len(states) == 1 and states[0]["state"] == "exhausted"
    assert states[0]["daily"] is False and states[0]["candidates"][0]["reason"] == "zero_quota"


def test_scheduler_reports_fallback_identity_without_credentials():
    import json
    def exhausted(*args):
        raise RuntimeError("429 per day quota exhausted")
    first = SimpleNamespace(info=SimpleNamespace(key="gemini", name="Gemini"), model="first",
                            api_key="never-expose-this", complete_json=exhausted)
    second = SimpleNamespace(info=first.info, model="actual", api_key="also-secret", complete_json=lambda *a: {})
    candidates = [Candidate(1, first, key_label="Primary"), Candidate(2, second, priority=1, key_label="Backup")]
    states = []
    QuotaScheduler(default_limits=lambda *a: Limits()).complete_json(candidates, "", "", {}, on_state=states.append)
    assert any(state["state"] == "switching" and state["next_model"] == "actual" for state in states)
    assert states[-1]["model"] == "actual" and states[-1]["key_label"] == "Backup"
    assert "secret" not in json.dumps(states) and "never-expose-this" not in json.dumps(states)
