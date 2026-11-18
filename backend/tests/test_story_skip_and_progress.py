import dataclasses
import json
from types import SimpleNamespace

import pytest

from feedlens import pipeline, scrapers
from feedlens.analyzer import HeuristicAnalyzer
from feedlens.db import Database
from feedlens.models import RawPost, RunRequest


def test_cross_posted_jobs_do_not_stop_later_group(monkeypatch):
    shared = [f"A cross-posted job advertisement number {i}" for i in range(5)]
    fresh = "A new job only present in the second group"
    monkeypatch.setattr(scrapers, "_human_pause", lambda *args: None)
    monkeypatch.setattr(scrapers.FacebookScraper, "ensure_access", lambda *args: False)
    monkeypatch.setattr(scrapers.FacebookScraper, "_expand", lambda *args: 0)

    def extract(self, page, stories):
        group = "first" if "/first" in page.url else "second"
        texts = shared if group == "first" else [*shared, fresh]
        offset = 1000 if group == "first" else 2000
        return [dict(text=text, author="Recruiter", posted_at="",
                     url=f"https://www.facebook.com/groups/{group}/posts/{offset + i}/")
                for i, text in enumerate(texts)]

    monkeypatch.setattr(scrapers.FacebookScraper, "extract_items", extract)
    page = SimpleNamespace(mouse=SimpleNamespace(wheel=lambda *args: None))
    page.goto = lambda url, **kwargs: setattr(page, "url", url)
    req = RunRequest(platform="facebook", mode="group", source_type="group",
                     sources=["first", "second"], count=5, only_new=True,
                     options={"latest": True, "old_streak": 5})
    report = {}
    posts = pipeline.collect_all(page, req, set(), lambda *args: None, False, report)

    assert [post.text for post in posts] == [*shared, fresh]
    second = report["sources"][1]
    assert second["skipped_old"] == 0
    assert second["skipped_dup"] == 5
    assert second["stop_reason"] != "caught_up"


def test_facebook_scroll_waits_for_new_content_within_existing_pace(monkeypatch):
    now = 0.0
    round_no = 0
    scrolled_at = 0.0

    def advance(seconds):
        nonlocal now
        now += seconds

    def scroll(*args):
        nonlocal round_no, scrolled_at
        round_no += 1
        scrolled_at = now

    # First scroll adds a card quickly, second shows no change and uses the full wait.
    def visible_messages(script):
        return ["old", "new"] if now >= 0.5 and round_no else ["old"]

    monkeypatch.setattr(scrapers.time, "monotonic", lambda: now)
    monkeypatch.setattr(scrapers, "_human_pause", lambda lo, hi: advance((lo + hi) / 2))
    monkeypatch.setattr(scrapers.random, "random", lambda: 1)
    monkeypatch.setattr(scrapers.FacebookScraper, "ensure_access", lambda *args: False)
    monkeypatch.setattr(scrapers.FacebookScraper, "_expand", lambda *args: 0)
    observed = []

    def extract(self, page, stories):
        if round_no:
            observed.append(now - scrolled_at)
        return [dict(text=f"Organic post number {round_no}", author="Author", url="", posted_at="")]

    monkeypatch.setattr(scrapers.FacebookScraper, "extract_items", extract)
    page = SimpleNamespace(goto=lambda *args, **kwargs: None, mouse=SimpleNamespace(wheel=scroll),
                           evaluate=visible_messages, wait_for_timeout=lambda ms: advance(ms / 1000))
    report = {}
    posts = scrapers.FacebookScraper().collect(page, "https://www.facebook.com/", "Feed", 3,
                                              set(), lambda *args: None, report=report)

    assert len(posts) == 3
    assert observed == pytest.approx([0.8, 1.6])
    assert report["timings"]["scroll_ready_wait"] == pytest.approx(0.8)
    assert report["timings"]["scroll_timeout_wait"] == pytest.approx(1.6)
    assert report["timings"]["scroll_wait"] == pytest.approx(2.4)


