
import feedlens.ai.registry as ai_registry
import feedlens.routes.dependencies as dependencies
from feedlens import api
from feedlens.runs import pipeline
from feedlens.ai import registry
from feedlens.analysis.heuristic import HeuristicAnalyzer
from feedlens.db.repository import Database
from feedlens.core.models import RawPost
from feedlens.core.models import RunRequest
from feedlens.db.tables import UserRow
from sqlalchemy import text
from tests.test_cloud import cloud, _signup


def test_default_ai_is_per_user_validated_and_survives_stale_preferences(cloud, monkeypatch):
    client = cloud()
    a, b = _signup(client), _signup(client, "second@example.test")
    monkeypatch.setattr(ai_registry, "list_models", lambda *args: ["demo-model"])
    assert client.put("/api/ai/default", json={"provider": "gemini"}).status_code == 401
    assert client.put("/api/ai/default", headers=a, json={"provider": "unknown"}).status_code == 404
    assert client.put("/api/ai/default", headers=a, json={"provider": "gemini"}).status_code == 400
    for provider in ("anthropic", "gemini"):
        assert client.put(f"/api/ai/keys/{provider}", headers=a, json={"api_key": "fake-valid-key-1234"}).status_code == 200
    assert client.put("/api/ai/default", headers=a, json={"provider": "gemini"}).status_code == 200
    providers = client.get("/api/ai/providers", headers=a).json()
    assert [p["key"] for p in providers if p.get("is_default")] == ["gemini"]
    assert not any(p.get("is_default") for p in client.get("/api/ai/providers", headers=b).json())
    client.put("/api/preferences", headers=a, json={"composer": {"count": 40}})
    prefs = client.get("/api/preferences", headers=a).json()
    assert prefs["composer"]["count"] == 40
    assert [p["key"] for p in client.get("/api/ai/providers", headers=a).json() if p.get("is_default")] == ["gemini"]
    client.delete("/api/ai/keys/gemini", headers=a)
    user_id = dependencies.db().get_user_by_email("a@x.io").id
    assert dependencies.db().get_default_ai(user_id) is None
    assert [p["key"] for p in client.get("/api/ai/providers", headers=a).json() if p.get("is_default")] == ["anthropic"]


def test_auto_analysis_uses_user_default_and_explicit_provider_wins(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'default.db'}")
    user = db.local_user_id()
    db.set_default_ai(user, "gemini")
    keys = {"anthropic": ("key-a", "db"), "gemini": ("key-g", "db")}
    monkeypatch.setattr(registry, "user_keys", lambda *a: keys)
    selected = []
    monkeypatch.setattr(pipeline, "get_analyzer", lambda provider, *a: selected.append(provider) or HeuristicAnalyzer())
    for provider in ("auto", "anthropic"):
        req = RunRequest(platform="facebook", ai_provider=provider)
        rid = db.create_run(req, user)
        pipeline.execute_analysis(db, rid, req, [RawPost(platform="facebook", source="feed", text="Demo article")], user)
        assert db.get_run(rid)["status"] == "done"
    assert selected == ["gemini", "anthropic"]
    assert registry.resolve_provider_key("auto", {"anthropic": ("key", "db")}, "gemini") == "anthropic"


def test_default_column_migrates_and_stale_composer_write_cannot_replace_it(tmp_path):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    db = Database(url)
    user_id = db.local_user_id()
    db.set_preferences(user_id, {"composer": {"count": 40}})
    with db.engine.begin() as connection:
        connection.execute(text("ALTER TABLE users DROP COLUMN default_ai_provider"))
    db.engine.dispose()
    db = Database(url)
    with db.Session() as stale:
        user = stale.get(UserRow, user_id)
        assert user.default_ai_provider is None
        db.set_default_ai(user_id, "gemini")
        user.preferences = {"composer": {"count": 80}}
        stale.commit()
    assert db.get_default_ai(user_id) == "gemini"
    assert db.get_preferences(user_id) == {"composer": {"count": 80}}
