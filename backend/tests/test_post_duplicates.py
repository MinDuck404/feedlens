import pytest

from feedlens.models import RawPost
from feedlens.post_duplicates import group_posts, normalize_text
from tests.test_cloud import cloud, _signup


TEXT = ("Acme tuyển Backend Developer Python tại Hà Nội, lương 30 triệu.\n"
        "Bạn sẽ xây dựng hệ thống quản lý đơn hàng, làm việc cùng đội ngũ kỹ thuật "
        "và phát triển các tính năng phục vụ khách hàng. Yêu cầu kinh nghiệm phát triển "
        "phần mềm, tinh thần hợp tác. Gửi CV qua email hr@acme.test để ứng tuyển.")


def post(text=TEXT, source="Nhóm A", url="https://example.test/1", platform="facebook"):
    return RawPost(platform=platform, source=source, text=text, url=url)


def test_normalization_removes_decorations_and_tracking_but_keeps_url_identity():
    assert normalize_text("  HELLO 🎉 #Hiring https://a.test/job?id=1&utm_source=fb&fbclid=x ") == "hello https a test job id 1"
    assert normalize_text("https://a.test/job?id=2") != normalize_text("https://a.test/job?id=1")
    assert normalize_text("https://[broken #Jobs") == "https broken"


@pytest.mark.parametrize("variant", [TEXT, TEXT.replace("Gửi CV", "Vui lòng gửi CV"), "🎉 " + TEXT + " #Hiring #Jobs"])
def test_copies_share_one_representative_with_all_sources(variant):
    groups = group_posts([post(), post(variant, "Nhóm B", "https://example.test/2")])
    assert len(groups) == 1
    assert len(groups[0]) == 2
    assert groups[0][0].text == max([TEXT, variant], key=len)


@pytest.mark.parametrize("variant", [TEXT.replace("Backend", "Frontend"), TEXT.replace("30 triệu", "40 triệu"), "Ai cần tuyển dev inbox"])
def test_different_roles_salary_and_short_posts_stay_separate(variant):
    original = variant if len(variant) < 80 else TEXT
    assert len(group_posts([post(original), post(variant, "Nhóm B")])) == 2


@pytest.mark.parametrize("left,right", [("C++", "C#"), ("USD $", "EUR €")])
def test_technology_and_currency_symbols_remain_meaningful(left, right):
    assert len(group_posts([post(TEXT + " " + left), post(TEXT + " " + right, "Nhóm B")])) == 2


def test_platforms_and_distinct_linkedin_job_ids_stay_separate():
    assert len(group_posts([post(), post(platform="reddit")])) == 2
    a = post().model_copy(update={"platform": "linkedin"})
    from feedlens.models import JobSeed
    a.job_seed = JobSeed(job_id="1")
    b = a.model_copy(update={"job_seed": JobSeed(job_id="2")})
    assert len(group_posts([a, b])) == 2


@pytest.mark.parametrize("provider", ["offline", "openai"])
@pytest.mark.parametrize("variant", [TEXT, TEXT + " #Hiring"])
def test_pipeline_analyzes_only_representatives_and_inherits_results(tmp_path, monkeypatch, provider, variant):
    from sqlalchemy import select
    from feedlens import pipeline
    from feedlens.analyzer import HeuristicAnalyzer
    from feedlens.db import Database
    from feedlens.db.tables import PostRow
    from feedlens.models import RunRequest

    db = Database(f"sqlite:///{tmp_path / 'posts.db'}")
    req = RunRequest(platform="facebook", ai_provider=provider, job_mode=True)
    rid = db.create_run(req)
    raw = [post(), post(variant, "Nhóm B", "https://example.test/2")]
    analyzer = HeuristicAnalyzer()
    if provider != "offline":
        analyzer.label = "Fake AI"
    classify = analyzer.classify
    calls = []

    def classify_once(posts, *args):
        calls.extend(posts)
        return classify(posts, *args)

    monkeypatch.setattr(analyzer, "classify", classify_once)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: analyzer)
    pipeline.execute_analysis(db, rid, req, raw, None)
    assert db.get_run(rid)["status"] == "done"
    assert len(calls) == 1
    saved = db.get_posts(rid, include_raw=True)
    assert len(saved) == 1
    assert {s.source for s in saved[0].sources} == {"Nhóm A", "Nhóm B"}
    assert {s.url for s in saved[0].sources} == {p.url for p in raw}
    # Stored duplicate rows retain the original identity and inherit the AI output.
    with db.Session() as session:
        rows = session.scalars(select(PostRow).where(PostRow.run_id == rid)).all()
        assert len(rows) == 2
        assert rows[0].category == rows[1].category
        assert rows[0].summary == rows[1].summary
        assert rows[0].job == rows[1].job
    assert db.analysis_counts(rid)["total"] == 1
    assert db.analysis_counts(rid)["ai"] == (provider != "offline")
    assert not db.can_continue_analysis(rid)
    assert sum(c["count"] for c in db.get_run(rid)["digest"]["categories"]) == 1
    pipeline.execute_analysis(db, rid, req, db.get_raw_posts(rid), None)
    assert len(calls) == 1
    other_run = db.create_run(req)
    pipeline.execute_analysis(db, other_run, req, raw, None)
    assert len(calls) == 2  # Grouping never crosses run boundaries.


