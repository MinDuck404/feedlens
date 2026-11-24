
import feedlens.routes.dependencies as dependencies
import feedlens.routes.runs as run_routes
import pytest

from feedlens import api
from feedlens.runs import pipeline
from feedlens.analysis.heuristic import HeuristicAnalyzer
from feedlens.core.models import RawPost
from feedlens.core.models import RunRequest
from tests.test_cloud import cloud, _signup


@pytest.mark.parametrize("status", ["error", "analysis_failed", "done"])
def test_legacy_saved_rows_without_raw_snapshot_can_continue_digest(cloud, monkeypatch, status):
    client = cloud(); headers = _signup(client)
    user_id = dependencies.db().get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="offline", only_new=True)
    rid = dependencies.db().create_run(req, user_id, status=status)
    raw = [RawPost(platform="facebook", source="feed", author="Author", text="Original post text", url="https://example.test/posts/1")]
    analyzer = HeuristicAnalyzer()
    dependencies.db().save_batch(rid, analyzer.classify(raw, False, [], "", lambda *a: None))
    assert not dependencies.db().get_raw_posts(rid)
    assert client.get(f"/api/runs/{rid}", headers=headers).json()["can_continue_analysis"] is True
    monkeypatch.setattr(analyzer, "classify", lambda *a: pytest.fail("Legacy completed rows must not be classified again"))
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a: analyzer)
    monkeypatch.setattr(pipeline, "scrape", lambda *a: pytest.fail("Retry must not browse"))
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    response = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "offline"})
    assert response.status_code == 200, response.text
    assert len(dependencies.db().get_raw_posts(rid)) == 1  # only_new did not discard its own saved rows.
    assert dependencies.db().get_run(rid)["digest"]
    assert client.get(f"/api/runs/{rid}", headers=headers).json()["can_continue_analysis"] is False


@pytest.mark.parametrize("status", ["error", "analysis_failed", "done"])
def test_partial_saved_raw_can_continue_even_when_an_old_digest_exists(cloud, monkeypatch, status):
    client = cloud(); headers = _signup(client)
    user_id = dependencies.db().get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = dependencies.db().create_run(req, user_id, status=status)
    raw = [RawPost(platform="facebook", source="feed", text=f"Saved partial scrape post {i}") for i in range(3)]
    analyzer = HeuristicAnalyzer()
    dependencies.db().save_raw_posts(rid, raw)
    completed = analyzer.classify(raw[:1], False, [], "", lambda *a: None)
    dependencies.db().save_batch(rid, completed)
    dependencies.db().update_run(rid, digest=analyzer.digest(completed, False))
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
    assert len(dependencies.db().get_posts(rid)) == 3


@pytest.mark.parametrize("status", ["pending", "queued", "scraping", "analyzing"])
def test_active_runs_cannot_launch_parallel_analysis(cloud, status):
    client = cloud(); headers = _signup(client)
    user_id = dependencies.db().get_user_by_email("a@x.io").id
    rid = dependencies.db().create_run(RunRequest(platform="facebook"), user_id, status=status)
    dependencies.db().save_raw_posts(rid, [RawPost(platform="facebook", source="feed", text="Saved post")])
    assert client.get(f"/api/runs/{rid}", headers=headers).json()["can_continue_analysis"] is False
    assert client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "offline"}).status_code == 409


