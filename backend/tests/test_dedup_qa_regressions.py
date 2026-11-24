
import feedlens.routes.dependencies as dependencies
import feedlens.routes.runs as run_routes
import csv
import io

import pytest
from sqlalchemy import select

from feedlens import api
from feedlens.runs import pipeline
from feedlens.analysis.heuristic import HeuristicAnalyzer
from feedlens.db import Database
from feedlens.db.tables import PostRow
from feedlens.runs.export import to_csv
from feedlens.runs.export import to_markdown
from feedlens.models import AnalyzedPost, PostGroup, PostSource, RawPost, RunRequest
from feedlens.analysis.duplicates import group_posts
from feedlens.analysis.duplicates import preserve_post_identities
from tests.test_cloud import cloud, _signup
from tests.test_post_duplicates import TEXT, post


@pytest.mark.parametrize("changed", [TEXT.replace("tại Hà Nội", "tại Hà Nội hoặc Remote"), TEXT.replace("Backend", "Senior Backend")])
@pytest.mark.parametrize("reverse", [False, True])
def test_internal_insertions_and_deletions_keep_distinct_vacancies(changed, reverse):
    posts = [post(), post(changed, "Group B")]
    assert len(group_posts(posts[::-1] if reverse else posts)) == 2


def test_short_posts_without_urls_keep_each_author_and_identity():
    raw = [post("Ai cần tuyển dev inbox", url="").model_copy(update={"author": author}) for author in ("Alice", "Bob", "Carol")]
    prepared = preserve_post_identities(raw)
    assert len(group_posts(prepared)) == 3
    assert len({p.fingerprint for p in prepared}) == 3


def fake_ai(monkeypatch):
    analyzer = HeuristicAnalyzer()
    analyzer.label = "Fake AI"
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: analyzer)
    return analyzer


def test_legacy_continue_preserves_completed_shorter_copy_when_provider_fails(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'legacy.db'}")
    req = RunRequest(platform="facebook", ai_provider="openai")
    rid = db.create_run(req, status="analysis_failed")
    raw = [post(), post(TEXT + " Inbox mình nhé!", "Group B"), post("A separate post", "feed")]
    db.save_raw_posts(rid, raw)
    db.save_batch(rid, [AnalyzedPost(**raw[0].model_dump(), category="job", summary="Already read", analyzed_by="Fake AI")])
    analyzer = fake_ai(monkeypatch)
    calls = []
    def fail(posts, *args):
        calls.extend(p.text for p in posts)
        raise RuntimeError("429 quota exhausted")
    monkeypatch.setattr(analyzer, "classify", fail)
    pipeline.execute_analysis(db, rid, req, raw, None)
    assert calls == ["A separate post"]
    assert db.analysis_counts(rid) == {"ai": 1, "offline": 0, "pending": 1, "total": 2}
    assert db.get_posts(rid, include_raw=True)[0].summary == "Already read"


def test_preferred_completed_representative_still_matches_every_member(tmp_path, monkeypatch):
    words = [f"word{chr(97 + i // 26)}{chr(97 + i % 26)}abcdefgh" for i in range(50)]
    raw = [post(" ".join(words[5:]), "A"), post(" ".join(words), "B"), post(" ".join(words[:-5]), "C")]
    db = Database(f"sqlite:///{tmp_path / 'preferred.db'}")
    req = RunRequest(platform="facebook", ai_provider="openai")
    rid = db.create_run(req)
    db.save_raw_posts(rid, raw)
    db.save_batch(rid, [AnalyzedPost(**raw[0].model_dump(), analyzed_by="Fake AI", summary="Read")])
    fake_ai(monkeypatch)
    pipeline.execute_analysis(db, rid, req, raw, None)
    assert len(db.get_posts(rid)) == 2


