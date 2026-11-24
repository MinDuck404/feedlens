"""Trần bài mỗi lượt chọn trong Cài đặt (500/1000/2000) và số bài cũ liên tiếp để bỏ qua nhóm."""
import pytest
from pydantic import ValidationError

from feedlens.runs import pipeline
from feedlens.models import RunRequest

GROUPS = [f"https://www.facebook.com/groups/g{i}" for i in range(13)]


def test_run_cap_comes_from_request_then_server_default():
    req = RunRequest(platform="facebook", source_type="group", sources=GROUPS, count=100)
    assert pipeline.run_cap(req) == pipeline.settings.max_posts
    big = req.model_copy(update={"max_posts": 2000})
    assert pipeline.run_cap(big) == 2000
    assert pipeline.total_target(big) == 1300  # 13 × 100, không bị cắt còn 500


def test_run_cap_only_accepts_offered_choices():
    with pytest.raises(ValidationError):
        RunRequest(platform="facebook", max_posts=5000)


def test_group_old_streak_defaults_to_five_and_is_bounded():
    req = RunRequest(platform="facebook", mode="group", sources=GROUPS[:1])
    assert req.options.old_streak == 5
    assert RunRequest(platform="facebook", mode="group", sources=GROUPS[:1], options={"latest": True, "old_streak": 3}).options.old_streak == 3
    with pytest.raises(ValidationError):
        RunRequest(platform="facebook", mode="group", sources=GROUPS[:1], options={"latest": True, "old_streak": 0})


def test_group_old_streak_reaches_the_scraper(monkeypatch):
    got = []

    class FakeScraper:
        last_report = {}

        def collect(self, page, url, label, target, seen, progress, **kwargs):
            got.append(kwargs.get("old_streak_limit"))
            return []

    monkeypatch.setitem(pipeline.SCRAPERS, "facebook", FakeScraper)
    req = RunRequest(platform="facebook", mode="group", sources=GROUPS[:2], options={"latest": True, "old_streak": 3})
    page = type("Page", (), {"is_closed": lambda self: False})()
    pipeline.collect_all(page, req, set(), lambda n, m: None, False, report={})
    assert got == [3, 3]
