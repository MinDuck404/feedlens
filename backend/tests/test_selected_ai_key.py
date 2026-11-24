"""User-selected credentials are validated before side effects and never rotated away."""
import pytest
import threading

from feedlens.core.crypto import encrypt
from feedlens.routes import dependencies
from feedlens.ai import registry
from feedlens.ai.scheduler import AIServiceUnavailable, QuotaScheduler
from feedlens.ai.limits import Limits
from feedlens.analysis.analyzer import get_analyzer
from feedlens.core.models import RawPost, RunRequest
from feedlens.runs import pipeline
from tests.test_ai_quota import Clock, Provider
from tests.test_cloud import cloud, _signup, _wait


@pytest.mark.parametrize("selection,status,code", [
    ("foreign", 404, "error.ai_key_unavailable"),
    ("disabled", 404, "error.ai_key_unavailable"),
    ("wrong_provider", 422, "error.ai_key_provider"),
])
def test_new_run_rejects_invalid_selected_key_before_creating_a_run(cloud, selection, status, code):
    client = cloud(); headers = _signup(client)
    _signup(client, "other@example.test")
    db = dependencies.db(); uid = db.get_user_by_email("a@x.io").id
    other = db.get_user_by_email("other@example.test").id
    own = db.add_key(uid, "gemini", encrypt("own-synthetic-secret"), "hint")
    foreign = db.add_key(other, "gemini", encrypt("foreign-synthetic-secret"), "hint")
    wrong = db.add_key(uid, "openai", encrypt("openai-synthetic-secret"), "hint")
    if selection == "disabled":
        db.update_key(uid, own.id, {"enabled": False})
    selected = foreign.id if selection == "foreign" else wrong.id if selection == "wrong_provider" else own.id
    response = client.post("/api/runs", headers=headers, json={"platform": "facebook", "ai_provider": "gemini",
        "ai_model": "chosen-model", "ai_key_id": selected})
    assert response.status_code == status, response.text
    assert response.json()["code"] == code and not db.list_runs(uid)
    assert "synthetic-secret" not in response.text


@pytest.mark.parametrize("model", [None, "chosen-model"])
def test_selected_key_never_rotates_to_another_key(model, monkeypatch):
    clock, calls = Clock(), []
    class ScriptedProvider(Provider):
        info = type("Info", (), {"key": "gemini", "name": "Gemini", "model_env": "GEMINI_MODEL",
                                 "default_model": "gemini-3.5-flash-lite"})()
        def __init__(self, model=None, api_key=None):
            super().__init__(model or self.info.default_model, clock)
            self.key = api_key
        def list_models(self):
            return ["gemini-3.5-flash-lite"]
        def complete_json(self, *args):
            calls.append((self.key, self.model))
            if self.model in {"chosen-model", "gemini-3.5-flash-lite"}:
                raise RuntimeError("503 UNAVAILABLE")
            return {"ok": True}
    monkeypatch.setitem(registry.PROVIDERS, "gemini", ScriptedProvider)
    keys = [registry.KeyCredential(1, "gemini", "first"), registry.KeyCredential(2, "gemini", "selected")]
    analyzer = get_analyzer("auto", model, keys, ai_key_id=2)
    analyzer.scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep, jitter=lambda wait: wait,
                                       default_limits=lambda *args: Limits())
    if model:
        with pytest.raises(AIServiceUnavailable):
            analyzer.complete_json("", "", {})
        assert {selected_model for _, selected_model in calls} == {"chosen-model"}
    else:
        assert analyzer.complete_json("", "", {}) == {"ok": True}
        assert calls == [("selected", "gemini-3.5-flash-lite"), ("selected", "gemini-3.1-flash-lite")]
    assert all(key == "selected" for key, _ in calls)


