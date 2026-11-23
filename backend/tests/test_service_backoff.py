"""Provider outages are resumable service pauses, not daily quota exhaustion."""
import threading

import pytest

from feedlens import pipeline
from feedlens.ai.limits import Limits
from feedlens.ai.scheduler import Candidate, QuotaScheduler, pacific_day
from feedlens.analyzer import LLMAnalyzer
from feedlens.db import Database
from feedlens.messages import error_code
from feedlens.models import AnalyzedPost, RawPost, RunRequest
from tests.test_ai_quota import Clock, Provider


def test_service_backoff_has_distinct_state_long_budget_and_refunds_daily_usage():
    clock = Clock(); provider = Provider("gemini-3.5-flash-lite", clock)
    def unavailable(*a):
        provider.calls.append(clock.value)
        raise RuntimeError("503 UNAVAILABLE")
    provider.complete_json = unavailable
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, jitter=lambda seconds: seconds)
    candidate = Candidate(1, provider)
    states = []
    with pytest.raises(Exception, match="service temporarily unavailable"):
        scheduler.complete_json([candidate], "", "", {}, on_state=states.append)
    waits = [state for state in states if state["state"] == "service_wait"]
    assert [state["wait_seconds"] for state in waits] == [5, 10, 20, 40, 80, 80, 65]
    assert all(state["status"] == 503 and state["retry_at"] for state in waits)
    assert states[-1]["state"] == "service_paused"
    assert 150 <= clock.value <= 300 and len(provider.calls) == 7
    assert scheduler.daily_requests(candidate, pacific_day()) == 0


@pytest.mark.parametrize("code", [500, 502, 503, 504])
@pytest.mark.parametrize("model", ["gemini-3.5-flash-lite", "gemini-3.8-flash"])
def test_service_wait_can_use_another_model_while_quota_wait_keeps_same_model(code, model):
    clock = Clock(); primary = Provider("gemini-3.5-flash-lite", clock); backup = Provider(model, clock)
    primary.complete_json = lambda *a: (_ for _ in ()).throw(RuntimeError(f"{code} UNAVAILABLE"))
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, jitter=lambda seconds: seconds)
    assert scheduler.complete_json([Candidate(1, primary), Candidate(2, backup)], "", "", {}) == {"ok": True}
    assert backup.calls == [0] and clock.value == 0


def test_stop_interrupts_service_wait_immediately():
    clock = Clock(); stop = threading.Event(); provider = Provider("model", clock)
    provider.complete_json = lambda *a: (_ for _ in ()).throw(RuntimeError("503 UNAVAILABLE"))
    scheduler = QuotaScheduler(clock=clock.clock, jitter=lambda seconds: seconds)
    states = []
    def state(value):
        states.append(value)
        if value["state"] == "service_wait":
            stop.set()
    with pytest.raises(Exception, match="stopped"):
        scheduler.complete_json([Candidate(1, provider)], "", "", {}, stop_event=stop, on_state=state)
    assert states[-1]["state"] == "service_wait" and clock.value == 0


def test_service_retry_after_respects_five_minute_total_budget():
    clock = Clock(); provider = Provider("model", clock)
    calls = []
    def unavailable(*a):
        calls.append(True)
        error = RuntimeError("503 UNAVAILABLE")
        error.response = type("Response", (), {"headers": {"retry-after": "600"}})()
        raise error
    provider.complete_json = unavailable
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, jitter=lambda seconds: seconds)
    with pytest.raises(Exception, match="service temporarily unavailable"):
        scheduler.complete_json([Candidate(1, provider)], "", "", {})
    assert clock.value == 300 and len(calls) == 1


def test_daily_exhausted_candidates_do_not_hide_service_pause():
    clock = Clock(); provider = Provider("model", clock)
    provider.complete_json = lambda *a: (_ for _ in ()).throw(RuntimeError("503 UNAVAILABLE"))
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, jitter=lambda seconds: seconds)
    scheduler.daily_blocked.add(((1, "model"), pacific_day()))
    states = []
    with pytest.raises(Exception, match="service temporarily unavailable"):
        scheduler.complete_json([Candidate(1, provider), Candidate(2, provider)], "", "", {}, on_state=states.append)
    assert states[-1]["state"] == "service_paused" and states[-1]["daily"] is False
    assert {item["reason"] for item in states[-1]["candidates"]} == {"provider_daily", "service_unavailable"}


def test_service_pause_keeps_read_posts_and_continue_is_immediate(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'service.db'}")
    uid = db.local_user_id(); key = db.add_key(uid, "gemini", "fake", "hint")
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = db.create_run(req, uid)
    raw = [RawPost(platform="facebook", source="feed", text=f"Distinct post {i}") for i in range(2)]
    db.save_raw_posts(rid, raw)
    db.save_batch(rid, [AnalyzedPost(**raw[0].model_dump(), analyzed_by="Gemini (model)", summary="Already read")])
    clock = Clock(); provider = Provider("model", clock); unavailable = [True]
    def reply(system, prompt, schema, effort):
        if unavailable[0]:
            raise RuntimeError("503 UNAVAILABLE")
        if "<post " in prompt:
            assert "Distinct post 0" not in prompt
            return {"items": [{"id": 0, "category": "news", "summary": "Read", "is_job": False}]}
        return {"overall": "Done", "categories": [], "action_items": []}
    provider.complete_json = reply
    scheduler = QuotaScheduler(db, clock=clock.clock, sleep=clock.sleep, jitter=lambda seconds: seconds,
                               default_limits=lambda *a: Limits(rpm=15, rpd=500))
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a: LLMAnalyzer(provider, scheduler=scheduler, candidates=[Candidate(key.id, provider)]))
    pipeline.execute_analysis(db, rid, req, raw, uid)
    run = db.get_run(rid)
    assert run["status"] == "analysis_failed" and error_code(run["error"], analysis_error=True) == "error.ai_service_paused"
    assert pipeline.PROGRESS[rid]["ai"]["state"] == "service_paused" and db.can_continue_analysis(rid)
    assert sum(p.analyzed for p in db.get_posts(rid, include_raw=True)) == 1
    assert db.ai_usage(key.id, pacific_day())[provider.model]["requests"] == 0
    before = clock.value; unavailable[0] = False
    pipeline.execute_analysis(db, rid, req, raw, uid)
    assert db.get_run(rid)["status"] == "done" and clock.value == before
