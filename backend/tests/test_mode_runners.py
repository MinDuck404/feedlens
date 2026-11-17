from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from feedlens import api, pipeline, scrapers, server_runner
from feedlens.models import JobSeed, RawPost, RunRequest
from feedlens.source_modes import normalize
from tests.test_cloud import cloud, _agent, _signup


@pytest.fixture
def fast_scrape(monkeypatch):
    monkeypatch.setattr(scrapers, "_human_pause", lambda *args: None)
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)
    monkeypatch.setattr(scrapers.Scraper, "ensure_access", lambda *args: False)


def test_plan_is_shared_by_local_and_cookie_runners(monkeypatch):
    from feedlens import browser
    calls = []
    class Fake:
        def collect(self, page, url, label, count, seen, progress, **kwargs):
            calls.append((page, url, count, kwargs["chronological"], kwargs["leading_old_grace"]))
            return [RawPost(platform="facebook", source=label, text="Post from " + label)]
    monkeypatch.setitem(pipeline.SCRAPERS, "facebook", Fake)
    @contextmanager
    def local(*args, **kwargs):
        yield SimpleNamespace(pages=["local-page"])
    @contextmanager
    def cookie(*args, **kwargs):
        yield "cookie-page"
    monkeypatch.setattr(browser, "open_context", local)
    monkeypatch.setattr(server_runner, "cookie_page", cookie)
    req = RunRequest(platform="facebook", mode="group", sources=["123", "456"], count=2)
    pipeline.scrape(req, set(), lambda *a: None)
    server_runner.scrape_with_cookies(req, [], set(), lambda *a: None)
    assert calls[:2] == [("local-page", t.url, 2, True, 0) for t in normalize(req)]
    assert calls[2:] == [("cookie-page", t.url, 2, True, 0) for t in normalize(req)]
    assert pipeline.total_target(req) == 4


def test_plan_quota_after_platform_cap_is_passed_to_collector(monkeypatch):
    quotas = []
    class Fake:
        def collect(self, page, url, label, count, seen, progress, **kwargs):
            quotas.append((count, kwargs["chronological"]))
            return []
    monkeypatch.setitem(pipeline.SCRAPERS, "reddit", Fake)
    req = RunRequest(platform="reddit", mode="subreddit", sources=["a", "b", "c"], count=40)
    pipeline.collect_all(None, req, set(), lambda *a: None, False)
    assert quotas == [(40, True), (40, True), (20, True)]


@pytest.mark.parametrize("chronological,expected", [(True, "caught_up"), (False, "target_reached")])
def test_target_chronology_overrides_url_guess(monkeypatch, fast_scrape, chronological, expected):
    old = [RawPost(platform="facebook", source="s", text=f"Old post number {i}") for i in range(8)]
    fresh = RawPost(platform="facebook", source="s", text="A new post after the old streak")
    monkeypatch.setattr(scrapers, "_facebook_items", lambda p: [p.model_dump(exclude={"platform", "source"}) for p in old + [fresh]])
    page = SimpleNamespace(goto=lambda *a, **k: None, evaluate=lambda *a: None,
                           mouse=SimpleNamespace(wheel=lambda *a: None))
    collector = scrapers.FacebookScraper()
    result = collector.collect(page, "https://www.facebook.com/", "s", 1,
                               {p.fingerprint for p in old}, lambda *a: None, chronological=chronological)
    assert collector.last_report["stop_reason"] == expected
    assert len(result) == (0 if chronological else 1)


def test_facebook_page_pinned_old_posts_have_a_small_grace(monkeypatch, fast_scrape):
    old = [RawPost(platform="facebook", source="s", text=f"Old post number {i}") for i in range(8)]
    fresh = RawPost(platform="facebook", source="s", text="New Page update below pinned posts")
    monkeypatch.setattr(scrapers, "_facebook_items", lambda p: [p.model_dump(exclude={"platform", "source"}) for p in old + [fresh]])
    page = SimpleNamespace(goto=lambda *a, **k: None, evaluate=lambda *a: None,
                           mouse=SimpleNamespace(wheel=lambda *a: None))
    collector = scrapers.FacebookScraper()
    result = collector.collect(page, "https://www.facebook.com/example/", "s", 1,
                               {p.fingerprint for p in old}, lambda *a: None,
                               chronological=True, leading_old_grace=3)
    assert len(result) == 1 and collector.last_report["skipped_old"] == 8


