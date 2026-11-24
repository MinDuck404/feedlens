"""Billing failures rotate credentials without hiding safe provider diagnostics."""
import pytest

from feedlens.ai.base import AIError
from feedlens.ai import registry
from feedlens.ai.limits import Limits
from feedlens.ai.scheduler import AIConfigurationError, Candidate, QuotaScheduler, pacific_day
from feedlens.analysis.analyzer import get_analyzer
from feedlens.core.crypto import encrypt
from feedlens.core.messages import error_code
from feedlens.core.models import RawPost, RunRequest
from feedlens.db.repository import Database
from feedlens.runs import pipeline
from tests.test_ai_quota import Clock, Provider


def provider_error(message, status):
    error = RuntimeError(message)
    error.status_code = status
    return error


@pytest.mark.parametrize("status,message", [
    (400, "Your credit balance is too low to access the Anthropic API"),
    (429, "insufficient_quota"),
    (400, "Billing is not active"),
    (400, "Billing disabled"),
    (400, "Active billing required"),
    (400, "Payment Required"),
    (402, "Account cannot accept this request"),
    (None, "HTTP 402"),
])
def test_billing_failure_uses_next_key_and_disables_all_models_on_failed_key(status, message):
    clock = Clock()
    first = Provider("claude-sonnet-5-5", clock)
    other_model = Provider("claude-haiku", clock)
    backup = Provider(first.model, clock)

    def insufficient_credit(*args):
        first.calls.append(clock.value)
        raise provider_error(message, status)

    first.complete_json = insufficient_credit
    candidates = [Candidate(1, first), Candidate(1, other_model), Candidate(2, backup, priority=1)]
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, default_limits=lambda *args: Limits())

    assert scheduler.complete_json(candidates, "system", "prompt", {}) == {"ok": True}
    assert first.calls == [0] and backup.calls == [0] and not other_model.calls
    assert all(candidate.disabled for candidate in candidates if candidate.key_id == 1)
    assert scheduler.status == {1: "invalid", 2: "ok"}
    assert scheduler.last_failures[candidates[0].pair] == {"kind": "billing", "status": status or 402}
    assert scheduler.daily_requests(candidates[0], pacific_day()) == 0


@pytest.mark.parametrize("failures,code", [
    (("billing", "billing"), "error.ai_billing"),
    (("auth", "billing"), "error.ai_billing"),
    (("billing", "auth"), "error.ai_billing"),
    (("auth", "auth"), "error.ai_auth"),
])
def test_all_disabled_keys_keep_billing_or_auth_error_on_later_calls(failures, code):
    clock, candidates, states = Clock(), [], []
    for key_id, kind in enumerate(failures, 1):
        error = provider_error("Your credit balance is too low" if kind == "billing" else "invalid x-api-key",
                               400 if kind == "billing" else 401)
        for model in ("claude-sonnet-5-5", "claude-haiku"):
            provider = Provider(model, clock)

            def fail(*args, provider=provider, error=error):
                provider.calls.append(clock.value)
                raise error

            provider.complete_json = fail
            candidates.append(Candidate(key_id, provider, priority=key_id))
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, default_limits=lambda *args: Limits())

    for _ in range(2):
        with pytest.raises(AIError) as failed:
            scheduler.complete_json(candidates, "system", "prompt", {}, on_state=states.append)
        assert error_code(str(failed.value), analysis_error=True) == code
        assert states[-1]["state"] == "error" and not states[-1].get("daily")
    assert [candidate.client.calls for candidate in candidates] == [[0], [], [0], []]
    assert scheduler.status == {1: "invalid", 2: "invalid"}


@pytest.mark.parametrize("model", [None, "claude-sonnet-5-5"])
@pytest.mark.parametrize("kind,code", [("billing", "error.ai_billing"), ("auth", "error.ai_auth")])
def test_pinned_key_billing_or_auth_never_uses_another_key(model, kind, code, monkeypatch):
    clock, calls = Clock(), []

    class ScriptedProvider(Provider):
        info = registry.PROVIDERS["anthropic"].info

        def __init__(self, model=None, api_key=None):
            super().__init__(model or self.info.default_model, clock)
            self.key = api_key

        def list_models(self):
            return [self.info.default_model, "claude-opus-4-1"]

        def complete_json(self, *args):
            calls.append((self.key, self.model))
            if self.key == "selected":
                raise provider_error("Your credit balance is too low" if kind == "billing" else "invalid x-api-key",
                                     400 if kind == "billing" else 401)
            return {"ok": True}

    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setitem(registry.PROVIDERS, "anthropic", ScriptedProvider)
    keys = [registry.KeyCredential(1, "anthropic", "backup"), registry.KeyCredential(2, "anthropic", "selected")]
    analyzer = get_analyzer("auto", model, keys, ai_key_id=2)
    analyzer.scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, default_limits=lambda *args: Limits())

    with pytest.raises(AIError) as failed:
        analyzer.complete_json("system", "prompt", {})
    assert error_code(str(failed.value), analysis_error=True) == code
    assert calls == [("selected", model or ScriptedProvider.info.default_model)]
    assert all(candidate.disabled for candidate in analyzer.candidates)


