
import feedlens.routes.dependencies as dependencies

import feedlens.ai.registry as ai_registry

import feedlens.analysis.prompts as analysis_prompts
from types import SimpleNamespace

from feedlens.ai.limits import Limits
from feedlens.ai.scheduler import Candidate, QuotaScheduler
from feedlens.db import Database
from feedlens.db.tables import UserRow
from sqlalchemy import create_engine, text
import pytest
from datetime import datetime, timezone
from feedlens.routes import ai_keys as ai_keys_api
from feedlens.ai.scheduler import QuotaExhausted, pacific_day
from tests.test_cloud import cloud, _signup


class Clock:
    def __init__(self):
        self.value = 0.0
    def clock(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


class Provider:
    info = SimpleNamespace(key="gemini", name="Gemini")
    def __init__(self, model, clock):
        self.model, self.clock, self.calls = model, clock, []
    def complete_json(self, *args, **kwargs):
        self.calls.append(self.clock.value)
        return {"ok": True}


@pytest.mark.parametrize("job_mode,tpm,count,expected_batches", [
    (False, 250_000, 1200, 30),
    (True, 250_000, 1200, 60),
    (True, 30_000, 100, None),
])
def test_classification_batch_size_respects_output_budget_and_model_tpm(job_mode, tpm, count, expected_batches, monkeypatch):
    import re
    from feedlens.analysis.llm import LLMAnalyzer
    from feedlens.models import RawPost

    clock = Clock()
    provider = Provider("gemini-3.5-flash-lite", clock)
    scheduler = QuotaScheduler(default_limits=lambda *a: Limits(tpm=tpm))
    analyzer = LLMAnalyzer(provider, scheduler=scheduler)
    sizes = []

    def reply(prompt, schema, effort):
        ids = re.findall(r'<post id="(\d+)"', prompt)
        sizes.append(len(ids))
        return {"items": [{"id": int(i), "category": "news", "summary": "Read", "is_job": False} for i in ids]}

    monkeypatch.setattr(analyzer, "_json_call", reply)
    raw = [RawPost(platform="facebook", source="feed", text=f"Post {i} " + "a" * 600) for i in range(count)]
    assert len(analyzer.classify(raw, job_mode, [], "", lambda *a: None)) == count
    assert sum(sizes) == count and max(sizes) <= 60
    if expected_batches:
        assert len(sizes) == expected_batches and max(sizes) <= (20 if job_mode else 40)
    else:
        assert max(sizes) < 20


def test_omitted_items_from_a_large_batch_share_one_retry(monkeypatch):
    import re
    from feedlens.analysis.llm import LLMAnalyzer
    from feedlens.models import RawPost

    analyzer = LLMAnalyzer(Provider("gemini-3.5-flash-lite", Clock()))
    calls = []

    def reply(prompt, schema, effort):
        items = re.findall(r'<post id="(\d+)"[^>]+>\n(Post \d+)', prompt)
        calls.append([body for _, body in items])
        return {"items": [{"id": int(i), "category": "news", "summary": "Read", "is_job": False}
                          for i, _ in (items[:10] if len(calls) == 1 else items)]}

    monkeypatch.setattr(analyzer, "_json_call", reply)
    raw = [RawPost(platform="facebook", source="feed", text=f"Post {i}") for i in range(20)]
    result = analyzer.classify(raw, True, [], "", lambda *a: None)
    assert calls == [[p.text for p in raw], [p.text for p in raw[10:]]]
    assert [p.text for p in result] == [p.text for p in raw]
    assert all(p.analyzed_by == analyzer.label for p in result)


def test_twenty_five_batches_never_exceed_five_requests_per_minute():
    clock = Clock()
    provider = Provider("gemini-3.8-flash", clock)
    # Isolate RPM: the real free-tier RPD=20 is tested separately.
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep,
                               default_limits=lambda *args: Limits(rpm=5, tpm=250_000, rpd=100))
    candidates = [Candidate(1, provider)]
    for _ in range(25):
        assert scheduler.complete_json(candidates, "system", "prompt", {}) == {"ok": True}
    assert len(provider.calls) == 25
    assert all(sum(start <= t < start + 60 for t in provider.calls) <= 5 for start in provider.calls)
    assert scheduler.parallelism(candidates) == 1


