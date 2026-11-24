"""Synthetic reproductions from the run-16 quota investigation; no paid API calls."""
import re
import threading
from types import SimpleNamespace as Obj

import pytest

from feedlens.ai.base import AIOutputTruncated
from feedlens.ai.limits import Limits
from feedlens.ai.scheduler import Candidate, QuotaExhausted, QuotaScheduler
from feedlens.analysis.llm import LLMAnalyzer
from feedlens.analysis.prompts import classification_batch_size
from feedlens.core.messages import progress_message
from feedlens.core.models import RawPost
from tests.test_ai_quota import Clock, Provider


def test_subbatch_is_checkpointed_before_later_child_starts(monkeypatch):
    saved, calls = [], []
    analyzer = LLMAnalyzer(Provider("test", Clock()))
    monkeypatch.setattr(analyzer.scheduler, "parallelism", lambda *a: 1)
    def reply(prompt, *args, **kwargs):
        ids = re.findall(r'<post id="(\d+)"', prompt)
        calls.append(len(ids))
        if len(ids) == 4:
            raise AIOutputTruncated("output limit")
        if "Post 2" in prompt:
            assert [p.text for p in saved] == ["Post 0", "Post 1"]
            raise RuntimeError("429 exhausted in child")
        return {"items": [{"id": int(i), "category": "news", "summary": "Read", "is_job": False} for i in ids]}
    monkeypatch.setattr(analyzer, "_json_call", reply)
    analyzer.on_batch = saved.extend
    with pytest.raises(RuntimeError, match="429"):
        analyzer.classify([RawPost(platform="facebook", source="feed", text=f"Post {i}") for i in range(4)], False, [], "", lambda *a: None)
    assert calls == [4, 2, 2]
    assert len(saved) == 2


def test_continuous_truncation_has_small_request_budget_and_keeps_unread(monkeypatch):
    calls = []
    analyzer = LLMAnalyzer(Provider("test", Clock()))
    monkeypatch.setattr(analyzer.scheduler, "parallelism", lambda *a: 1)
    def broken(*a, **kw):
        calls.append(True)
        raise AIOutputTruncated("always invalid")
    monkeypatch.setattr(analyzer, "_json_call", broken)
    with pytest.raises(Exception, match="output|truncat|invalid"):
        analyzer.classify([RawPost(platform="facebook", source="feed", text=f"Post {i}") for i in range(40)], True, [], "", lambda *a: None)
    assert len(calls) <= 6


def test_ready_key_of_same_model_precedes_other_model_and_priority():
    clock = Clock()
    lite1, flash1, lite2 = [Provider(m, clock) for m in ("gemini-3.5-flash-lite", "gemini-flash", "gemini-3.5-flash-lite")]
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    candidates = [Candidate(1, lite1), Candidate(1, flash1), Candidate(2, lite2, priority=1)]
    scheduler.blocked_until[candidates[0].pair] = 30
    scheduler.complete_json(candidates, "", "", {})
    assert lite2.calls == [0] and not flash1.calls and not lite1.calls


@pytest.mark.parametrize("kind,daily", [("PerMinute", False), ("PerDay", True)])
def test_gemini_real_quota_id_beats_generic_daily_help_text(kind, daily):
    clock = Clock(); provider = Provider("gemini-3.5-flash-lite", clock)
    attempts = []
    def reply(*a):
        attempts.append(clock.value)
        if len(attempts) == 1:
            raise RuntimeError('429 RESOURCE_EXHAUSTED. {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", '
                '"violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests", '
                f'"quotaId": "GenerateRequests{kind}PerProjectPerModel-FreeTier", "quotaValue": "15"}}]}}]}}}} '
                'See help for requests per day. Please retry in 2s.')
        return {}
    provider.complete_json = reply
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    if daily:
        with pytest.raises(QuotaExhausted):
            scheduler.complete_json([Candidate(1, provider)], "", "", {})
        assert len(attempts) == 1
    else:
        assert scheduler.complete_json([Candidate(1, provider)], "", "", {}) == {}
        assert len(attempts) == 2 and clock.value == 2


