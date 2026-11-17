"""Source contracts are checked without a browser, a live account or paid AI."""
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from feedlens.db import Database
from feedlens.db.tables import RunRow
from feedlens.models import AnalyzedPost, JobInfo, JobSeed, RawPost, RunRequest
from feedlens.source_modes import effective_mode, legacy_agent_compatible, normalize, total_target


@pytest.mark.parametrize("platform,source_type,sources,mode", [
    ("facebook", "feed", [], "feed"), ("facebook", "group", ["g"], "group"),
    ("facebook", "search", ["python"], "search"),
    ("linkedin", "group", ["123"], "legacy_group"),
    ("linkedin", "search", ["python"], "recruiting_posts"), ("linkedin", "feed", [], "feed"),
    ("reddit", "feed", [], "home"), ("reddit", "group", ["r/forhire"], "subreddit"),
    ("reddit", "search", ["python"], "search"),
    ("x", "group", ["@vercel"], "account"),
    ("x", "group", ["https://x.com/i/lists/123"], "list"),
    ("x", "group", ["@vercel", "https://x.com/i/lists/123"], "legacy_group"),
    ("x", "group", ["https://x.com/i/communities/123"], "legacy_group"),
    ("x", "search", ["python"], "search"), ("x", "feed", [], "feed"),
])
def test_legacy_mode_inference_and_round_trip(platform, source_type, sources, mode):
    req = RunRequest(platform=platform, source_type=source_type, sources=sources)
    assert effective_mode(req) == mode
    assert req.source_type == source_type
    assert RunRequest.model_validate_json(req.model_dump_json()) == req
    assert legacy_agent_compatible(req)
    assert normalize(req)


def test_legacy_defaults_do_not_change_source_semantics():
    old = RunRequest(platform="facebook", source_type="group", sources=["123"])
    new = RunRequest(platform="facebook", mode="group", sources=["123"])
    assert not old.options.latest and new.options.latest
    assert normalize(old)[0].url == "https://www.facebook.com/groups/123"
    assert "sorting_setting=CHRONOLOGICAL" in normalize(new)[0].url
    assert normalize(new)[0].chronological and not normalize(old)[0].chronological
    old_search = RunRequest(platform="linkedin", source_type="search", sources=["Python"])
    new_search = RunRequest(platform="linkedin", mode="recruiting_posts", sources=["Python"])
    assert parse_qs(urlsplit(normalize(old_search)[0].url).query) == {
        "keywords": ["Python"], "sortBy": ['"date_posted"']}
    assert parse_qs(urlsplit(normalize(new_search)[0].url).query)["keywords"] == ["Python hiring"]


@pytest.mark.parametrize("data", [
    {"platform": "facebook", "mode": "jobs"},
    {"platform": "linkedin", "mode": "subreddit"},
    {"platform": "reddit", "mode": "feed"},
    {"platform": "x", "mode": "account", "options": {"sort": "new"}},
    {"platform": "facebook", "mode": "feed", "options": {"latest": True}},
    {"platform": "facebook", "mode": "group", "options": {"sort": "new"}},
    {"platform": "reddit", "mode": "search", "options": {"sort": "top_week"}},
    {"platform": "reddit", "mode": "subreddit", "options": {"sort": "hot"}},
    {"platform": "linkedin", "mode": "jobs", "options": {"keywords": "Python", "work_modes": ["wfh"]}},
    {"platform": "linkedin", "mode": "jobs", "options": {"keywords": "Python", "posted_within": "year"}},
    {"platform": "linkedin", "mode": "jobs", "options": {"keywords": " "}},
    {"platform": "linkedin", "mode": "jobs", "options": {}},
    {"platform": "facebook", "mode": "group", "options": []},
    {"platform": "facebook", "source_type": "invalid"},
    {"platform": ["facebook"]},
    {"platform": "facebook", "mode": {}},
    {"platform": "facebook", "source_type": []},
    {"platform": "facebook", "mode": "group", "options": {"latest": "true"}},
])
def test_closed_mode_options(data):
    with pytest.raises(ValidationError):
        RunRequest(**data)