def test_model_discovery_uses_only_the_selected_owned_key(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    _signup(client, "other@example.test")
    db = dependencies.db(); uid = db.get_user_by_email("a@x.io").id
    primary = db.add_key(uid, "gemini", encrypt("primary"), "hint", "Primary")
    selected = db.add_key(uid, "gemini", encrypt("selected"), "hint", "Selected")
    foreign = db.add_key(db.get_user_by_email("other@example.test").id, "gemini", encrypt("foreign"), "hint")
    calls = []
    class DiscoveryProvider:
        info = type("Info", (), {"name": "Gemini", "model_env": "GEMINI_MODEL", "default_model": "default"})()
        def __init__(self, model=None, api_key=None):
            self.key = api_key
        def list_models(self):
            calls.append(self.key)
            return ["selected-model"] if self.key == "selected" else ["primary-model"]
    monkeypatch.setitem(registry.PROVIDERS, "gemini", DiscoveryProvider)
    response = client.get("/api/ai/models/gemini", headers=headers, params={"ai_key_id": selected.id, "refresh": True})
    assert response.status_code == 200 and response.json()["models"] == ["selected-model"]
    assert calls == ["selected"]
    response = client.get("/api/ai/models/gemini", headers=headers, params={"ai_key_id": foreign.id})
    assert response.status_code == 404 and response.json()["code"] == "error.ai_key_unavailable"
    described = client.get("/api/ai/keys", headers=headers).json()
    assert {key["id"] for key in described} == {primary.id, selected.id}
    assert all({"id", "label", "provider", "status"} <= key.keys() for key in described)
    assert "api_key" not in str(described) and "ciphertext" not in str(described)


@pytest.mark.parametrize("pin_key", [False, True])
def test_run_execution_honors_selected_key_and_legacy_requests_keep_auto_priority(cloud, monkeypatch, pin_key):
    client = cloud(); _signup(client)
    db = dependencies.db(); uid = db.get_user_by_email("a@x.io").id
    db.add_key(uid, "gemini", encrypt("primary-key"), "hint")
    selected = db.add_key(uid, "gemini", encrypt("selected-key"), "hint")
    db.add_key(uid, "openai", encrypt("default-key"), "hint")
    db.set_default_ai(uid, "openai")
    calls = []
    class AnalysisProvider(Provider):
        def __init__(self, model=None, api_key=None):
            super().__init__(model or "default-model", Clock())
            self.key = api_key
        def complete_json(self, system, prompt, schema, effort):
            calls.append(self.key)
            if "items" in schema["properties"]:
                return {"items": [{"id": 0, "category": "news", "summary": "Read", "is_job": False}]}
            return {"overall": "Done", "categories": [], "action_items": []}
    monkeypatch.setitem(registry.PROVIDERS, "gemini", AnalysisProvider)
    monkeypatch.setitem(registry.PROVIDERS, "openai", AnalysisProvider)
    data = {"platform": "facebook", "ai_provider": "auto", "ai_model": "chosen-model"}
    if pin_key:
        data["ai_key_id"] = selected.id
    request = RunRequest(**data)
    assert request.ai_key_id == (selected.id if pin_key else None)
    rid = db.create_run(request, uid)
    pipeline.execute_analysis(db, rid, request, [RawPost(platform="facebook", source="feed", text="A distinct article about Python")], uid)
    assert db.get_run(rid)["status"] == "done", db.get_run(rid)["error"]
    assert set(calls) == {"selected-key" if pin_key else "default-key"}


@pytest.mark.parametrize("reset_auto", [False, True])
def test_retry_analysis_can_change_the_key_or_explicitly_restore_auto(cloud, monkeypatch, reset_auto):
    client = cloud(); headers = _signup(client)
    db = dependencies.db(); uid = db.get_user_by_email("a@x.io").id
    primary = db.add_key(uid, "gemini", encrypt("primary-key"), "hint")
    previous = db.add_key(uid, "gemini", encrypt("previous-key"), "hint")
    calls = []
    class AnalysisProvider(Provider):
        def __init__(self, model=None, api_key=None):
            super().__init__(model or "chosen-model", Clock())
            self.key = api_key
        def complete_json(self, system, prompt, schema, effort):
            calls.append(self.key)
            if "items" in schema["properties"]:
                return {"items": [{"id": 0, "category": "news", "summary": "Read", "is_job": False}]}
            return {"overall": "Done", "categories": [], "action_items": []}
    monkeypatch.setitem(registry.PROVIDERS, "gemini", AnalysisProvider)
    request = RunRequest(platform="facebook", ai_provider="gemini", ai_model="chosen-model", ai_key_id=previous.id)
    rid = db.create_run(request, uid, status="analysis_failed")
    db.save_raw_posts(rid, [RawPost(platform="facebook", source="feed", text="A distinct article about Python")])
    selected = None if reset_auto else primary.id
    response = client.post(f"/api/runs/{rid}/analysis", headers=headers,
        json={"ai_provider": "gemini", "ai_model": "chosen-model", "ai_key_id": selected})
    assert response.status_code == 200, response.text
    result = _wait(client, headers, rid)
    assert result["status"] == "done", result
    assert result["request"]["ai_key_id"] == selected
    assert set(calls) == {"primary-key"}


def test_stop_then_continue_validates_key_selection_before_requesting_a_stop(cloud):
    client = cloud(); headers = _signup(client)
    db = dependencies.db(); uid = db.get_user_by_email("a@x.io").id
    db.add_key(uid, "gemini", encrypt("primary-key"), "hint")
    rid = db.create_run(RunRequest(platform="facebook", ai_provider="gemini"), uid, status="analyzing")
    response = client.post(f"/api/runs/{rid}/analysis/stop", headers=headers,
        json={"ai_provider": "gemini", "ai_model": "chosen-model", "ai_key_id": 99999})
    assert response.status_code == 404 and response.json()["code"] == "error.ai_key_unavailable"


def test_cv_can_pin_a_key_and_model_and_rejects_foreign_keys_without_saving(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    _signup(client, "other@example.test")
    db = dependencies.db(); uid = db.get_user_by_email("a@x.io").id
    db.add_key(uid, "gemini", encrypt("primary"), "hint")
    selected = db.add_key(uid, "gemini", encrypt("selected"), "hint")
    foreign = db.add_key(db.get_user_by_email("other@example.test").id, "gemini", encrypt("foreign"), "hint")
    calls = []
    class CVProvider(Provider):
        info = type("Info", (), {"key": "gemini", "name": "Gemini", "model_env": "GEMINI_MODEL",
                                 "default_model": "gemini-3.5-flash-lite"})()
        def __init__(self, model=None, api_key=None):
            super().__init__(model or self.info.default_model, Clock())
            self.key = api_key
        def list_models(self):
            return ["gemini-3.5-flash-lite"]
        def complete_json(self, *args):
            calls.append((self.key, self.model))
            return {"markdown": "# AI Profile", "suggested_roles": ["Backend Developer"], "adjacent_roles": []}
    monkeypatch.setitem(registry.PROVIDERS, "gemini", CVProvider)
    data = {"text": "Python FastAPI Docker developer with testing skills", "ai_provider": "auto",
            "ai_model": "chosen-model", "ai_key_id": selected.id}
    response = client.post("/api/profile/cv", headers=headers, data=data)
    assert response.status_code == 200 and response.json()["markdown"] == "# AI Profile"
    assert calls == [("selected", "chosen-model")]
    response = client.post("/api/profile/cv", headers=headers, data={**data, "ai_key_id": foreign.id})
    assert response.status_code == 404 and response.json()["code"] == "error.ai_key_unavailable"
    assert client.get("/api/profile", headers=headers).json() is None
    assert calls == [("selected", "chosen-model")]


@pytest.mark.parametrize("invalid_id", [0, -1, True, "2"])
def test_key_selection_requires_a_positive_json_integer(cloud, invalid_id):
    client = cloud(); headers = _signup(client)
    response = client.post("/api/runs", headers=headers,
        json={"platform": "facebook", "ai_provider": "offline", "ai_key_id": invalid_id})
    assert response.status_code == 422 and response.json()["code"] == "error.validation"


def test_stop_and_continue_replaces_the_key_used_for_remaining_analysis(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    db = dependencies.db(); uid = db.get_user_by_email("a@x.io").id
    first = db.add_key(uid, "gemini", encrypt("first-key"), "hint", tier="paid")
    replacement = db.add_key(uid, "gemini", encrypt("replacement-key"), "hint", tier="paid")
    started, release = threading.Event(), threading.Event()
    calls = []
    class AnalysisProvider(Provider):
        def __init__(self, model=None, api_key=None):
            super().__init__(model or "chosen-model", Clock())
            self.key = api_key
        def complete_json(self, system, prompt, schema, effort):
            calls.append((self.key, self.model))
            if self.key == "first-key":
                started.set()
                assert release.wait(2)
            if "items" in schema["properties"]:
                return {"items": [{"id": 0, "category": "news", "summary": "Read", "is_job": False}]}
            return {"overall": "Done", "categories": [], "action_items": []}
    monkeypatch.setitem(registry.PROVIDERS, "gemini", AnalysisProvider)
    request = RunRequest(platform="facebook", ai_provider="gemini", ai_model="first-model", ai_key_id=first.id)
    rid = db.create_run(request, uid, status="analysis_failed")
    db.save_raw_posts(rid, [RawPost(platform="facebook", source="feed", text="A distinct article about Python")])
    try:
        assert client.post(f"/api/runs/{rid}/analysis", headers=headers,
            json={"ai_provider": "gemini", "ai_model": "first-model"}).status_code == 200
        assert started.wait(1)
        response = client.post(f"/api/runs/{rid}/analysis/stop", headers=headers,
            json={"ai_provider": "gemini", "ai_model": "replacement-model", "ai_key_id": replacement.id})
        assert response.status_code == 202 and response.json()["will_continue"] is True
    finally:
        release.set()
    result = _wait(client, headers, rid)
    assert result["status"] == "done", result
    assert result["request"]["ai_key_id"] == replacement.id
    assert result["request"]["ai_model"] == "replacement-model"
    assert ("replacement-key", "replacement-model") in calls