def test_missing_representative_row_still_returns_group_without_include_raw(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'pending.db'}")
    rid = db.create_run(RunRequest(platform="facebook"))
    p = post()
    db.save_raw_posts(rid, [p])
    db.save_post_groups(rid, [PostGroup(fingerprint=p.fingerprint, fingerprints=[p.fingerprint], sources=[PostSource(source=p.source, url=p.url)])])
    posts = db.get_posts(rid)
    assert len(posts) == 1 and not posts[0].analyzed
    assert posts[0].text == TEXT and posts[0].sources[0].url == p.url


@pytest.mark.parametrize("same_observation", [False, True])
def test_legacy_reanalysis_rekeys_existing_rows_without_orphan_pending(cloud, monkeypatch, same_observation):
    client = cloud()
    headers = _signup(client)
    uid = dependencies.db().get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="openai")
    rid = dependencies.db().create_run(req, uid, status="done")
    raw = [post("Ai cần tuyển dev inbox", "Group A"), post("Ai cần tuyển dev inbox", "Group A" if same_observation else "Group B")]
    dependencies.db().save_posts(rid, [AnalyzedPost(**p.model_dump(), analyzed_by="Fake AI") for p in raw])
    original_ids = {p.id for p in dependencies.db().get_posts(rid)}
    fake_ai(monkeypatch)
    monkeypatch.setattr(run_routes, "_check_ai", lambda *args: "openai")
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    result = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"mode": "reanalyze_all", "ai_provider": "openai"})
    assert result.status_code == 200
    assert dependencies.db().get_run(rid)["status"] == "done"
    with dependencies.db().Session() as session:
        rows = session.scalars(select(PostRow).where(PostRow.run_id == rid)).all()
        assert {row.id for row in rows} == original_ids
        assert all(row.analyzed_by != "pending" for row in rows)
    count = 1 if same_observation else 2
    assert dependencies.db().analysis_counts(rid) == {"ai": count, "offline": 0, "pending": 0, "total": count}


def test_history_search_trends_and_retagging_count_representatives_and_keep_legacy(cloud, monkeypatch):
    client = cloud()
    headers = _signup(client)
    uid = dependencies.db().get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="openai")
    fake_ai(monkeypatch)
    rid = dependencies.db().create_run(req, uid)
    raw = [post(TEXT + " #Hiring" * i, f"Group {i}", f"https://example.test/{i}") for i in range(3)]
    pipeline.execute_analysis(dependencies.db(), rid, req, raw, uid)
    old = dependencies.db().create_run(req, uid, status="done")
    dependencies.db().save_posts(old, [AnalyzedPost(**p.model_dump(), analyzed_by="Fake AI") for p in raw])
    foreign = dependencies.db().create_user("other@test.example", "fake-hash")
    other = dependencies.db().create_run(req, foreign)
    pipeline.execute_analysis(dependencies.db(), other, req, raw, foreign)
    assert len(dependencies.db().user_posts(uid)) == 4
    for fts in (True, False):
        found, total = dependencies.db().search_posts(uid, q="Acme", limit=2, offset=1, _use_fts=fts)
        assert total == 4 and len(found) == 2
    assert client.get("/api/search?q=Acme", headers=headers).json()["total"] == 4
    assert client.get("/api/trends?days=30", headers=headers).json()["summary"]["total_posts"] == 4


@pytest.mark.parametrize("digest", [None, {"overall": "Read", "categories": [], "action_items": []}])
def test_markdown_and_csv_preserve_every_grouped_source(digest):
    p = AnalyzedPost(**post().model_dump(), summary="A job", sources=[PostSource(source="Group A", url="https://example.test/a"), PostSource(source="Group B", url="https://example.test/b")])
    run = {"id": 1, "request": {"platform": "facebook", "source_type": "group"}, "created_at": "2026-11-23", "digest": digest}
    md = to_markdown(run, [p])
    csv_text = to_csv([p], run)
    for value in ("Group A", "Group B", "https://example.test/a", "https://example.test/b"):
        assert value in md and value in csv_text
    assert len(list(csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff"))))) == 1