@pytest.mark.parametrize("platform,mode,source", [
    ("facebook", "group", "https://evil.example/groups/123"),
    ("facebook", "page", "https://facebook.com.evil.example/page"),
    ("facebook", "page", "https://user:secret@facebook.com/page"),
    ("facebook", "group", "https://facebook.com:8765/groups/123"),
    ("facebook", "page", "file:///etc/passwd"),
    ("facebook", "page", "//facebook.com/page"),
    ("facebook", "page", "https://facebook.com/groups/123"),
    ("facebook", "page", "https://facebook.com/login"),
    ("facebook", "page", "https://facebook.com/profile.php?id=abc"),
    ("facebook", "page", "https://facebook.com/profile.php?id=12&id=34"),
    ("facebook", "group", "https://facebook.com/groups/123/posts/456"),
    ("facebook", "group", "https://facebook.com/groups/%2e%2e"),
    ("facebook", "search", "https://evil.example/groups/123 | python"),
    ("reddit", "subreddit", "https://evil.example/r/forhire"),
    ("reddit", "subreddit", "https://reddit.com/user/someone"),
    ("linkedin", "legacy_group", "https://evil.example/groups/123"),
    ("x", "account", "https://x.com/search?q=test"),
    ("x", "list", "https://x.com/user/status/123"),
    ("x", "account", "javascript:alert(1)"),
])
def test_source_hosts_and_paths_are_rejected(platform, mode, source):
    with pytest.raises(ValueError):
        normalize(RunRequest(platform=platform, mode=mode, sources=[source]))


def test_jobs_query_is_encoded_one_target_and_legacy_projection():
    req = RunRequest(platform="linkedin", mode="jobs", sources=["ignored", "also ignored"],
                     count=25, options={"keywords": "C++ & Python", "location": "Hồ Chí Minh",
                                        "work_modes": ["remote", "hybrid"], "posted_within": "day"})
    assert req.sources == ["C++ & Python"] and req.source_type == "search" and req.job_mode
    before = req.model_dump_json()
    plan = normalize(req)
    assert len(plan) == 1 and plan[0].per_target_count == 25 and plan[0].chronological
    params = parse_qs(urlsplit(plan[0].url).query)
    assert params["keywords"] == ["C++ & Python"] and params["location"] == ["Hồ Chí Minh"]
    assert params["f_WT"] == ["2,3"] and params["f_TPR"] == ["r86400"]
    assert req.model_dump_json() == before
    assert total_target(req) == 25 and not legacy_agent_compatible(req)


def test_facebook_page_profile_id_and_slug_drop_tracking():
    req = RunRequest(platform="facebook", mode="page", sources=[
        "https://www.facebook.com/profile.php?id=123&__cft__=private", "SomePage"])
    assert [t.url for t in normalize(req)] == [
        "https://www.facebook.com/profile.php?id=123", "https://www.facebook.com/SomePage/"]
    assert all(t.chronological for t in normalize(req))


@pytest.mark.parametrize("sort,suffix,chronological", [
    ("new", "/new/", True), ("top_day", "/top/?t=day", False),
    ("top_week", "/top/?t=week", False),
])
def test_reddit_sort_is_explicit(sort, suffix, chronological):
    req = RunRequest(platform="reddit", mode="subreddit", sources=["r/forhire"], options={"sort": sort})
    assert normalize(req)[0].url.endswith(suffix)
    assert normalize(req)[0].chronological is chronological
    assert legacy_agent_compatible(req) is (sort == "new")


def test_target_dedupe_platform_and_global_caps():
    req = RunRequest(platform="facebook", mode="group", count=40, sources=["a", "b", "a"])
    assert [p.per_target_count for p in normalize(req)] == [40, 40]
    assert total_target(req) == 80 and total_target(req, max_posts=60) == 60
    reddit = RunRequest(platform="reddit", mode="subreddit", count=40, sources=["a", "b", "c", "d"])
    assert [p.per_target_count for p in normalize(reddit)] == [40, 40, 20]
    x = RunRequest(platform="x", mode="search", count=40, sources=["a & b", "a & b", "c"])
    assert [p.per_target_count for p in normalize(x)] == [40, 20]
    assert parse_qs(urlsplit(normalize(x)[0].url).query)["q"] == ["a & b"]
    assert not legacy_agent_compatible(reddit)
    assert not legacy_agent_compatible(x)