@pytest.mark.parametrize("secret", [
    "sk-demo",
    "sk-ant-demo",
    "AIzaDemo",
    "sk-synthetic-openai-secret",
    "sk-ant-api03-synthetic-anthropic-secret",
    "AIzaSyntheticGoogleApiKey1234567890",
    "0123456789abcdef0123456789abcdef",
    "QWxwaGFCZXRhR2FtbWFEZWx0YQ==",
    "abcdefghijklmnopqrstuvwxyz0123456789-_",
])
def test_configuration_error_keeps_sanitized_capped_provider_detail(secret):
    clock, states = Clock(), []
    provider = Provider("claude-sonnet-5-5", clock)
    backup = Provider(provider.model, clock)
    message = f"Unsupported parameter: temperature. request_id=req_test_123; api_key={secret}. " + "Safe explanation. " * 30

    def invalid_configuration(*args):
        provider.calls.append(clock.value)
        raise provider_error(message, 400)

    provider.complete_json = invalid_configuration
    candidates = [Candidate(1, provider), Candidate(2, backup, priority=1)]
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, default_limits=lambda *args: Limits())

    with pytest.raises(AIConfigurationError) as failed:
        scheduler.complete_json(candidates, "system", "prompt", {}, on_state=states.append)
    detail = states[-1]["detail"]
    assert "Unsupported parameter: temperature" in str(failed.value)
    assert "req_test_123" in detail and "[REDACTED]" in detail and len(detail) <= 300
    assert states[-1]["candidates"][0]["detail"] == detail and str(failed.value).endswith(detail)
    assert secret not in str(failed.value) and secret not in str(states)
    assert error_code(str(failed.value), analysis_error=True) == "error.ai_configuration"
    assert provider.calls == [0] and not backup.calls


def test_configuration_detail_redacts_tokens_before_truncating():
    clock, states = Clock(), []
    provider = Provider("claude-sonnet-5-5", clock)
    secret = "0123456789abcdef" * 4
    message = "Unsupported parameter: temperature. " + "Reason. " * 31 + secret

    def invalid_configuration(*args):
        raise provider_error(message, 400)

    provider.complete_json = invalid_configuration
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, default_limits=lambda *args: Limits())
    with pytest.raises(AIConfigurationError) as failed:
        scheduler.complete_json([Candidate(1, provider)], "system", "prompt", {}, on_state=states.append)
    assert "[REDACTED]" in states[-1]["detail"] and len(states[-1]["detail"]) <= 300
    assert secret[:20] not in str(failed.value) and secret[:20] not in str(states)


@pytest.mark.parametrize("outcome", ["backup", "all_billing", "pinned"])
def test_analysis_run_uses_backup_or_persists_clear_billing_error(outcome, tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'billing.db'}")
    uid = db.local_user_id()
    first = db.add_key(uid, "anthropic", encrypt("first-key"), "hint")
    db.add_key(uid, "anthropic", encrypt("backup-key"), "hint")
    clock, calls = Clock(), []

    class ScriptedProvider(Provider):
        info = registry.PROVIDERS["anthropic"].info

        def __init__(self, model=None, api_key=None):
            super().__init__(model or self.info.default_model, clock)
            self.key = api_key

        def complete_json(self, system, prompt, schema, effort):
            calls.append((self.key, self.model))
            if self.key == "first-key" or outcome == "all_billing":
                raise provider_error("Your credit balance is too low to access the Anthropic API", 400)
            if "items" in schema["properties"]:
                return {"items": [{"id": 0, "category": "news", "summary": "Read", "is_job": False}]}
            return {"overall": "Done", "categories": [], "action_items": []}

    monkeypatch.setitem(registry.PROVIDERS, "anthropic", ScriptedProvider)
    request = RunRequest(platform="facebook", ai_provider="anthropic", ai_model="claude-sonnet-5-5",
                         ai_key_id=first.id if outcome == "pinned" else None)
    rid = db.create_run(request, uid)
    raw = [RawPost(platform="facebook", source="feed", text="An article about Python programming")]
    pipeline.execute_analysis(db, rid, request, raw, uid)
    run = db.get_run(rid)

    if outcome == "backup":
        assert run["status"] == "done" and run["error"] is None
        assert calls == [("first-key", request.ai_model), ("backup-key", request.ai_model), ("backup-key", request.ai_model)]
        assert all(post.analyzed for post in db.get_posts(rid))
    else:
        assert run["status"] == "analysis_failed" and error_code(run["error"], analysis_error=True) == "error.ai_billing"
        expected_keys = ["first-key"] if outcome == "pinned" else ["first-key", "backup-key"]
        assert calls == [(key, request.ai_model) for key in expected_keys]
        assert db.get_raw_posts(rid) == raw and pipeline.PROGRESS[rid]["ai"]["state"] == "error"