@pytest.mark.parametrize("error", [RuntimeError("404 model not found"), ConnectionResetError("connection reset"), OSError("getaddrinfo failed")])
def test_retired_model_and_low_level_network_use_candidate_backup(error):
    clock = Clock(); primary, backup = Provider("primary", clock), Provider("backup", clock)
    primary.complete_json = lambda *a: (_ for _ in ()).throw(error)
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    assert scheduler.complete_json([Candidate(1, primary), Candidate(2, backup)], "", "", {}) == {"ok": True}
    assert backup.calls


def test_failure_phase_and_smaller_job_batches():
    assert progress_message({"phase": "analysis_failed", "message": "failed"})["message_code"] == "progress.analysis_failed"
    assert classification_batch_size(True, [], "", has_cv=True) <= 20


def test_all_keys_minute_limited_wait_for_same_model_instead_of_scarce_fallback():
    clock = Clock()
    clients = [Provider(model, clock) for model in ("gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-flash")]
    candidates = [Candidate(1, clients[0]), Candidate(2, clients[1], priority=1), Candidate(1, clients[2])]
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    scheduler.blocked_until[candidates[0].pair] = 30
    scheduler.blocked_until[candidates[1].pair] = 10
    scheduler.complete_json(candidates, "", "", {})
    assert clients[1].calls == [10] and not clients[2].calls


def test_quota_day_switches_key_before_model_and_explains_same_model():
    clock = Clock()
    clients = [Provider(model, clock) for model in ("gemini-3.5-flash-lite", "gemini-flash", "gemini-3.5-flash-lite")]
    clients[0].complete_json = lambda *a: (_ for _ in ()).throw(RuntimeError("429 quotaId: GenerateRequestsPerDayPerProjectPerModel"))
    candidates = [Candidate(1, clients[0], key_label="Main"), Candidate(1, clients[1]), Candidate(2, clients[2], priority=1, key_label="Backup")]
    notes, states = [], []
    QuotaScheduler(clock=clock.clock, sleep=clock.sleep).complete_json(candidates, "", "", {}, notify=notes.append, on_state=states.append)
    assert clients[2].calls == [0] and not clients[1].calls
    assert any("Backup" in note and "c\u00f9ng model" in note for note in notes)
    assert states[-1]["switched_key"] is True


def test_known_project_shares_minute_and_daily_quota_between_keys():
    clock = Clock()
    clients = [Provider("gemini-3.5-flash-lite", clock) for _ in range(2)]
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep,
                               default_limits=lambda *a: Limits(rpm=2, rpd=10))
    candidates = [Candidate(i + 1, p) for i, p in enumerate(clients)]
    # First errors identify the project, without asking users to expose their key values.
    for candidate in candidates:
        original = candidate.client.complete_json
        failed = [False]
        def request(*a, original=original, failed=failed):
            if not failed[0]:
                failed[0] = True
                raise RuntimeError("429 consumer: projects/123456 quotaId: GenerateRequestsPerMinutePerProjectPerModel limit: 2 retry in 1s")
            return original(*a)
        candidate.client.complete_json = request
        scheduler.complete_json([candidate], "", "", {})
    assert scheduler.quota_pair(candidates[0]) == scheduler.quota_pair(candidates[1])
    assert clock.value >= 60  # A second key must not bypass the two-request project window.
    clients[0].complete_json = lambda *a: (_ for _ in ()).throw(RuntimeError("429 consumer projects/123456 quotaId GenerateRequestsPerDayPerProjectPerModel"))
    before = len(clients[1].calls)
    with pytest.raises(QuotaExhausted):
        scheduler.complete_json(candidates, "", "", {})
    assert len(clients[1].calls) == before


