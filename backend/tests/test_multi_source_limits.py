from feedlens.db.repository import Database
from feedlens.core.models import AnalyzedPost
from feedlens.core.models import JobSeed
from feedlens.core.models import RawPost
from feedlens.core.models import RunRequest
from feedlens.runs.source_modes import SourceTarget
from feedlens.runs.source_modes import allocate_targets
from feedlens.runs.source_modes import normalize
from feedlens.runs.source_modes import total_target


def test_thirteen_groups_share_the_five_hundred_post_cap():
    req = RunRequest(platform="facebook", mode="group", sources=[f"group{i}" for i in range(13)], count=120)
    plan = normalize(req)
    assert [target.per_target_count for target in plan] == [39] * 6 + [38] * 7
    assert total_target(req, max_posts=500) == 500


def test_small_source_keeps_its_request_and_surplus_goes_to_large_source():
    plan = allocate_targets([SourceTarget("small", "one", False, 10),
                             SourceTarget("large", "two", False, 600)], 500)
    assert [target.per_target_count for target in plan] == [10, 490]


def test_only_new_counts_raw_posts_waiting_for_analysis(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'only-new.db'}")
    user_id = db.local_user_id()
    req = RunRequest(platform="facebook", only_new=True)
    rid = db.create_run(req, user_id, status="analysis_failed")
    analyzed = RawPost(platform="facebook", source="feed", text="Already analyzed post")
    pending = RawPost(platform="facebook", source="feed", text="Collected but not yet analyzed")
    db.save_raw_posts(rid, [analyzed, pending])
    db.save_batch(rid, [AnalyzedPost(**analyzed.model_dump())])
    assert db.known_fingerprints(req.platform, user_id) == {analyzed.fingerprint, pending.fingerprint}
    assert [p.fingerprint for p in db.get_analysis_posts(rid)] == [analyzed.fingerprint, pending.fingerprint]


def test_raw_seen_posts_are_scoped_and_empty_snapshots_are_safe(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'isolation.db'}")
    owner = db.local_user_id()
    other = db.create_user("other@example.test", "!")
    expected = set()
    for index, (user, platform, status, digest, included) in enumerate([
        (owner, "facebook", "analyzing", {"overall": "partial"}, True),
        (owner, "facebook", "analysis_failed", None, True),
        (owner, "facebook", "done", None, True),
        (owner, "facebook", "error", {}, True),
        (owner, "facebook", "done", {"overall": "complete"}, False),
        (other, "facebook", "analysis_failed", None, False),
        (owner, "linkedin", "analysis_failed", None, False),
        (None, "facebook", "analysis_failed", None, False),
    ]):
        req = RunRequest(platform=platform)
        rid = db.create_run(req, user, status=status)
        post = RawPost(platform=platform, source="feed", text=f"Distinct raw post {index}")
        db.save_raw_posts(rid, [post])
        db.update_run(rid, digest=digest)
        if included:
            expected.add(post.fingerprint)
    for empty in [None, []]:
        rid = db.create_run(RunRequest(platform="facebook"), owner, status="analysis_failed")
        db.update_run(rid, raw_posts=empty)
    assert db.known_fingerprints("facebook", owner) == expected
    assert not (db.known_fingerprints("facebook") & expected)


def test_raw_job_seed_fingerprint_matches_its_native_job_id(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'jobs.db'}")
    uid = db.local_user_id()
    rid = db.create_run(RunRequest(platform="linkedin"), uid, status="analysis_failed")
    post = RawPost(platform="linkedin", source="jobs", text="Native role", job_seed=JobSeed(job_id="123"))
    db.save_raw_posts(rid, [post])
    assert db.known_fingerprints("linkedin", uid) == {post.fingerprint}


def test_custom_caps_and_small_budgets_preserve_order():
    req = RunRequest(platform="facebook", mode="group", sources=["one", "two", "three"], count=10)
    assert [t.per_target_count for t in normalize(req, max_posts=5)] == [2, 2, 1]
    assert [t.per_target_count for t in normalize(req, max_posts=2)] == [1, 1, 0]
    assert total_target(req, max_posts=5) == 5
    assert [t.per_target_count for t in normalize(req, max_posts=100)] == [10, 10, 10]


def test_collect_report_and_cloud_agent_use_the_same_fair_plan(monkeypatch):
    from contextlib import contextmanager
    from dataclasses import replace
    from types import SimpleNamespace
    from feedlens.runs import agent
    from feedlens.browser import profiles as browser
    from feedlens.runs import pipeline

    quotas = []
    class Collector:
        def collect(self, page, url, label, target, seen, progress, **kwargs):
            quotas.append(target)
            posts = [RawPost(platform="facebook", source=label, text=f"New post {label}/{i}") for i in range(target)]
            self.last_report = dict(target=target, collected=len(posts), skipped_old=0, stop_reason="target_reached")
            return posts
    monkeypatch.setitem(pipeline.SCRAPERS, "facebook", Collector)
    monkeypatch.setattr(pipeline, "settings", replace(pipeline.settings, max_posts=500))
    req = RunRequest(platform="facebook", mode="group", sources=[f"g{i}" for i in range(13)], count=120)
    report = {}
    posts = pipeline.collect_all(None, req, set(), lambda *a: None, False, report)
    assert quotas == [39] * 6 + [38] * 7 and len(posts) == 500
    assert [s["target"] for s in report["sources"]] == quotas
    quotas.clear()
    @contextmanager
    def fake_profile(*args, **kwargs):
        yield SimpleNamespace(pages=[None])
    monkeypatch.setattr(browser, "open_context", fake_profile)
    uploaded = []
    def post(path, **kwargs):
        uploaded.append(kwargs["json"]["posts"])
        return SimpleNamespace(raise_for_status=lambda: None)
    client = agent.Agent.__new__(agent.Agent)
    client.http = SimpleNamespace(post=post)
    client.handle(14, req)
    assert quotas == [39] * 6 + [38] * 7
    assert len(uploaded[0]) == 500