def test_offline_completed_run_can_reanalyze_every_post_with_fake_ai(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    user_id = dependencies.db().get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="offline", keywords=["python"])
    rid = dependencies.db().create_run(req, user_id)
    raw = [RawPost(platform="facebook", source="group", text=f"Offline post number {i}") for i in range(3)]
    offline = HeuristicAnalyzer()
    dependencies.db().save_raw_posts(rid, raw)
    dependencies.db().save_batch(rid, offline.classify(raw, False, [], "", lambda *a: None))
    dependencies.db().update_run(rid, status="done", digest=offline.digest(dependencies.db().get_posts(rid), False), ai_label=offline.label)

    class FakeAI(HeuristicAnalyzer):
        label = "Fake AI provider"

    fake = FakeAI(); classified = []
    classify = fake.classify
    def record(posts, *args):
        classified.extend(post.text for post in posts)
        return classify(posts, *args)
    monkeypatch.setattr(fake, "classify", record)
    monkeypatch.setattr(run_routes, "_check_ai", lambda *args: None)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: fake)
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))

    assert client.get(f"/api/runs/{rid}", headers=headers).json()["can_reanalyze_ai"] is True
    response = client.post(f"/api/runs/{rid}/analysis", headers=headers,
                           json={"ai_provider": "openai", "ai_model": "fake-model", "mode": "reanalyze_all"})
    assert response.status_code == 200, response.text
    assert classified == [post.text for post in raw]
    assert dependencies.db().get_run(rid)["ai_label"] == fake.label
    assert dependencies.db().get_run(rid)["digest"]["overall"]


def test_completed_ai_run_can_reanalyze_and_resume_only_new_ai_checkpoints(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    database = dependencies.db()
    user_id = database.get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="openai", job_mode=True, keywords=["Python"])
    rid = database.create_run(req, user_id)
    raw = [RawPost(platform="facebook", source="feed", text=f"Tuyển Python Developer {i}") for i in range(4)]
    database.save_raw_posts(rid, raw)
    old_ai = HeuristicAnalyzer()
    existing = old_ai.classify(raw, True, ["Python"], "", lambda *a: None)
    for post in existing:
        post.analyzed_by = "Legacy AI"
    database.save_batch(rid, existing)
    database.update_run(rid, status="done", ai_label="Legacy AI", digest=old_ai.digest(existing, True),
                        request={**req.model_dump(), "analysis_used_ai": True})
    ids = {p.fingerprint: p.id for p in database.get_posts(rid)}

    class PartialAI(HeuristicAnalyzer):
        label = "New AI"

        def classify(self, posts, *args):
            batch = super().classify(posts[:1], *args)
            batch[0].analyzed_by = self.label
            batch[0].summary = "CV-aware checkpoint"
            self.on_batch(batch)
            raise RuntimeError("429 quota exceeded")

    partial = PartialAI()
    monkeypatch.setattr(run_routes, "_check_ai", lambda *args: "openai")
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: partial)
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    monkeypatch.setattr(pipeline, "scrape", lambda *args: pytest.fail("Reanalysis must not scrape"))
    before = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert before["can_reprocess_ai"] is True
    assert before["reanalyze_requests_estimate"] > 0
    response = client.post(f"/api/runs/{rid}/analysis", headers=headers,
                           json={"ai_provider": "openai", "mode": "reanalyze_all"})
    assert response.status_code == 200
    partial_result = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert partial_result["status"] == "analysis_failed"
    assert partial_result["analysis_counts"] == {"ai": 1, "offline": 0, "pending": 3, "total": 4}
    assert [p["analyzed"] for p in partial_result["posts"]] == [True, False, False, False]
    assert {p.fingerprint: p.id for p in database.get_posts(rid)} == ids
    assert database.get_posts(rid)[0].summary == "CV-aware checkpoint"

    resumed = HeuristicAnalyzer()
    resumed.label = partial.label
    seen = []
    classify = HeuristicAnalyzer.classify

    def resume(posts, *args):
        seen.extend(p.text for p in posts)
        result = classify(resumed, posts, *args)
        for post in result:
            post.analyzed_by = resumed.label
        return result

    monkeypatch.setattr(resumed, "classify", resume)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: resumed)
    response = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "openai"})
    assert response.status_code == 200
    assert seen == [post.text for post in raw[1:]]
    final = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert final["status"] == "done" and final["analysis_counts"] == {"ai": 4, "offline": 0, "pending": 0, "total": 4}
    assert {p.fingerprint: p.id for p in database.get_posts(rid)} == ids
    assert all(post["analyzed"] for post in final["posts"])