def test_retry_and_split_requests_obey_same_pair_rpm(monkeypatch):
    clock = Clock(); provider = Provider("gemini-flash", clock)
    calls = []
    def reply(system, prompt, schema, effort):
        calls.append(clock.value)
        ids = re.findall(r'<post id="(\d+)"', prompt)
        if len(ids) > 2:
            raise AIOutputTruncated("output limit")
        if len(calls) == 3:
            raise RuntimeError("429 quotaId GenerateRequestsPerMinutePerProjectPerModel limit: 5 retry in 1s")
        return {"items": [{"id": int(i), "category": "news", "summary": "Read", "is_job": False} for i in ids]}
    provider.complete_json = reply
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, default_limits=lambda *a: Limits(rpm=5))
    monkeypatch.setattr(scheduler, "parallelism", lambda *a: 1)
    analyzer = LLMAnalyzer(provider, scheduler=scheduler)
    result = analyzer.classify([RawPost(platform="facebook", source="feed", text=f"Post {i}") for i in range(8)], True, [], "", lambda *a: None)
    assert len(result) == 8 and len(calls) == 8
    assert all(sum(t <= value < t + 60 for value in calls) <= 5 for t in calls)


def test_gemini_sends_exact_requested_id_and_reports_server_model_version():
    from feedlens.ai.providers.gemini import GeminiProvider
    provider = object.__new__(GeminiProvider)
    provider.model = "gemini-3.7-flash"
    provider.genai = Obj(types=Obj(GenerateContentConfig=Obj, ThinkingConfig=Obj))
    sent = []
    def generate(**kwargs):
        sent.append(kwargs["model"])
        return Obj(text='{"items": []}', candidates=[Obj(finish_reason="STOP")], model_version="gemini-3.8-flash")
    provider.client = Obj(models=Obj(generate_content=generate))
    analyzer = LLMAnalyzer(provider)
    states = []
    analyzer.on_state = states.append
    analyzer.complete_json("s", "p", {})
    assert sent == ["gemini-3.7-flash"]
    assert states[-1]["requested_model"] == "gemini-3.7-flash"
    assert states[-1]["model"] == "gemini-3.8-flash"


def test_concurrent_requests_never_reserve_six_in_one_minute():
    from concurrent.futures import ThreadPoolExecutor
    clock = Clock(); provider = Provider("gemini-flash", clock)
    waiting, release = threading.Event(), threading.Event()
    def sleep(seconds):
        waiting.set()
        assert release.wait(3)
    scheduler = QuotaScheduler(clock=clock.clock, sleep=sleep, default_limits=lambda *a: Limits(rpm=5))
    candidates = [Candidate(1, provider)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(scheduler.complete_json, candidates, "", "", {}) for _ in range(6)]
        assert waiting.wait(3)
        assert len(scheduler.windows[candidates[0].pair]) == 5
        clock.value = 60
        release.set()
        assert all(future.result(timeout=3) == {"ok": True} for future in futures)
    assert sum(value == 0 for value in provider.calls) <= 5


def test_model_alias_does_not_reset_minute_or_daily_budget():
    clock = Clock()
    alias, canonical = Provider("alias", clock), Provider("actual", clock)
    alias.served_model = "actual"
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, default_limits=lambda *a: Limits(rpm=1, rpd=2))
    scheduler.complete_json([Candidate(1, alias)], "", "", {})
    scheduler.complete_json([Candidate(1, canonical)], "", "", {})
    assert canonical.calls == [60]
    with pytest.raises(QuotaExhausted):
        scheduler.complete_json([Candidate(1, canonical)], "", "", {})


def test_empty_output_does_not_spend_two_requests_for_every_batch(monkeypatch):
    analyzer = LLMAnalyzer(Provider("test", Clock()))
    monkeypatch.setattr(analyzer.scheduler, "parallelism", lambda *a: 1)
    calls = []
    monkeypatch.setattr(analyzer, "_json_call", lambda *a, **kw: calls.append(True) or {"items": []})
    with pytest.raises(Exception, match="empty analysis"):
        analyzer.classify([RawPost(platform="facebook", source="feed", text=f"Post {i}") for i in range(220)], True, [], "", lambda *a: None)
    assert len(calls) <= 3


