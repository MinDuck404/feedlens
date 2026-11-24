"""Polling metadata never serializes the run's full post corpus."""
import pytest

from feedlens import api, pipeline
from feedlens.analysis.heuristic import HeuristicAnalyzer
from feedlens.models import AnalyzedPost, RawPost, RunRequest
from tests.test_cloud import cloud, _signup


def test_light_detail_omits_posts_preserves_metadata_and_counts_completed(cloud, monkeypatch):
    client = cloud()
    owner, other = _signup(client), _signup(client, "other@example.test")
    uid = api.db().get_user_by_email("a@x.io").id
    rid = api.db().create_run(RunRequest(platform="facebook"), uid, status="analyzing")
    raw = [RawPost(platform="facebook", source="test", text=f"Observed post {i}") for i in range(3)]
    api.db().save_raw_posts(rid, raw)
    api.db().save_batch(rid, [AnalyzedPost(**raw[0].model_dump(), category="news", summary="Done")])
    full = client.get(f"/api/runs/{rid}", headers=owner).json()
    assert len(full["posts"]) == 3
    monkeypatch.setattr(api.db(), "get_posts", lambda *a, **k: pytest.fail("Light polling hydrated posts"))
    monkeypatch.setattr(api.db(), "can_continue_analysis", lambda *a: pytest.fail("Active runs cannot continue analysis"))
    response = client.get(f"/api/runs/{rid}?posts=0", headers=owner)
    assert response.status_code == 200
    light = response.json()
    assert "posts" not in light and light["posts_version"] == 1
    assert {key: value for key, value in light.items() if key != "posts_version"} == {
        key: value for key, value in full.items() if key not in {"posts", "posts_version"}}
    assert client.get(f"/api/runs/{rid}?posts=0", headers=other).status_code == 404
    assert client.get("/api/runs/99999?posts=0", headers=owner).status_code == 404


def test_light_detail_500_posts_is_small_and_version_tracks_checkpoints(cloud):
    client = cloud()
    headers = _signup(client)
    uid = api.db().get_user_by_email("a@x.io").id
    rid = api.db().create_run(RunRequest(platform="facebook", count=500), uid, status="analyzing")
    raw = [RawPost(platform="facebook", source="synthetic", text=f"Post {i}: " + "a" * 2200) for i in range(500)]
    api.db().save_raw_posts(rid, raw)
    api.db().save_batch(rid, [AnalyzedPost(**post.model_dump(), summary="Synthetic analysis") for post in raw[:20]])
    light = client.get(f"/api/runs/{rid}?posts=0", headers=headers)
    full = client.get(f"/api/runs/{rid}", headers=headers)
    assert light.json()["posts_version"] == 20
    assert len(full.json()["posts"]) == 500
    assert len(light.content) < 5000 and len(light.content) < len(full.content) // 100
    print(f"500 synthetic posts: full={len(full.content)} bytes, light={len(light.content)} bytes")
    api.db().save_batch(rid, [AnalyzedPost(**post.model_dump(), summary="Synthetic analysis") for post in raw[20:40]])
    assert client.get(f"/api/runs/{rid}?posts=0", headers=headers).json()["posts_version"] == 40
    api.db().update_run(rid, status="analysis_failed", error="401 Unauthorized")
    terminal = client.get(f"/api/runs/{rid}?posts=0", headers=headers).json()
    assert terminal["can_continue_analysis"] is True and terminal["error_code"] == "error.ai_auth"
    assert "posts" not in terminal


def test_resumed_analysis_reports_unique_progress_and_only_sends_missing_posts(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    db = api.db()
    uid = db.get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="openai")
    rid = db.create_run(req, uid, status="analysis_failed")
    raw = [RawPost(platform="facebook", source="feed", text=f"Observed post {i}") for i in (1, 2, 2, 3)]
    db.save_raw_posts(rid, raw)
    db.save_batch(rid, [AnalyzedPost(**raw[0].model_dump(), analyzed_by="Fake AI")])
    db.save_batch(rid, [AnalyzedPost(**raw[-1].model_dump(), analyzed_by="offline")])

    auth = f"/api/runs/{rid}"
    before = client.get(auth, headers=headers).json()
    assert before["analysis_counts"] == {"ai": 1, "offline": 1, "pending": 1, "total": 3}
    assert len(before["posts"]) == 3

    class FakeAI(HeuristicAnalyzer):
        label = "Fake AI"
        notify = None

        def classify(self, posts, *args):
            assert [p.text for p in posts] == [raw[1].text, raw[-1].text]
            self.notify("Đang chờ hạn mức phút của Fake AI (fake-model): 8 giây")
            waiting = client.get(f"{auth}?posts=0", headers=headers).json()["progress"]
            assert (waiting["done"], waiting["target"]) == (1, 3)
            assert waiting["message_code"] == "progress.quota_wait"
            result = super().classify(posts, *args)
            result[1].analyzed_by = "offline"  # Still omitted by AI after retry.
            self.on_batch(result)
            checkpoint = client.get(f"{auth}?posts=0", headers=headers).json()
            assert (checkpoint["progress"]["done"], checkpoint["progress"]["target"]) == (2, 3)
            assert checkpoint["analysis_counts"]["ai"] == 2
            return result

    monkeypatch.setattr(api, "_check_ai", lambda *a: "openai")
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a: FakeAI())
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    assert client.post(f"{auth}/analysis", headers=headers, json={"ai_provider": "openai"}).status_code == 200
    detail = client.get(auth, headers=headers).json()
    assert detail["status"] == "done"
    assert detail["analysis_counts"] == {"ai": 2, "offline": 1, "pending": 0, "total": 3}
    assert (detail["progress"]["done"], detail["progress"]["target"]) == (2, 3)
    assert detail["collected"] == 4