def test_migration_preserves_old_cards_until_reanalysis(tmp_path, monkeypatch):
    from sqlalchemy import text
    from feedlens import pipeline
    from feedlens.analyzer import HeuristicAnalyzer
    from feedlens.db import Database
    from feedlens.models import AnalyzedPost, RunRequest

    url = f"sqlite:///{tmp_path / 'old.db'}"
    db = Database(url)
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = db.create_run(req)
    raw = [post(), post(TEXT + " #Hiring", "Nhóm B", "https://example.test/2")]
    db.save_raw_posts(rid, raw)
    db.save_posts(rid, [AnalyzedPost(**p.model_dump(), category="job", summary="Old") for p in raw])
    with db.engine.begin() as conn:
        conn.execute(text("ALTER TABLE runs DROP COLUMN post_groups"))
    db.engine.dispose()
    db = Database(url)
    assert len(db.get_posts(rid)) == 2
    assert all(p.summary == "Old" and not p.sources for p in db.get_posts(rid))
    analyzer = HeuristicAnalyzer()
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: analyzer)
    pipeline.execute_analysis(db, rid, req, db.get_raw_posts(rid), None, reanalyze_all=True)
    assert db.get_run(rid)["status"] == "done"
    assert len(db.get_posts(rid)) == 1


def test_pipeline_keeps_identical_short_posts_and_hash_collisions(tmp_path, monkeypatch):
    from feedlens import pipeline
    from feedlens.analyzer import HeuristicAnalyzer
    from feedlens.db import Database
    from feedlens.models import RunRequest

    db = Database(f"sqlite:///{tmp_path / 'short.db'}")
    req = RunRequest(platform="facebook", ai_provider="offline")
    analyzer = HeuristicAnalyzer()
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: analyzer)
    for texts in [("Ai cần tuyển dev inbox",) * 2, (TEXT * 3 + " lương 30 triệu", TEXT * 3 + " lương 40 triệu")]:
        rid = db.create_run(req)
        raw = [post(texts[0]), post(texts[1], "Nhóm B", "https://example.test/2")]
        pipeline.execute_analysis(db, rid, req, raw, None)
        assert db.get_run(rid)["status"] == "done"
        assert len(db.get_posts(rid, include_raw=True)) == 2


def test_api_exposes_sources_and_counts_only_representatives(cloud, monkeypatch):
    from feedlens import api, pipeline
    from feedlens.analyzer import HeuristicAnalyzer
    from feedlens.models import RunRequest

    client = cloud()
    headers = _signup(client)
    db = api.db()
    uid = db.get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="offline")
    rid = db.create_run(req, uid)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: HeuristicAnalyzer())
    pipeline.execute_analysis(db, rid, req, [post(), post(TEXT, "Nhóm B", "https://example.test/2")], uid)
    response = client.get(f"/api/runs/{rid}", headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert len(result["posts"]) == 1
    assert result["analysis_counts"]["total"] == 1
    assert result["posts"][0]["sources"] == [
        {"source": "Nhóm A", "url": "https://example.test/1"},
        {"source": "Nhóm B", "url": "https://example.test/2"},
    ]


def test_interrupted_analysis_keeps_duplicate_inheritance_and_retries_only_missing(tmp_path, monkeypatch):
    from feedlens import pipeline
    from feedlens.analyzer import HeuristicAnalyzer
    from feedlens.db import Database
    from feedlens.models import RunRequest

    db = Database(f"sqlite:///{tmp_path / 'retry.db'}")
    req = RunRequest(platform="facebook", ai_provider="openai")
    rid = db.create_run(req)
    raw = [post(), post(TEXT, "Nhóm B", "https://example.test/2"), post("A separate news story", "feed", "https://example.test/3")]
    analyzer = HeuristicAnalyzer()
    analyzer.label = "Fake AI"
    classify = analyzer.classify
    fail = [True]
    calls = []

    def classify_batch(posts, *args):
        calls.append([p.text for p in posts])
        result = classify(posts, *args)
        if fail[0]:
            analyzer.on_batch(result[:1])
            raise RuntimeError("429 quota exhausted")
        return result

    monkeypatch.setattr(analyzer, "classify", classify_batch)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: analyzer)
    pipeline.execute_analysis(db, rid, req, raw, None)
    assert db.get_run(rid)["status"] == "analysis_failed"
    assert db.analysis_counts(rid) == {"ai": 1, "offline": 0, "pending": 1, "total": 2}
    saved = db.get_posts(rid, include_raw=True)
    assert len(saved) == 2 and len(saved[0].sources) == 2 and saved[0].analyzed
    fail[0] = False
    pipeline.execute_analysis(db, rid, req, db.get_raw_posts(rid), None)
    assert db.get_run(rid)["status"] == "done"
    assert calls == [[TEXT, "A separate news story"], ["A separate news story"]]
