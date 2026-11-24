"""CV conversion keeps useful text when providers are overloaded or too slow."""
from types import SimpleNamespace
import threading
import time

import pytest

from feedlens.ai import registry
from feedlens.analysis import llm
from feedlens.core.crypto import encrypt
from feedlens.routes import dependencies, profile as profile_routes
from tests.test_cloud import cloud, _signup


def configure_provider(client, headers, monkeypatch, reply, discover=None):
    calls = []
    class Provider:
        info = SimpleNamespace(key="gemini", name="Gemini", model_env="GEMINI_MODEL",
                               default_model="gemini-3.5-flash-lite", env_key="GEMINI_API_KEY")
        def __init__(self, model=None, api_key=None):
            self.model = model or self.info.default_model
        def list_models(self):
            return discover() if discover else ["gemini-3.5-flash-lite"]
        def complete_json(self, system, prompt, schema, effort):
            calls.append((self.model, effort))
            return reply(self.model)
    monkeypatch.setitem(registry.PROVIDERS, "gemini", Provider)
    monkeypatch.setattr(llm, "RETRY_BASE_SECONDS", 0)
    uid = dependencies.db().get_user_by_email("a@x.io").id
    dependencies.db().add_key(uid, "gemini", encrypt("synthetic-secret"), "hint", tier="paid")
    return calls


def unavailable(model):
    raise RuntimeError("503 UNAVAILABLE synthetic-secret")


def test_all_models_unavailable_saves_redacted_cv_and_preserves_matching_criteria(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    client.put("/api/profile", headers=headers, json={"markdown": "Previous CV", "primary_roles": ["Backend Developer"],
        "criteria": {"locations": ["Hanoi"], "work_modes": ["remote"]}})
    calls = configure_provider(client, headers, monkeypatch, unavailable)
    response = client.post("/api/profile/cv", headers=headers, data={"ai_provider": "gemini", "language": "en",
        "text": "Python FastAPI Docker developer with testing skills\nEmail: private@example.test"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["ai_status"] == "unavailable" and result["code"] == "error.cv_ai_unavailable"
    assert result["offline"] is True and result["saved"] is True
    stored = client.get("/api/profile", headers=headers).json()
    assert "Python FastAPI" in stored["markdown"] and "private@example.test" not in stored["markdown"]
    assert stored["criteria"]["locations"] == ["Hanoi"] and stored["criteria"]["work_modes"] == ["remote"]
    assert stored["primary_roles"] == ["Backend Developer"]
    assert {model for model, _ in calls} == {"gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash"}
    assert all(effort == "medium" for _, effort in calls)
    assert "synthetic-secret" not in response.text


def test_cv_uses_the_shared_model_fallback_and_keeps_success_as_a_draft(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    def reply(model):
        if model == "gemini-3.5-flash-lite":
            return unavailable(model)
        return {"markdown": "# Python profile", "suggested_roles": ["Backend Developer"], "adjacent_roles": []}
    calls = configure_provider(client, headers, monkeypatch, reply)
    response = client.post("/api/profile/cv", headers=headers, data={"ai_provider": "gemini",
        "text": "Python FastAPI Docker developer with testing skills"})
    assert response.status_code == 200 and response.json()["offline"] is False
    assert response.json()["markdown"] == "# Python profile"
    assert calls[0][0] == "gemini-3.5-flash-lite" and calls[-1][0] == "gemini-3.1-flash-lite"
    assert client.get("/api/profile", headers=headers).json() is None


@pytest.mark.parametrize("blocked_stage", ["discovery", "generation"])
def test_cv_deadline_includes_discovery_and_stops_further_ai_calls(cloud, monkeypatch, blocked_stage):
    client = cloud(); headers = _signup(client)
    release, finished = threading.Event(), threading.Event()
    def block():
        try:
            release.wait(2)
        finally:
            finished.set()
    def reply(model):
        block()
        raise RuntimeError("503 UNAVAILABLE")
    def discover():
        block()
        return ["gemini-3.5-flash-lite"]
    calls = configure_provider(client, headers, monkeypatch, reply,
                               discover if blocked_stage == "discovery" else None)
    monkeypatch.setattr(profile_routes, "CV_DEADLINE_SECONDS", 0.03)
    with client:
        started = time.monotonic()
        try:
            response = client.post("/api/profile/cv", headers=headers, data={"ai_provider": "gemini",
                "text": "Python FastAPI Docker developer with testing skills"})
            assert response.status_code == 200 and response.json()["reason"] == "timeout"
            assert response.json()["saved"] is True and time.monotonic() - started < 1
            assert "FastAPI" in client.get("/api/profile", headers=headers).json()["markdown"]
            count = len(calls)
        finally:
            release.set()
            assert finished.wait(1)
    assert len(calls) == count == (0 if blocked_stage == "discovery" else 1)