def test_empty_sources_and_model_copy_are_validated_at_plan_time():
    with pytest.raises(ValueError):
        normalize(RunRequest(platform="facebook", mode="page"))
    req = RunRequest(platform="facebook")
    with pytest.raises(ValueError):
        normalize(req.model_copy(update={"mode": "jobs"}))


def test_fingerprint_legacy_unchanged_and_jobs_have_stable_ids():
    p = RawPost(platform="facebook", source="s", text=" Hello   WORLD ")
    assert p.fingerprint == hashlib.sha1(b"facebook|hello world").hexdigest()
    seed = JobSeed(job_id="123", title="Python", company="Acme")
    a = RawPost(platform="linkedin", source="query-a", text="First", job_seed=seed)
    b = RawPost(platform="linkedin", source="query-b", text="Updated description", job_seed=seed)
    assert a.fingerprint == b.fingerprint
    assert a.fingerprint != b.model_copy(update={"job_seed": JobSeed(job_id="456")}).fingerprint
    assert RawPost.model_validate_json(a.model_dump_json()) == a
    no_id = RawPost(platform="linkedin", source="s", text="Hello", job_seed=JobSeed(title="Hello"))
    assert no_id.fingerprint == RawPost(platform="linkedin", source="s", text="Hello").fingerprint


@pytest.mark.parametrize("save_method", ["save_batch", "save_posts"])
def test_job_seed_survives_repository_round_trip_and_checkpoint(tmp_path, save_method):
    db = Database(f"sqlite:///{tmp_path / 'seed.db'}")
    req = RunRequest(platform="linkedin", mode="jobs", options={"keywords": "Python"})
    rid = db.create_run(req)
    seed = JobSeed(title="Python", company="Acme", job_id="123", url="https://www.linkedin.com/jobs/view/123/")
    p = AnalyzedPost(platform="linkedin", source="Python", text="Description", job_seed=seed,
                     category="job", job=JobInfo(title="Python"))
    getattr(db, save_method)(rid, [p])
    loaded = db.get_posts(rid)[0]
    assert loaded.job_seed == seed and loaded.fingerprint == p.fingerprint
    assert db.get_raw_posts(rid)[0].job_seed == seed
    assert db.known_fingerprints("linkedin") == {p.fingerprint}
    db.save_batch(rid, [loaded])
    assert len(db.get_posts(rid)) == 1
    assert db.get_analysis_posts(rid)[0].fingerprint == loaded.fingerprint


def test_legacy_raw_and_stored_request_are_not_migrated_on_read(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'legacy.db'}")
    rid = db.create_run(RunRequest(platform="facebook"))
    legacy = {"platform": "facebook", "source_type": "group", "sources": ["123"]}
    with db.Session.begin() as s:
        row = s.get(RunRow, rid)
        row.request = legacy
        row.raw_posts = [{"platform": "facebook", "source": "123", "text": "Old post"}]
    req = RunRequest(**db.get_run(rid)["request"])
    assert req.mode == "group" and not req.options.latest
    assert db.get_raw_posts(rid)[0].job_seed is None
    assert db.get_raw_posts(rid)[0].sponsored is False
    assert db.get_run(rid)["request"] == legacy


def test_old_agent_skips_new_modes_without_blocking_legacy_or_other_users(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'queue.db'}")
    user_id = db.local_user_id()
    modern = db.create_run(RunRequest(platform="facebook", mode="page", sources=["example"]), user_id, status="pending")
    old = db.create_run(RunRequest(platform="facebook"), user_id, status="pending")
    assert db.claim_next_pending(user_id)["id"] == old
    assert db.get_run(modern)["status"] == "pending"
    assert db.claim_next_pending(user_id) is None
    assert db.claim_next_pending(user_id + 1, protocol_version=2) is None
    assert db.claim_next_pending(user_id, protocol_version=2)["id"] == modern
