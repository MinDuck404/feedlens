"""Thời gian từng giai đoạn của lượt: lướt (scrapers.py ghi chi tiết), AI phân tích, tóm tắt."""
import pytest

from feedlens import pipeline
from feedlens.analyzer import HeuristicAnalyzer
from feedlens.db.repository import Database
from feedlens.models import RawPost, RunRequest


@pytest.fixture
def db(tmp_path):
    return Database(f"sqlite:///{(tmp_path / 't.db').as_posix()}")

POSTS = [RawPost(platform="facebook", source="g", author="A", text="Tuyển Python Developer Hà Nội lương 25tr"),
         RawPost(platform="facebook", source="g", author="B", text="Bán laptop Dell cũ giá 8 triệu")]


def timings(db, run_id):
    return db.get_run(run_id)["request"]["scrape_report"]["timings"]


def test_local_run_records_scrape_analysis_and_summary(db, monkeypatch):
    def fake_scrape(req, seen, progress, report):
        report["timings"] = {"navigation": 1.5, "expand": 0.25}  # do scrapers.py ghi
        report["full_text_from_story"] = 3
        report["sources"] = [{"label": "g", "target": 2, "collected": 2, "skipped_old": 0, "stop_reason": "target_reached"}]
        return POSTS

    monkeypatch.setattr(pipeline, "scrape", fake_scrape)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a, **k: HeuristicAnalyzer())
    req = RunRequest(platform="facebook", source_type="group", sources=["https://www.facebook.com/groups/g"], count=2)
    run_id = db.create_run(req)
    pipeline.execute_run(db, run_id, req)

    run = db.get_run(run_id)
    assert run["status"] == "done"
    t = timings(db, run_id)
    assert t["navigation"] == 1.5 and t["expand"] == 0.25  # không bị ghi đè
    assert t["scrape_total"] >= 0 and t["analysis"] >= 0 and t["summary"] >= 0
    assert run["request"]["scrape_report"]["full_text_from_story"] == 3


def test_ingested_run_gets_analysis_timings_without_scrape_report(db):
    req = RunRequest(platform="facebook")
    run_id = db.create_run(req)
    pipeline._analyze(db, run_id, req, POSTS, HeuristicAnalyzer(), lambda phase: (lambda n, m: None))
    t = timings(db, run_id)
    assert set(t) >= {"analysis", "summary"} and "scrape_total" not in t


def test_continue_analysis_adds_to_previous_time(db):
    req = RunRequest(platform="facebook")
    run_id = db.create_run(req)
    pipeline.add_timings(db, run_id, analysis=10.0, summary=1.0)
    pipeline.add_timings(db, run_id, analysis=5.0)
    t = timings(db, run_id)
    assert t["analysis"] == 15.0 and t["summary"] == 1.0


def test_collect_all_hands_the_report_to_the_scraper(monkeypatch):
    seen_reports = []

    class FakeScraper:
        last_report = {"target": 1, "collected": 1, "skipped_old": 0, "stop_reason": "target_reached"}

        def collect(self, page, url, label, target, seen, progress, report=None, **kwargs):
            seen_reports.append(report)
            report.setdefault("timings", {})["navigation"] = 2.0
            return POSTS[:1]

    monkeypatch.setitem(pipeline.SCRAPERS, "facebook", FakeScraper)
    req = RunRequest(platform="facebook", source_type="group", sources=["https://www.facebook.com/groups/g"], count=1)
    report: dict = {}
    pipeline.collect_all(type("Page", (), {"is_closed": lambda self: False})(), req, set(), lambda n, m: None, False, report=report)
    assert seen_reports == [report] and report["timings"]["navigation"] == 2.0