def test_offline_full_reanalysis_reports_missing_ai_key(cloud):
    client = cloud(); headers = _signup(client)
    user_id = dependencies.db().get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = dependencies.db().create_run(req, user_id, status="done")
    dependencies.db().save_raw_posts(rid, [RawPost(platform="facebook", source="feed", text="Saved offline post")])
    dependencies.db().update_run(rid, ai_label=HeuristicAnalyzer.label)

    response = client.post(f"/api/runs/{rid}/analysis", headers=headers,
                           json={"ai_provider": "openai", "mode": "reanalyze_all"})
    assert response.status_code == 400
    assert response.json()["code"] == "error.key_missing"


def test_completed_ai_run_can_be_fully_reanalyzed(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    user_id = dependencies.db().get_user_by_email("a@x.io").id
    rid = dependencies.db().create_run(RunRequest(platform="facebook", ai_provider="openai"), user_id, status="done")
    dependencies.db().save_raw_posts(rid, [RawPost(platform="facebook", source="feed", text="Already AI analyzed")])
    dependencies.db().update_run(rid, ai_label="OpenAI")

    class FakeAI(HeuristicAnalyzer):
        label = "OpenAI refreshed"

    fake = FakeAI()
    monkeypatch.setattr(run_routes, "_check_ai", lambda *args: "openai")
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: fake)
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    response = client.post(f"/api/runs/{rid}/analysis", headers=headers,
                           json={"ai_provider": "openai", "mode": "reanalyze_all"})
    assert response.status_code == 200
    detail = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert detail["status"] == "done" and detail["ai_label"] == fake.label


@pytest.mark.parametrize("retry_exhausted", [False, True])
def test_interrupted_ai_upgrade_continues_only_offline_posts(cloud, monkeypatch, retry_exhausted):
    client = cloud(); headers = _signup(client)
    database = dependencies.db()
    user_id = database.get_user_by_email("a@x.io").id
    rid = database.create_run(RunRequest(platform="facebook", ai_provider="offline"), user_id)
    raw = [RawPost(platform="facebook", source="feed", text=f"Tuyển Python developer {i}") for i in range(3)]
    offline = HeuristicAnalyzer()
    database.save_raw_posts(rid, raw)
    database.save_batch(rid, offline.classify(raw, True, [], "", lambda *a: None))
    database.update_run(rid, status="done", ai_label=offline.label,
                        digest=offline.digest(database.get_posts(rid), True))

    class FakeAI(HeuristicAnalyzer):
        label = "Fake AI"
        calls = 0
        seen = []

        def classify(self, posts, *args):
            self.calls += 1
            self.seen.append([p.text for p in posts])
            if self.calls == 1:
                batch = super().classify(posts[:1], *args)
                batch[0].summary = "AI checkpoint"
                self.on_batch(batch)
                raise RuntimeError("429 quota exceeded")
            if retry_exhausted:
                raise RuntimeError("429 quota exceeded")
            return super().classify(posts, *args)

    fake = FakeAI()
    monkeypatch.setattr(run_routes, "_check_ai", lambda *args: "openai")
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: fake)
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    monkeypatch.setattr(pipeline, "scrape", lambda *args: pytest.fail("Continue must not browse"))
    response = client.post(f"/api/runs/{rid}/analysis", headers=headers,
                           json={"ai_provider": "openai", "mode": "reanalyze_all"})
    assert response.status_code == 200
    checkpoint = database.get_posts(rid)[0]
    assert database.get_run(rid)["status"] == "analysis_failed"
    partial = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert partial["analysis_counts"] == {"ai": 1, "offline": 0, "pending": 2, "total": 3}
    assert partial["can_continue_analysis"] is True
    assert partial["ai_label"] == fake.label
    response = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "openai"})
    assert response.status_code == 200
    assert fake.seen == [[p.text for p in raw], [p.text for p in raw[1:]]]
    saved = database.get_posts(rid)
    assert saved[0].id == checkpoint.id and saved[0].summary == "AI checkpoint"
    detail = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert detail["analysis_counts"] == {"ai": 1 if retry_exhausted else 3,
                                          "offline": 0, "pending": 2 if retry_exhausted else 0, "total": 3}
    assert [p.analyzed_by for p in saved] == ([fake.label, "pending", "pending"] if retry_exhausted else [fake.label] * 3)
    assert detail["status"] == ("analysis_failed" if retry_exhausted else "done")
    assert detail["ai_label"] == fake.label
    assert detail["can_continue_analysis"] is retry_exhausted
    assert (detail["error_code"] == "error.ai_quota") is retry_exhausted