def test_save_scrape_report_caps_target_at_max_posts_and_records_story_counts(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{(tmp_path / 'cap.db').as_posix()}")
    monkeypatch.setattr(pipeline, "settings", dataclasses.replace(pipeline.settings, max_posts=20))
    req = RunRequest(
        platform="facebook",
        source_type="group",
        sources=["https://www.facebook.com/groups/g1", "https://www.facebook.com/groups/g2", "https://www.facebook.com/groups/g3"],
        count=10,
    )
    rid = db.create_run(req)
    pipeline.save_scrape_report(
        db,
        rid,
        req,
        {
            "sources": [
                {"label": "g1", "target": 7, "collected": 2, "skipped_old": 5, "stop_reason": "caught_up"},
                {"label": "g2", "target": 9, "collected": 9, "skipped_old": 0, "stop_reason": "target_reached"},
                {"label": "g3", "target": 9, "collected": 9, "skipped_old": 0, "stop_reason": "target_reached"},
            ],
            "from_story": 0,
            "full_text_from_story": 0,
        },
    )
    sr = db.get_run(rid)["request"]["scrape_report"]
    assert sr["target"] == 20
    assert sr["collected"] == 20
    assert sr["from_story"] == 0
    assert sr["full_text_from_story"] == 0

    pipeline.save_scrape_report(
        db,
        rid,
        req,
        {
            "sources": [{"label": "g1", "target": 20, "collected": 12, "skipped_old": 0, "stop_reason": "no_more_posts"}],
            "from_story": 12,
            "full_text_from_story": 3,
        },
    )
    sr2 = db.get_run(rid)["request"]["scrape_report"]
    assert sr2["from_story"] == 12
    assert sr2["full_text_from_story"] == 3


def test_story_posts_skip_expand_and_link_resolve(monkeypatch):
    monkeypatch.setattr(scrapers, "_human_pause", lambda *a, **k: None)
    story_text = "Tuyển kỹ sư Python backend tại Hà Nội lương 30 triệu làm việc hybrid cùng team sản phẩm"
    story_payload = json.dumps({
        "data": {
            "node": {
                "__typename": "Story",
                "post_id": "1234567890",
                "url": "https://www.facebook.com/groups/pythondemo/posts/1234567890/",
                "creation_time": 1700000000,
                "actors": [{"name": "Minh Nguyen"}],
                "message": {"text": story_text},
                "comet_sections": {
                    "content": {
                        "story": {
                            "to": {"__typename": "Group", "id": "999", "url": "https://www.facebook.com/groups/pythondemo/"},
                            "message": {"text": story_text},
                        }
                    }
                },
            }
        }
    })

    expand_clicks = []
    locator_calls = []

    class FakeMouse:
        def wheel(self, dx, dy):
            pass

    class FakePage:
        url = "https://www.facebook.com/groups/pythondemo/?sorting_setting=CHRONOLOGICAL"
        mouse = FakeMouse()

        def __init__(self):
            self._listeners = {}

        def on(self, event, fn):
            self._listeners.setdefault(event, []).append(fn)

        def remove_listener(self, event, fn):
            if event in self._listeners and fn in self._listeners[event]:
                self._listeners[event].remove(fn)

        def goto(self, url, **kwargs):
            pass

        def wait_for_timeout(self, ms):
            pass

        def locator(self, selector):
            locator_calls.append(selector)
            raise AssertionError("locator/hover should not be called for Story-sourced posts")

        def evaluate(self, script, arg=None):
            if "script[type=" in script:
                return [story_payload]
            if "document.querySelectorAll('[data-feedlens-expand]')" in script and arg is None:
                return [{"idx": 0, "author": "Minh Nguyen", "text": story_text}]
            if "wanted.has(id)" in script:
                expand_clicks.append(list(arg or []))
                return len(arg or [])
            if "data-feedlens-node" in script and "FB_JS" not in script and "removeAttribute" in script and "const out = []" not in script:
                return None
            if "window.scrollY" in script:
                return 0
            if "window.scrollTo" in script:
                return None
            if "const out = []" in script:
                return [{
                    "author": "Minh Nguyen",
                    "text": story_text,
                    "url": "",
                    "posted_at": "",
                    "sponsored": False,
                    "_node_index": 0,
                    "_node_marker": "0",
                    "_hover": [0],
                    "links": [],
                    "_author_url": "",
                }]
            return []

    page = FakePage()
    scraper = scrapers.FacebookScraper()
    monkeypatch.setattr(scraper, "ensure_access", lambda *a, **k: False)
    report: dict = {}
    posts = scraper.collect(
        page,
        "https://www.facebook.com/groups/pythondemo/?sorting_setting=CHRONOLOGICAL",
        "Python Demo",
        target=1,
        seen=set(),
        progress=lambda *a: None,
        report=report,
    )
    assert len(posts) == 1
    assert posts[0].url == "https://www.facebook.com/groups/pythondemo/posts/1234567890/"
    assert report["from_story"] == 1
    assert report["full_text_from_story"] == 0
    assert locator_calls == []
    assert all(clicks == [] for clicks in expand_clicks)


def test_execute_run_saves_incremental_sources_progress(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{(tmp_path / 'progress.db').as_posix()}")
    monkeypatch.setattr(pipeline, "settings", dataclasses.replace(pipeline.settings, max_posts=30))
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a, **k: HeuristicAnalyzer())
    monkeypatch.setattr(pipeline, "open_context", None, raising=False)

    class FakeScraper:
        def urls(self, source_type, sources):
            return [("Group 1", "https://www.facebook.com/groups/g1"), ("Group 2", "https://www.facebook.com/groups/g2")]

        def collect(self, page, url, label, target, seen, progress, report=None, **kwargs):
            count = 15 if "g1" in url else 5
            posts = []
            self.last_report = {
                "target": target,
                "collected": 0,
                "skipped_old": 0,
                "skipped_ads": 0,
                "examined": 0,
                "stop_reason": None,
            }
            for i in range(count):
                posts.append(RawPost(platform="facebook", source=label, text=f"{label} post number {i} with enough length"))
                self.last_report["collected"] = i + 1
                self.last_report["examined"] = i + 1
                progress(i + 1, f"{i + 1}/{target}")
            self.last_report["stop_reason"] = "target_reached" if count >= target else "caught_up"
            return posts

    monkeypatch.setitem(pipeline.SCRAPERS, "facebook", FakeScraper)

    from contextlib import contextmanager
    from feedlens import browser

    @contextmanager
    def fake_context(*args, **kwargs):
        yield SimpleNamespace(pages=[SimpleNamespace(is_closed=lambda: False)])

    monkeypatch.setattr(browser, "open_context", fake_context)

    snapshots = []
    orig_update_run = db.update_run

    def spy_update_run(run_id, **fields):
        orig_update_run(run_id, **fields)
        req_field = fields.get("request")
        if isinstance(req_field, dict) and "scrape_report" in req_field:
            snapshots.append(json.loads(json.dumps(req_field["scrape_report"])))

    monkeypatch.setattr(db, "update_run", spy_update_run)

    req = RunRequest(
        platform="facebook",
        source_type="group",
        sources=["https://www.facebook.com/groups/g1", "https://www.facebook.com/groups/g2"],
        count=15,
    )
    run_id = db.create_run(req)
    pipeline.execute_run(db, run_id, req)

    # First snapshot when Group 1 starts: Group 1 running, Group 2 pending
    assert len(snapshots) >= 4
    first_sources = snapshots[0]["sources"]
    assert first_sources[0]["status"] == "running" and first_sources[0]["stop_reason"] is None
    assert first_sources[1]["status"] == "pending" and first_sources[1]["stop_reason"] is None

    # Intermediate flush around ~10 posts during Group 1
    mid_g1 = [s for s in snapshots if s["sources"][0]["status"] == "running" and s["sources"][0]["collected"] >= 10]
    assert mid_g1, "Expected incremental flush around 10 posts while Group 1 is running"
    assert mid_g1[0]["sources"][0]["stop_reason"] is None

    # Final snapshot: both groups done with preserved fields
    final_sources = snapshots[-1]["sources"]
    assert final_sources[0]["status"] == "done" and final_sources[0]["collected"] == 15
    assert final_sources[0]["stop_reason"] == "target_reached"
    assert final_sources[1]["status"] == "done" and final_sources[1]["collected"] == 5
    assert final_sources[1]["stop_reason"] == "caught_up"