def test_reddit_new_url_fallback_is_chronological():
    assert scrapers.is_chronological_url("https://www.reddit.com/r/forhire/new/")
    assert not scrapers.is_chronological_url("https://www.reddit.com/r/forhire/top/?t=week")


def test_linkedin_jobs_paginate_with_seed_and_common_report(monkeypatch, fast_scrape):
    from feedlens import scrapers_linkedin_jobs as jobs
    class Page:
        def __init__(self):
            self.url = ""
            self.visited = []
        def goto(self, url, **kwargs):
            self.url = url
            self.visited.append(url)
        def evaluate(self, *args):
            return True
    page = Page()
    def extract(p):
        offset = parse_qs(urlsplit(p.url).query).get("start", ["0"])[0]
        seed = JobSeed(title="Python developer", company="Acme", job_id=offset,
                       url=f"https://www.linkedin.com/jobs/view/{offset}/")
        return [{"text": "Python role " + offset, "author": "Acme", "url": seed.url, "job_seed": seed.model_dump()}]
    monkeypatch.setattr(jobs, "extract_job_cards", extract)
    req = RunRequest(platform="linkedin", mode="jobs", count=2, options={"keywords": "Python"})
    report = {}
    result = pipeline.collect_all(page, req, set(), lambda *a: None, False, report)
    assert [p.job_seed.job_id for p in result] == ["0", "25"]
    assert len(page.visited) == 2
    assert report["sources"][0]["stop_reason"] == "target_reached"
    assert report["sources"][0]["collected"] == 2
    assert report["sources"][0]["target"] == 2


def test_linkedin_jobs_empty_pages_stop_without_infinite_paging(monkeypatch, fast_scrape):
    from feedlens import scrapers_linkedin_jobs as jobs
    urls = []
    page = SimpleNamespace(goto=lambda url, **k: urls.append(url), evaluate=lambda *a: True)
    monkeypatch.setattr(jobs, "extract_job_cards", lambda p: [])
    req = RunRequest(platform="linkedin", mode="jobs", options={"keywords": "Python"})
    report = {}
    assert pipeline.collect_all(page, req, set(), lambda *a: None, False, report) == []
    assert len(urls) == 2 and report["sources"][0]["stop_reason"] == "no_more_posts"


def test_linkedin_jobs_only_new_and_time_budget_use_common_loop(monkeypatch, fast_scrape):
    from feedlens import scrapers_linkedin_jobs as jobs
    old = RawPost(platform="linkedin", source="s", text="Old job", job_seed=JobSeed(job_id="123"))
    fresh = RawPost(platform="linkedin", source="s", text="New job", job_seed=JobSeed(job_id="456"))
    monkeypatch.setattr(jobs, "extract_job_cards", lambda p: [p.model_dump(exclude={"platform", "source"}) for p in [old, fresh]])
    page = SimpleNamespace(goto=lambda *a, **k: None, evaluate=lambda *a: True)
    collector = scrapers.LinkedInJobsScraper()
    found = collector.collect(page, jobs.jobs_search_url("Python"), "s", 1,
                              {old.fingerprint}, lambda *a: None, chronological=True)
    assert [p.job_seed.job_id for p in found] == ["456"]
    assert collector.last_report["skipped_old"] == 1
    clock = iter([0, 0, 1000])
    monkeypatch.setattr(scrapers.time, "monotonic", lambda: next(clock, 1000))
    monkeypatch.setattr(jobs, "extract_job_cards", lambda p: [fresh.model_dump(exclude={"platform", "source"})])
    collector.collect(page, jobs.jobs_search_url("Python"), "s", 2, set(), lambda *a: None, chronological=True)
    assert collector.last_report["collected"] == 1
    assert collector.last_report["stop_reason"] == "budget_exhausted"


def test_agent_advertises_protocol_two(monkeypatch):
    from feedlens import agent
    client = agent.Agent.__new__(agent.Agent)
    calls = []
    def get(path, **kwargs):
        calls.append((path, kwargs))
        raise KeyboardInterrupt
    client.http = SimpleNamespace(get=get)
    monkeypatch.setattr(client, "check", lambda: None)
    with pytest.raises(KeyboardInterrupt):
        client.run_forever()
    assert calls == [("/api/agent/next", {"params": {"protocol_version": 2}})]


