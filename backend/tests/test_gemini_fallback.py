"""Configured default models survive incomplete discovery and provider overload."""
from feedlens.ai import registry
from feedlens.ai.scheduler import Candidate, QuotaScheduler
from feedlens.ai.limits import default_limits, Limits
from feedlens.ai.scheduler import AIConfigurationError
from feedlens.analysis.analyzer import get_analyzer
from tests.test_ai_quota import Clock, Provider
import pytest


def test_default_gemini_chain_includes_configured_models_missing_from_discovery(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr(registry, "list_models", lambda *args: ["gemini-3.8-flash"])
    assert registry.resolve_models(1, "gemini", "synthetic-secret", None) == [
        "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash",
    ]
    assert registry.resolve_models(1, "gemini", "synthetic-secret", "chosen-model") == ["chosen-model"]


def test_configured_fallback_models_have_their_own_free_limits():
    assert default_limits("gemini", "models/gemini-3.1-flash-lite") == Limits(15, 250_000, 500)
    assert default_limits("gemini", "gemini-3.6-flash") == Limits(5, 250_000, 20)
    assert default_limits("gemini", "gemini-3.1-flash-lite", "paid") == Limits()


@pytest.mark.parametrize("working_pair", [(1, "gemini-3.6-flash"), (2, "gemini-3.5-flash-lite")])
def test_overload_tries_other_models_on_same_key_before_changing_key(working_pair, caplog):
    clock, calls, states = Clock(), [], []
    candidates = []
    for key in (1, 2):
        for model in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash"):
            provider = Provider(model, clock)
            def reply(*args, pair=(key, model)):
                calls.append(pair)
                if pair != working_pair:
                    raise RuntimeError("503 UNAVAILABLE synthetic-secret")
                return {"ok": True}
            provider.complete_json = reply
            candidates.append(Candidate(key, provider, priority=key))
    scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    with caplog.at_level("INFO"):
        assert scheduler.complete_json(candidates, "", "", {}, on_state=states.append) == {"ok": True}
    expected = [(1, "gemini-3.5-flash-lite"), (1, "gemini-3.1-flash-lite"), (1, "gemini-3.6-flash")]
    assert calls == expected + ([(2, "gemini-3.5-flash-lite")] if working_pair[0] == 2 else [])
    assert any(s.get("switch_reason") == "service" and s.get("switched_model") for s in states)
    assert "gemini-3.1-flash-lite" in caplog.text and "overload" in caplog.text
    assert "synthetic-secret" not in caplog.text


@pytest.mark.parametrize("status", [400, 401, 503])
def test_explicit_model_never_changes_and_bad_requests_are_not_retried(status, monkeypatch):
    clock, calls = Clock(), []
    class ScriptedProvider(Provider):
        def __init__(self, model, api_key):
            super().__init__(model, clock)
            self.key = api_key
        def complete_json(self, *args):
            calls.append((self.key, self.model))
            if self.key == "first":
                error = RuntimeError("synthetic provider error")
                error.status_code = status
                raise error
            return {"ok": True}
        def list_models(self):
            pytest.fail("Explicit models do not need model discovery")
    monkeypatch.setitem(registry.PROVIDERS, "gemini", ScriptedProvider)
    keys = [registry.KeyCredential(1, "gemini", "first"), registry.KeyCredential(2, "gemini", "second")]
    analyzer = get_analyzer("gemini", "chosen-model", keys)
    if status == 400:
        with pytest.raises(AIConfigurationError):
            analyzer.complete_json("", "", {})
        assert calls == [("first", "chosen-model")]
    else:
        assert analyzer.complete_json("", "", {}) == {"ok": True}
        assert calls == [("first", "chosen-model"), ("second", "chosen-model")]