def test_ai_upgrade_with_no_results_cannot_complete_or_relabel_offline_rows(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    database = dependencies.db()
    user_id = database.get_user_by_email("a@x.io").id
    rid = database.create_run(RunRequest(platform="facebook", ai_provider="offline"), user_id)
    raw = [RawPost(platform="facebook", source="feed", text="Tuyển Python developer")]
    offline = HeuristicAnalyzer()
    database.save_raw_posts(rid, raw)
    database.save_batch(rid, offline.classify(raw, True, [], "", lambda *a: None))
    database.update_run(rid, status="done", digest=offline.digest(database.get_posts(rid), True))

    class EmptyAI(HeuristicAnalyzer):
        label = "Empty AI"

        def classify(self, *args):
            return []

        def digest(self, *args):
            pytest.fail("Offline rows cannot become an AI digest without AI classification")

    monkeypatch.setattr(run_routes, "_check_ai", lambda *args: "openai")
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: EmptyAI())
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    for mode in ("reanalyze_all", "continue"):
        response = client.post(f"/api/runs/{rid}/analysis", headers=headers,
                               json={"ai_provider": "openai", "mode": mode})
        assert response.status_code == 200
        result = client.get(f"/api/runs/{rid}", headers=headers).json()
        assert result["status"] == "analysis_failed" and result["digest"] is None
        assert result["ai_label"] == ""
        assert result["analysis_counts"] == {"ai": 0, "offline": 0, "pending": 1, "total": 1}
        assert result["can_continue_analysis"] is True


def test_analysis_provenance_migrates_legacy_labels_without_losing_rows(tmp_path):
    from sqlalchemy import text
    from feedlens.db.repository import Database

    url = f"sqlite:///{tmp_path / 'provenance.db'}"
    database = Database(url)
    offline = HeuristicAnalyzer()
    ids = []
    for label in (offline.label, "Fake AI", ""):
        rid = database.create_run(RunRequest(platform="facebook", ai_provider="offline"))
        posts = offline.classify([RawPost(platform="facebook", source="feed", text=f"Legacy {label}")],
                                 False, [], "", lambda *a: None)
        database.save_batch(rid, posts)
        database.update_run(rid, ai_label=label, status="done")
        ids.append((rid, database.get_posts(rid)[0].id))
    with database.engine.begin() as connection:
        connection.execute(text("ALTER TABLE posts DROP COLUMN analyzed_by"))
    database.engine.dispose()
    upgraded = Database(url)
    for (rid, post_id), label in zip(ids, ("offline", "Fake AI", "offline")):
        saved = upgraded.get_posts(rid)
        assert len(saved) == 1 and saved[0].id == post_id
        assert saved[0].analyzed_by == label
    upgraded.engine.dispose()
    reopened = Database(url)
    assert reopened.get_posts(ids[1][0])[0].analyzed_by == "Fake AI"


def test_offline_matching_ignores_stopwords_short_tokens_and_partial_words():
    raw = [RawPost(platform="facebook", source="feed", text="Tuyển dụng vị trí các ứng viên cận HCM hoặc nơi khác. Python, React! Lương salary.")]
    result = HeuristicAnalyzer().classify(raw, True, ["các", "hoặc", "cận", "và", "a", "py", "act", "Python", "React"],
                                         "các hoặc cận", lambda *a: None)
    assert result[0].job.match_reason == "Khớp từ khóa: python, react"
    assert result[0].job.match_score == 66  # "act" must not match "React".
    assert result[0].analyzed_by == "offline"