@pytest.mark.parametrize("arguments,expected", [
    (["facebook", "--type", "group", "--source", "123"], "group"),
    (["linkedin", "--mode", "jobs", "--options", '{"keywords":"Python"}'], "jobs"),
])
def test_cli_retains_type_and_accepts_mode_options(monkeypatch, arguments, expected):
    from feedlens import cli, db
    original = cli._request_from_args
    captured = []
    def capture(args):
        captured.append(original(args))
        raise KeyboardInterrupt
    monkeypatch.setattr(db, "Database", lambda *a: None)
    monkeypatch.setattr(cli, "_request_from_args", capture)
    with pytest.raises(KeyboardInterrupt):
        cli.main(["run", *arguments])
    assert captured[0].mode == expected


def test_cli_demo_still_runs_with_valid_source_plan(monkeypatch, tmp_path):
    from feedlens import cli, db
    database = db.Database(f"sqlite:///{tmp_path / 'demo.db'}")
    monkeypatch.setattr(db, "Database", lambda *a: database)
    monkeypatch.setattr(pipeline, "scrape", pipeline.scrape)  # Restore the demo's temporary override.
    cli.main(["demo"])
    assert database.list_runs()[0]["status"] == "done"


@pytest.mark.parametrize("payload", [
    {"platform": "facebook", "mode": "page", "sources": ["https://evil.example/page"]},
    {"platform": "facebook", "mode": "group", "sources": []},
    {"platform": "linkedin", "mode": "jobs", "options": {"keywords": "Python", "work_modes": ["bad"]}},
    {"platform": "reddit", "mode": "search", "options": {"latest": True}},
])
def test_invalid_run_returns_422_before_queue_or_browser(cloud, monkeypatch, payload):
    client = cloud(); h = _signup(client)
    monkeypatch.setattr(api, "start_run", lambda *a: pytest.fail("Must validate before launch"))
    response = client.post("/api/runs", headers=h, json=payload)
    assert response.status_code == 422 and response.json()["code"] == "error.validation"
    assert client.get("/api/runs", headers=h).json() == []


def test_agent_protocol_negotiation_keeps_old_requests_usable(cloud):
    client = cloud(); h = _signup(client); ag = _agent(client, h)
    jobs = client.post("/api/runs", headers=h, json={"platform": "linkedin", "mode": "jobs",
        "options": {"keywords": "Python"}, "count": 2, "ai_provider": "offline"}).json()["id"]
    page = client.post("/api/runs", headers=h, json={"platform": "facebook", "mode": "page",
        "sources": ["example"], "ai_provider": "offline"}).json()["id"]
    legacy = client.post("/api/runs", headers=h, json={"platform": "facebook", "ai_provider": "offline"}).json()["id"]
    assert client.get("/api/agent/next", headers=ag).json()["job"]["id"] == legacy
    assert client.get("/api/agent/next", headers=ag).json()["job"] is None
    assert client.get("/api/agent/next?protocol_version=2", headers=ag).json()["job"]["id"] == jobs
    assert client.get("/api/agent/next?protocol_version=2", headers=ag).json()["job"]["id"] == page
    assert client.get("/api/agent/next?protocol_version=3", headers=ag).status_code == 422


def test_retry_analysis_keeps_mode_options_and_report(cloud, monkeypatch):
    client = cloud(); h = _signup(client)
    uid = api.db().get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", mode="page", sources=["example"], ai_provider="offline")
    rid = api.db().create_run(req, uid, status="error")
    report = {"target": 2, "collected": 1, "skipped_old": 3, "stop_reason": "no_more_posts"}
    api.db().update_run(rid, request={**req.model_dump(), "scrape_report": report})
    api.db().save_raw_posts(rid, [RawPost(platform="facebook", source="example", text="Saved original post")])
    called = []
    monkeypatch.setattr(api, "start_analysis", lambda db, run_id, request, raw, user_id: called.append(request))
    assert client.post(f"/api/runs/{rid}/analysis", headers=h, json={"ai_provider": "offline"}).status_code == 200
    stored = api.db().get_run(rid)["request"]
    assert stored["mode"] == "page" and stored["options"] == {} and stored["scrape_report"] == report
    assert called[0].mode == "page"
