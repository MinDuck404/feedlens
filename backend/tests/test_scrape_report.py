from types import SimpleNamespace

from feedlens import pipeline
from feedlens.db import Database
from feedlens.models import AnalyzedPost, RawPost, RunRequest


def make_db(tmp_path):
    return Database(f"sqlite:///{(tmp_path / 't.db').as_posix()}")


def test_sponsored_flag_survives_analysis_and_old_runs_default_false(tmp_path):
    db = make_db(tmp_path)
    run = db.create_run(RunRequest(platform="facebook"))
    ad = RawPost(platform="facebook", source="Feed", text="Sponsored product launch post body", sponsored=True)
    normal = RawPost(platform="facebook", source="Feed", text="A friend shares a long story today")
    db.save_raw_posts(run, [ad, normal])
    db.save_batch(run, [AnalyzedPost(**p.model_dump(), category="other") for p in (ad, normal)])
    flags = {p.text: p.sponsored for p in db.get_posts(run)}
    assert flags == {ad.text: True, normal.text: False}

    legacy = db.create_run(RunRequest(platform="facebook"))
    db.update_run(legacy, raw_posts=[{"platform": "facebook", "source": "Feed", "text": normal.text}])
    db.save_batch(legacy, [AnalyzedPost(**normal.model_dump(exclude={"sponsored"}), category="other")])
    assert [p.sponsored for p in db.get_posts(legacy)] == [False]


def test_save_scrape_report_keeps_request_and_writes_local_samples(tmp_path, monkeypatch):
    db = make_db(tmp_path)
    req = RunRequest(platform="facebook", count=20)
    run = db.create_run(req)
    monkeypatch.setattr(pipeline, "settings", SimpleNamespace(data_dir=tmp_path))
    pipeline.save_scrape_report(db, run, req, {
        "sources": [{"label": "Feed", "target": 20, "collected": 14, "skipped_old": 23, "examined": 37,
                     "stop_reason": "budget_exhausted"}],
        "missing_link_samples": ["<div>a</div>", "<div>b</div>"]})
    saved = db.get_run(run)["request"]
    assert saved["count"] == 20
    assert saved["scrape_report"]["skipped_old"] == 23 and saved["scrape_report"]["stop_reason"] == "budget_exhausted"
    html = (tmp_path / "debug" / "missing-links" / f"run-{run}.html").read_text(encoding="utf-8")
    assert "<div>a</div>" in html and "<div>b</div>" in html
    assert RunRequest(**saved).count == 20  # extra key does not break re-reading the request


def test_empty_report_changes_nothing(tmp_path):
    db = make_db(tmp_path)
    req = RunRequest(platform="facebook")
    run = db.create_run(req)
    pipeline.save_scrape_report(db, run, req, {})
    assert "scrape_report" not in db.get_run(run)["request"]