def test_220_jobs_with_cv_require_eleven_reads_and_one_digest(tmp_path, monkeypatch):
    from feedlens.runs import pipeline
    from feedlens.db.repository import Database
    from feedlens.jobs.profile import JobProfile
    from feedlens.core.models import RunRequest
    db = Database(f"sqlite:///{tmp_path / '220.db'}")
    uid = db.local_user_id()
    db.set_job_profile(uid, JobProfile(markdown="Python CV", primary_roles=["Developer"]).model_dump_json())
    req = RunRequest(platform="facebook", ai_provider="offline", job_mode=True)
    rid = db.create_run(req, uid)
    clock = Clock(); provider = Provider("gemini-3.5-flash-lite", clock)
    sizes = []
    def reply(system, prompt, schema, effort):
        ids = re.findall(r'<post id="(\d+)"', prompt)
        sizes.append(len(ids))
        if not ids:
            return {"overall": "Summary", "categories": [], "action_items": []}
        return {"items": [{"id": int(i), "category": "news", "summary": "Read", "is_job": False} for i in ids]}
    provider.complete_json = reply
    analyzer = LLMAnalyzer(provider, scheduler=QuotaScheduler(clock=clock.clock, sleep=clock.sleep))
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a: analyzer)
    pipeline.execute_analysis(db, rid, req,
        [RawPost(platform="facebook", source="feed", text=f"Independent post {i}") for i in range(220)], uid)
    assert db.get_run(rid)["status"] == "done"
    assert sizes.count(20) == 11 and sizes.count(0) == 1
    assert sum(p.analyzed for p in db.get_posts(rid)) == 220
    assert pipeline.PROGRESS[rid]["ai_requests"] == 12
    assert pipeline.PROGRESS[rid]["newly_read"] == 220


@pytest.mark.parametrize("ids", [["0", "1"], [91, 92]])
def test_response_ids_are_normalized_or_rejected_instead_of_silently_dropped(ids, monkeypatch):
    analyzer = LLMAnalyzer(Provider("test", Clock()))
    monkeypatch.setattr(analyzer, "_json_call", lambda *a, **kw: {"items": [
        {"id": item, "category": "news", "summary": "Read", "is_job": False} for item in ids]})
    raw = [RawPost(platform="facebook", source="feed", text=f"Post {i}") for i in range(2)]
    if ids[0] == "0":
        assert all(p.analyzed_by != "offline" for p in analyzer.classify(raw, False, [], "", lambda *a: None))
    else:
        with pytest.raises(Exception, match="output|invalid"):
            analyzer.classify(raw, False, [], "", lambda *a: None)


def test_gemini_low_thinking_and_safe_empty_output_diagnostics(caplog):
    from feedlens.ai.providers.gemini import GeminiProvider
    provider = object.__new__(GeminiProvider)
    provider.model = "gemini-3.8-flash"
    provider.genai = Obj(types=Obj(GenerateContentConfig=Obj, ThinkingConfig=Obj))
    configs = []
    def generate(**kwargs):
        configs.append(kwargs["config"])
        return Obj(text='{"items": []}', candidates=[Obj(finish_reason="STOP")], model_version=provider.model,
                   usage_metadata=Obj(prompt_token_count=120, candidates_token_count=7, thoughts_token_count=7000))
    provider.client = Obj(models=Obj(generate_content=generate))
    with caplog.at_level("INFO"):
        provider.complete_json("private instructions", "PRIVATE POST CONTENT", {})
    assert configs[0].thinking_config.thinking_level == "low"
    assert "thinking_tokens=7000" in caplog.text and "items=0" in caplog.text
    assert "PRIVATE POST CONTENT" not in caplog.text and "private instructions" not in caplog.text


def test_classification_schema_requires_at_least_one_item():
    from feedlens.analysis.prompts import CLASSIFY_SCHEMA
    from feedlens.analysis.prompts import KNOWN_JOBS_SCHEMA
    from feedlens.analysis.topics import _with_topic_fields
    for schema in (CLASSIFY_SCHEMA, KNOWN_JOBS_SCHEMA, _with_topic_fields(CLASSIFY_SCHEMA)):
        assert schema["properties"]["items"].get("minItems") == 1