def test_old_key_migrates_without_changing_ciphertext_or_id(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    engine = create_engine(url)
    UserRow.__table__.create(engine)
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id,email,password_hash,created_at) VALUES (1,'a@example.test','!','2026-11-17')"))
        c.execute(text("CREATE TABLE api_keys (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), provider VARCHAR(20), ciphertext TEXT, hint VARCHAR(16), created_at DATETIME, UNIQUE(user_id,provider))"))
        c.execute(text("INSERT INTO api_keys VALUES (7,1,'gemini','ENCRYPTED-UNCHANGED','…1234','2026-11-17')"))
    db = Database(url)
    row = db.list_keys(1)[0]
    assert (row.id, row.ciphertext, row.priority, row.enabled, row.tier, row.label) == (7, 'ENCRYPTED-UNCHANGED', 0, True, 'free', '')
    assert row.created_at.isoformat() == "2026-11-17T00:00:00"
    db.engine.dispose()
    db = Database(url)
    assert db.list_keys(1)[0].id == 7 and db.list_keys(1)[0].created_at == row.created_at
    with db.engine.connect() as c:
        assert c.exec_driver_sql("PRAGMA foreign_key_list(api_keys)").fetchone()[2] == "users"
        assert c.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    db.add_key(1, 'gemini', 'ANOTHER-CIPHERTEXT', '…5678')
    assert len(db.list_keys(1)) == 2


def test_default_lite_first_and_daily_exhaustion_moves_to_flash():
    clock = Clock()
    lite = Provider("gemini-3.5-flash-lite", clock)
    flash = Provider("gemini-3.8-flash", clock)
    attempts = []
    def exhausted(*args):
        attempts.append("lite")
        raise RuntimeError("429 quotaId GenerateRequestsPerDayPerProjectPerModel limit: 0")
    lite.complete_json = exhausted
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    scheduler.complete_json([Candidate(1, flash), Candidate(1, lite)], "s", "p", {})
    assert attempts == ["lite"] and flash.calls == [0]
    assert clock.value == 0  # Daily exhaustion must never wait for a minute.


def test_auth_failure_uses_next_key_and_records_invalid_status():
    clock = Clock(); first = Provider("gemini-3.5-flash-lite", clock); second = Provider(first.model, clock)
    first.complete_json = lambda *a: (_ for _ in ()).throw(RuntimeError("401 UNAUTHENTICATED"))
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    assert scheduler.complete_json([Candidate(1, first), Candidate(2, second, priority=1)], "s", "p", {}) == {"ok": True}
    assert scheduler.status[1] == "invalid" and second.calls == [0]


def test_new_key_routes_are_private_ordered_and_never_leak_secrets(cloud, monkeypatch):
    client = cloud(); a = _signup(client); b = _signup(client, "b@example.test")
    monkeypatch.setattr(ai_keys_api, "list_models", lambda *args: ["gemini-3.5-flash-lite"])
    assert client.get("/api/ai/keys").status_code == 401
    ids = []
    for label in ["Main", "Backup"]:
        response = client.post("/api/ai/keys", headers=a, json={"provider":"gemini", "api_key":"SECRET-KEY-1234", "label":label})
        assert response.status_code == 200, response.text
        assert "SECRET-KEY" not in response.text and "ciphertext" not in response.text
        ids.append(response.json()["id"])
    assert [row["priority"] for row in client.get("/api/ai/keys", headers=a).json()] == [0,1]
    assert client.put("/api/ai/keys/order", headers=a, json={"provider":"gemini","ids":ids[::-1]}).status_code == 200
    assert client.get("/api/ai/keys", headers=a).json()[0]["id"] == ids[1]
    from feedlens import api
    db = dependencies.db()
    assert db.reserve_ai_usage(ids[1], "gemini-3.8-flash", pacific_day(), 100, 20)
    usage = client.get("/api/ai/keys", headers=a).json()[0]["usage_today"]
    assert usage == {"gemini-3.8-flash": {"requests": 1, "limit_rpd": 20}}
    assert client.patch(f"/api/ai/keys/{ids[0]}", headers=b, json={"enabled":False}).status_code == 404
    assert client.delete(f"/api/ai/keys/{ids[0]}", headers=b).status_code == 404
    assert client.patch(f"/api/ai/keys/{ids[0]}", headers=a, json={"label":"Disabled", "enabled":False,"tier":"paid"}).json()["enabled"] is False
    assert client.delete(f"/api/ai/keys/{ids[1]}", headers=a).status_code == 200
    assert client.put("/api/ai/keys/order", headers=a, json={"provider":"gemini","ids":[ids[0],ids[0]]}).status_code == 422
    configured = next(p for p in client.get("/api/ai/providers", headers=a).json() if p["key"] == "gemini")
    assert configured["configured"] is False


