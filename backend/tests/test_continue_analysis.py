import pytest

from feedlens import api, pipeline
from feedlens.analyzer import HeuristicAnalyzer
from feedlens.models import RawPost, RunRequest
from tests.test_cloud import cloud, _signup


@pytest.mark.parametrize("status", ["error", "analysis_failed", "done"])
def test_legacy_saved_rows_without_raw_snapshot_can_continue_digest(cloud, monkeypatch, status):
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="offline", only_new=True)
    rid = api.db().create_run(req, user_id, status=status)
    raw = [RawPost(platform="facebook", source="feed", author="Author", text="Original post text", url="https://example.test/posts/1")]
    analyzer = HeuristicAnalyzer()
    api.db().save_batch(rid, analyzer.classify(raw, False, [], "", lambda *a: None))
    assert not api.db().get_raw_posts(rid)
    assert client.get(f"/api/runs/{rid}", headers=headers).json()["can_continue_analysis"] is True
    monkeypatch.setattr(analyzer, "classify", lambda *a: pytest.fail("Legacy completed rows must not be classified again"))
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a: analyzer)
    monkeypatch.setattr(pipeline, "scrape", lambda *a: pytest.fail("Retry must not browse"))
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    response = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "offline"})
    assert response.status_code == 200, response.text
    assert len(api.db().get_raw_posts(rid)) == 1  # only_new did not discard its own saved rows.
    assert api.db().get_run(rid)["digest"]
    assert client.get(f"/api/runs/{rid}", headers=headers).json()["can_continue_analysis"] is False


@pytest.mark.parametrize("status", ["error", "analysis_failed", "done"])
def test_partial_saved_raw_can_continue_even_when_an_old_digest_exists(cloud, monkeypatch, status):
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = api.db().create_run(req, user_id, status=status)
    raw = [RawPost(platform="facebook", source="feed", text=f"Saved partial scrape post {i}") for i in range(3)]
    analyzer = HeuristicAnalyzer()
    api.db().save_raw_posts(rid, raw)
    completed = analyzer.classify(raw[:1], False, [], "", lambda *a: None)
    api.db().save_batch(rid, completed)
    api.db().update_run(rid, digest=analyzer.digest(completed, False))
    classify = analyzer.classify; seen = []
    def record(posts, *args):
        seen.extend(p.text for p in posts)
        return classify(posts, *args)
    monkeypatch.setattr(analyzer, "classify", record)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a: analyzer)
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    assert client.get(f"/api/runs/{rid}", headers=headers).json()["can_continue_analysis"] is True
    assert client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "offline"}).status_code == 200
    assert seen == [p.text for p in raw[1:]]
    assert len(api.db().get_posts(rid)) == 3


@pytest.mark.parametrize("status", ["pending", "queued", "scraping", "analyzing"])
def test_active_runs_cannot_launch_parallel_analysis(cloud, status):
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    rid = api.db().create_run(RunRequest(platform="facebook"), user_id, status=status)
    api.db().save_raw_posts(rid, [RawPost(platform="facebook", source="feed", text="Saved post")])
    assert client.get(f"/api/runs/{rid}", headers=headers).json()["can_continue_analysis"] is False
    assert client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "offline"}).status_code == 409


def test_offline_completed_run_can_reanalyze_every_post_with_fake_ai(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="offline", keywords=["python"])
    rid = api.db().create_run(req, user_id)
    raw = [RawPost(platform="facebook", source="group", text=f"Offline post number {i}") for i in range(3)]
    offline = HeuristicAnalyzer()
    api.db().save_raw_posts(rid, raw)
    api.db().save_batch(rid, offline.classify(raw, False, [], "", lambda *a: None))
    api.db().update_run(rid, status="done", digest=offline.digest(api.db().get_posts(rid), False), ai_label=offline.label)

    class FakeAI(HeuristicAnalyzer):
        label = "Fake AI provider"

    fake = FakeAI(); classified = []
    classify = fake.classify
    def record(posts, *args):
        classified.extend(post.text for post in posts)
        return classify(posts, *args)
    monkeypatch.setattr(fake, "classify", record)
    monkeypatch.setattr(api, "_check_ai", lambda *args: None)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: fake)
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))

    assert client.get(f"/api/runs/{rid}", headers=headers).json()["can_reanalyze_ai"] is True
    response = client.post(f"/api/runs/{rid}/analysis", headers=headers,
                           json={"ai_provider": "openai", "ai_model": "fake-model", "mode": "reanalyze_all"})
    assert response.status_code == 200, response.text
    assert classified == [post.text for post in raw]
    assert api.db().get_run(rid)["ai_label"] == fake.label
    assert api.db().get_run(rid)["digest"]["overall"]


def test_offline_full_reanalysis_reports_missing_ai_key(cloud):
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = api.db().create_run(req, user_id, status="done")
    api.db().save_raw_posts(rid, [RawPost(platform="facebook", source="feed", text="Saved offline post")])
    api.db().update_run(rid, ai_label=HeuristicAnalyzer.label)

    response = client.post(f"/api/runs/{rid}/analysis", headers=headers,
                           json={"ai_provider": "openai", "mode": "reanalyze_all"})
    assert response.status_code == 400
    assert response.json()["code"] == "error.key_missing"


def test_only_offline_completed_runs_allow_full_reanalysis(cloud):
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    rid = api.db().create_run(RunRequest(platform="facebook", ai_provider="openai"), user_id, status="done")
    api.db().save_raw_posts(rid, [RawPost(platform="facebook", source="feed", text="Already AI analyzed")])
    api.db().update_run(rid, ai_label="OpenAI")

    response = client.post(f"/api/runs/{rid}/analysis", headers=headers,
                           json={"ai_provider": "openai", "mode": "reanalyze_all"})
    assert response.status_code == 409
