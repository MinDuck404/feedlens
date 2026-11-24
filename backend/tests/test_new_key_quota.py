"""New credentials must not inherit another credential's runtime quota identity."""

import feedlens.routes.dependencies as dependencies

import feedlens.ai.registry as ai_registry

from types import SimpleNamespace

import pytest

from feedlens.ai.limits import Limits
from feedlens.ai.scheduler import Candidate, QuotaExhausted, QuotaScheduler, pacific_day, scheduler_for
from feedlens.db.repository import Database
from tests.test_ai_quota import Clock, Provider
from tests.test_cloud import cloud


def test_deleted_key_id_reuse_does_not_inherit_project_exhaustion(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'reuse.db'}")
    uid = db.local_user_id()
    old = db.add_key(uid, "gemini", "fake-ciphertext", "hint", "Old project")
    scheduler = scheduler_for(db)
    provider = Provider("gemini-3.5-flash-lite", Clock())
    candidate = Candidate(old.id, provider)
    scheduler.key_projects[("gemini", old.id)] = "old-project"
    scope = scheduler.quota_pair(candidate)
    scheduler.daily_blocked.add((scope, pacific_day()))
    scheduler.failures[candidate.pair] = 3
    assert db.delete_key_id(uid, old.id)
    new = db.add_key(uid, "gemini", "other-fake-ciphertext", "hint", "New project")
    assert new.id == old.id  # SQLite can reuse the highest deleted INTEGER PRIMARY KEY.
    assert scheduler.quota_pair(Candidate(new.id, provider)) == (new.id, provider.model)
    assert candidate.pair not in scheduler.failures
    assert scheduler.complete_json([Candidate(new.id, provider)], "", "", {}) == {"ok": True}
    assert (scope, pacific_day()) in scheduler.daily_blocked  # Other keys in the old project stay limited.


def test_fresh_unknown_key_is_independent_of_known_or_unknown_exhausted_keys():
    clock = Clock(); scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    old, fresh = Candidate(1, Provider("gemini-3.5-flash-lite", clock)), Candidate(2, Provider("gemini-3.5-flash-lite", clock))
    scheduler.daily_blocked.add((old.pair, pacific_day()))
    scheduler.model_aliases[("gemini", old.model)] = "actual-model"
    scheduler.key_projects[("gemini", old.key_id)] = "old-project"
    scheduler.daily_blocked.add((scheduler.quota_pair(old), pacific_day()))
    assert scheduler.complete_json([old, fresh], "", "", {}) == {"ok": True}
    assert fresh.client.calls == [0] and not old.client.calls


@pytest.mark.parametrize("limits,tokens,reason", [(Limits(tpm=100), 101, "too_large"),
    (Limits(rpm=0), 1, "zero_quota"), (Limits(rpd=0), 1, "zero_quota")])
def test_rejected_candidates_report_the_actual_local_reason(limits, tokens, reason):
    scheduler = QuotaScheduler(default_limits=lambda *a: limits)
    candidate = Candidate(5, Provider("model", Clock()), key_label="New project")
    states = []
    with pytest.raises(QuotaExhausted) as failure:
        scheduler.acquire([candidate], tokens, on_state=states.append)
    assert failure.value.candidates[0]["reason"] == reason
    assert states[-1]["candidates"][0]["key_label"] == "New project"
    assert "New project" in str(failure.value) and "model" in str(failure.value)


def test_new_key_added_after_scheduler_creation_is_used_on_continue(cloud, monkeypatch):
    from feedlens import api
    from feedlens.runs import pipeline
    from feedlens.analysis import analyzer as module
    from feedlens.routes import ai_keys as ai_keys_api
    from feedlens.core.crypto import encrypt
    from feedlens.core.models import RawPost
    from feedlens.core.models import RunRequest
    from tests.test_cloud import _signup
    client = cloud()
    headers = _signup(client)
    db = dependencies.db(); uid = db.get_user_by_email("a@x.io").id
    old = db.add_key(uid, "gemini", encrypt("fake-old-secret"), "hint", "Old")
    scheduler = scheduler_for(db)
    model = "gemini-3.5-flash-lite"
    scheduler.daily_blocked.add(((old.id, model), pacific_day()))
    monkeypatch.setattr(ai_keys_api, "list_models", lambda *a: [model])
    monkeypatch.setattr(ai_registry, "resolve_models", lambda *a: [model])
    calls = []
    def provider(key, chosen, secret):
        def reply(system, prompt, schema, effort):
            calls.append(secret == "fake-new-secret")
            return ({"items": [{"id": 0, "category": "news", "summary": "Read", "is_job": False}]}
                    if "<post " in prompt else {"overall": "Done", "categories": [], "action_items": []})
        return SimpleNamespace(info=SimpleNamespace(key="gemini", name="Gemini"), model=chosen, complete_json=reply)
    monkeypatch.setattr(ai_registry, "get_provider", provider)
    response = client.post("/api/ai/keys", headers=headers,
        json={"provider": "gemini", "api_key": "fake-new-secret", "label": "New project"})
    assert response.status_code == 200
    rid = db.create_run(RunRequest(platform="facebook", ai_provider="gemini"), uid)
    db.save_raw_posts(rid, [RawPost(platform="facebook", source="feed", text="One remaining post")])
    db.update_run(rid, status="analysis_failed")
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    assert client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider":"gemini"}).status_code == 200
    assert db.get_run(rid)["status"] == "done" and calls == [True, True]


@pytest.mark.parametrize("status", [None, 400])
def test_client_and_bad_request_configuration_do_not_consume_daily_quota(tmp_path, status):
    db = Database(f"sqlite:///{tmp_path / 'configuration.db'}")
    key = db.add_key(db.local_user_id(), "gemini", "fake", "hint")
    clock = Clock(); provider = Provider("gemini-3.5-flash-lite", clock)
    error = TypeError("unsupported thinking_level SECRET-DO-NOT-LOG") if status is None else RuntimeError("400 INVALID_ARGUMENT, project 429123: SECRET-DO-NOT-LOG")
    if status:
        error.status_code = status
    calls = []
    def failed(*a):
        calls.append(True)
        raise error
    provider.complete_json = failed
    scheduler = QuotaScheduler(db, clock=clock.clock, sleep=clock.sleep)
    states = []
    with pytest.raises(Exception, match="configuration") as failure:
        scheduler.complete_json([Candidate(key.id, provider)], "s", "p", {}, on_state=states.append)
    assert "SECRET-DO-NOT-LOG" not in str(failure.value)
    assert not isinstance(failure.value, QuotaExhausted) and len(calls) == 1
    assert db.ai_usage(key.id, pacific_day())[provider.model]["requests"] == 0
    assert states[-1]["candidates"][0]["reason"] == "configuration"