def test_exhausted_daily_quota_keeps_completed_batches_and_raw_posts(tmp_path, monkeypatch):
    from feedlens.runs import pipeline
    from feedlens.analysis.llm import LLMAnalyzer
    from feedlens.messages import error_code
    from feedlens.models import RawPost, RunRequest
    from tests.test_core import FakeProvider
    db = Database(f"sqlite:///{tmp_path / 'partial.db'}")
    user = db.local_user_id(); key = db.add_key(user, "gemini", "cipher", "1234")
    clock = Clock()
    provider = FakeProvider()
    scheduler = QuotaScheduler(db, clock=clock.clock, sleep=clock.sleep,
                               default_limits=lambda *a: Limits(rpm=5, tpm=250_000, rpd=1))
    candidates = [Candidate(key.id, provider)]
    analyzer = LLMAnalyzer(provider, candidates=candidates, scheduler=scheduler)
    monkeypatch.setattr(analysis_prompts, "BATCH_SIZE", 1)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a: analyzer)
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = db.create_run(req, user)
    raw = [RawPost(platform="facebook", source="feed", text=f"Original post {i}") for i in range(2)]
    pipeline.execute_analysis(db, rid, req, raw, user)
    run = db.get_run(rid)
    assert run["status"] == "analysis_failed"
    assert error_code(run["error"], analysis_error=True) == "error.ai_quota"
    assert sum(p.analyzed for p in db.get_posts(rid)) == 1 and len(db.get_raw_posts(rid)) == 2
    with pytest.raises(QuotaExhausted):
        scheduler.acquire(candidates, 1)
    # A process restart must not reset the daily allowance.
    fresh = QuotaScheduler(db, clock=clock.clock, sleep=clock.sleep,
                           default_limits=lambda *a: Limits(rpd=1))
    with pytest.raises(QuotaExhausted):
        fresh.acquire([Candidate(key.id, provider)], 1)


def test_minute_wait_uses_another_key_of_the_same_model():
    clock = Clock(); primary = Provider("gemini-3.5-flash-lite", clock); backup = Provider(primary.model, clock)
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep,
        default_limits=lambda *a: Limits(rpm=1, rpd=100))
    candidates = [Candidate(1, primary), Candidate(2, backup, priority=1)]
    scheduler.complete_json(candidates, "", "", {})
    scheduler.complete_json(candidates, "", "", {})
    assert primary.calls == [0] and backup.calls == [0]


def test_token_window_waits_until_reserved_tokens_expire():
    clock = Clock(); provider = Provider("gemini-3.5-flash-lite", clock)
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep,
        default_limits=lambda *a: Limits(tpm=20_000))
    candidates = [Candidate(1, provider)]
    for _ in range(3):
        scheduler.complete_json(candidates, "", "p" * 6000, {})
    assert provider.calls == [0, 60, 120]


def test_daily_vendor_exhaustion_survives_restart_and_resets_on_pacific_midnight(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'daily.db'}")
    key = db.add_key(db.local_user_id(), "gemini", "cipher", "1234")
    clock = Clock(); wall = [datetime(2026, 11, 17, 7, 59, tzinfo=timezone.utc)]
    provider = Provider("gemini-3.5-flash-lite", clock)
    provider.complete_json = lambda *a: (_ for _ in ()).throw(RuntimeError("429 limit: 500, quotaId: GenerateRequestsPerDayPerProjectPerModel"))
    scheduler = QuotaScheduler(db, clock=clock.clock, sleep=clock.sleep, now=lambda: wall[0])
    with pytest.raises(QuotaExhausted):
        scheduler.complete_json([Candidate(key.id, provider)], "", "", {})
    fresh = QuotaScheduler(db, clock=clock.clock, sleep=clock.sleep, now=lambda: wall[0])
    with pytest.raises(QuotaExhausted):
        fresh.acquire([Candidate(key.id, provider)], 1)
    wall[0] = datetime(2026, 11, 17, 8, 1, tzinfo=timezone.utc)
    assert pacific_day(wall[0]) == "2026-11-17"
    assert fresh.acquire([Candidate(key.id, provider)], 1)


def test_limit_learning_accepts_provider_message_order_and_paid_has_no_defaults():
    from feedlens.ai.limits import default_limits, learn_limits
    assert learn_limits("limit: 7, quotaId: GenerateRequestsPerMinutePerProjectPerModel", Limits()).rpm == 7
    assert learn_limits("quotaId: GenerateTokensPerMinutePerProjectPerModel limit: 1234", Limits()).tpm == 1234
    assert learn_limits("limit: 20, quotaId: GenerateRequestsPerDayPerProjectPerModel", Limits()).rpd == 20
    assert default_limits("gemini", "gemini-3.8-flash", "paid") == Limits()


def test_concurrent_daily_reservations_cannot_overspend(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    db = Database(f"sqlite:///{tmp_path / 'concurrent.db'}")
    key = db.add_key(db.local_user_id(), "gemini", "cipher", "1234")
    clock = Clock(); provider = Provider("gemini-3.5-flash-lite", clock)
    scheduler = QuotaScheduler(db, clock=clock.clock, sleep=clock.sleep,
        default_limits=lambda *a: Limits(rpd=5))
    def reserve(_):
        try:
            scheduler.acquire([Candidate(key.id, provider)], 1)
            return True
        except QuotaExhausted:
            return False
    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(reserve, range(25))) == 5
    assert db.ai_usage(key.id, pacific_day())[provider.model]["requests"] == 5


def test_custom_system_calls_share_analyzer_quota():
    from feedlens.analysis.llm import LLMAnalyzer
    clock = Clock(); provider = Provider("gemini-3.8-flash", clock)
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep,
        default_limits=lambda *a: Limits(rpm=1))
    analyzer = LLMAnalyzer(provider, scheduler=scheduler)
    analyzer.complete_json("Search instructions", "question", {}, "low")
    analyzer._json_call("classify", {}, "low")
    assert provider.calls == [0, 60]


def test_get_analyzer_uses_all_enabled_keys_and_shared_persistent_scheduler(tmp_path, monkeypatch):
    from feedlens.analysis import analyzer as module
    from feedlens.ai.registry import user_key_list
    from feedlens.crypto import encrypt
    db = Database(f"sqlite:///{tmp_path / 'credentials.db'}")
    user = db.local_user_id()
    first = db.add_key(user, "gemini", encrypt("first-secret"), "cret")
    second = db.add_key(user, "gemini", encrypt("second-secret"), "cret")
    disabled = db.add_key(user, "gemini", encrypt("disabled-secret"), "cret")
    db.update_key(user, disabled.id, {"enabled": False})
    clock = Clock()
    def provider(key, model, secret):
        value = Provider(model, clock)
        if secret == "first-secret":
            def unauthorized(*a): raise RuntimeError("401 Unauthorized")
            value.complete_json = unauthorized
        return value
    monkeypatch.setattr(ai_registry, "get_provider", provider)
    monkeypatch.setattr(ai_registry, "resolve_models", lambda user, key, secret, requested: [requested])
    one = module.get_analyzer("gemini", "explicit-model", user_key_list(db, user), user)
    two = module.get_analyzer("gemini", "explicit-model", user_key_list(db, user), user)
    assert one.scheduler is two.scheduler
    assert [c.key_id for c in one.candidates] == [first.id, second.id]
    assert one._json_call("hello", {}, "low") == {"ok": True}
    assert one.scheduler.status[first.id] == "invalid"
    assert db.ai_usage(second.id, pacific_day())["explicit-model"]["requests"] == 1


def test_paid_key_only_obeys_retry_after_including_long_waits():
    clock = Clock(); provider = Provider("gemini-3.8-flash", clock)
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    candidate = Candidate(1, provider, tier="paid")
    scheduler.learned[candidate.pair] = Limits(rpm=0, tpm=1, rpd=0)
    def complete(*a):
        provider.calls.append(clock.value)
        if len(provider.calls) == 1:
            error = RuntimeError("429 PerMinute limit: 1")
            error.response = SimpleNamespace(headers={"retry-after": "120"})
            raise error
        return {"ok": True}
    provider.complete_json = complete
    assert scheduler.complete_json([candidate], "", "", {}) == {"ok": True}
    assert provider.calls == [0, 120]


@pytest.mark.parametrize("has_backup", [False, True])
def test_paid_continuous_429_stops_or_uses_next_model(has_backup):
    clock = Clock(); primary = Provider("primary", clock); backup = Provider("backup", clock)
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    def limited(*args):
        primary.calls.append(clock.value)
        if len(primary.calls) > 3:
            pytest.fail("429 retry loop exceeded its finite budget")
        raise RuntimeError("429 retry in 1s")
    primary.complete_json = limited
    candidates = [Candidate(1, primary, tier="paid")]
    if has_backup:
        # Another model on the same key must remain eligible.
        candidates.append(Candidate(1, backup, tier="paid"))
        assert scheduler.complete_json(candidates, "", "", {}) == {"ok": True}
        assert backup.calls == [2]
    else:
        with pytest.raises(QuotaExhausted):
            scheduler.complete_json(candidates, "", "", {})
    assert primary.calls == [0, 1, 2]


def test_success_resets_consecutive_429_retry_budget():
    clock = Clock(); provider = Provider("primary", clock)
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    def complete(*args):
        provider.calls.append(clock.value)
        if len(provider.calls) % 3:
            raise RuntimeError("429 retry in 1s")
        return {"ok": True}
    provider.complete_json = complete
    candidates = [Candidate(1, provider, tier="paid")]
    for _ in range(2):
        assert scheduler.complete_json(candidates, "", "", {}) == {"ok": True}
    assert len(provider.calls) == 6 and clock.value == 4
