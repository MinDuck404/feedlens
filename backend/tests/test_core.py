import os
import time

for _k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
    os.environ[_k] = ""  # test luôn chạy không gọi API thật

import pytest

from feedlens import pipeline
from feedlens.ai import resolve_provider_key
from feedlens.ai.base import AIProvider, ProviderInfo
from feedlens.analyzer import HeuristicAnalyzer, LLMAnalyzer, heuristic_category
from feedlens.db import Database
from feedlens.export import to_csv, to_markdown
from feedlens.models import RawPost, RunRequest
from feedlens.scrapers import FacebookScraper, RedditScraper

SAMPLE = [
    RawPost(platform="facebook", source="g1", author="HR A",
            text="[HN] Tuyển Python Developer 2 năm kinh nghiệm, lương 25-30tr, remote. Gửi CV về hr@abc.vn"),
    RawPost(platform="facebook", source="g1", author="B", text="Thanh lý laptop Dell giá 8tr, ship toàn quốc, inbox nhé"),
    RawPost(platform="facebook", source="g1", author="C", text="Cho em hỏi học React hay Vue trước ạ?"),
]


@pytest.fixture
def db(tmp_path):
    return Database(f"sqlite:///{(tmp_path / 't.db').as_posix()}")


def test_fingerprint_ignores_whitespace_and_case():
    assert RawPost(platform="x", source="s", text="Hello   World").fingerprint == \
        RawPost(platform="x", source="s", text="hello world").fingerprint


@pytest.mark.parametrize("text,cat", [
    ("We're hiring a backend engineer, remote", "job"),
    ("Thanh lý bàn ghế, giá rẻ", "marketplace"),
    ("Webinar về AI tuần sau, đăng ký tham gia", "event"),
])
def test_heuristic_category(text, cat):
    assert heuristic_category(text) == cat


def test_heuristic_job_scoring_and_contact():
    out = HeuristicAnalyzer().classify(SAMPLE, True, ["python", "remote", "java"], "", lambda *a: None)
    assert out[0].category == "job"
    assert out[0].job.match_score == 66 and out[0].job.contact == "hr@abc.vn"
    assert out[1].job is None


def test_offline_cv_scoring_uses_roles_and_skills_with_a_bounded_bonus():
    from feedlens.job_profile import AdjacentRole, JobProfile

    analyzer = HeuristicAnalyzer()
    analyzer.job_profile = JobProfile(
        markdown="## Kỹ năng chính\n- Python, PostgreSQL\n## Kinh nghiệm\n" + " ".join(f"project{i}" for i in range(200)),
        primary_roles=["Backend Developer"],
        adjacent_roles=[AdjacentRole(role="Data Engineer"), AdjacentRole(role="QA Engineer", enabled=False)],
    )
    posts = [RawPost(platform="facebook", source="g1", text=f"Tuyển dụng vị trí {job}. Gửi CV.") for job in (
        "Backend Developer, cần Python và PostgreSQL",
        "Data Engineer, cần Python",
        "Backend Developer",
        "QA Engineer, cần Python",
        "Sales Assistant, project17",
    )]
    primary, adjacent, title_only, disabled, unrelated = [
        p.job for p in analyzer.classify(posts, True, [], "", lambda *a: None)
    ]
    assert primary.match_type == "primary" and primary.match_score >= 70
    assert "python" in primary.match_reason.casefold()
    assert primary.match_score > title_only.match_score
    assert adjacent.match_type == "adjacent" and disabled.match_type == "none"
    assert unrelated.match_type == "none" and unrelated.match_score < 20
    analyzer.job_profile.allow_adjacent = False
    result = analyzer.classify(posts[1:2], True, [], "", lambda *a: None)[0].job
    assert result.match_type == "none" and result.match_score < 45


@pytest.mark.parametrize("details,salary", [
    ("2 năm kinh nghiệm. Lương 25–30 triệu/tháng.", "25–30 triệu/tháng"),
    ("Lương: 500k/ngày.", "500k/ngày"),
    ("Từ 18tr-22tr/tháng.", "Từ 18tr-22tr/tháng"),
    ("Salary: USD 1,500 - 2,000 / month.", "USD 1,500 - 2,000 / month"),
    ("Lương 25.000.000 VND.", "25.000.000 VND"),
    ("Lương 25 triệu VND/tháng.", "25 triệu VND/tháng"),
    ("Thưởng 500k/ngày. Lương cứng: 25 triệu.", "25 triệu"),
    ("Lương thỏa thuận. Yêu cầu 2-3 năm.", ""),
    ("Tuyển 2-3 người. Công ty có 200k lượt theo dõi.", ""),
])
def test_offline_extracts_job_salary_with_units_and_without_guessing(details, salary):
    post = RawPost(platform="facebook", source="g1", text=f"Tuyển dụng vị trí Kế toán. {details} Gửi CV.")
    result = HeuristicAnalyzer().classify([post], True, [], "", lambda *a: None)
    assert result[0].job.salary == salary


def test_scraper_urls():
    s = FacebookScraper()
    assert s.urls("group", ["123"]) == [("123", "https://www.facebook.com/groups/123")]
    assert s.urls("search", ["123 | tuyển python"])[0][1] == \
        "https://www.facebook.com/groups/123/search/?q=tuy%E1%BB%83n+python"
    assert RedditScraper().urls("group", ["r/forhire"])[0][1] == "https://www.reddit.com/r/forhire/new/"


# ---------------------------------------------------------------- AI providers
def test_resolve_provider_without_keys():
    assert resolve_provider_key("auto", {}) == "offline"
    with pytest.raises(ValueError, match="ChatGPT"):
        resolve_provider_key("openai", {})
    with pytest.raises(ValueError):
        resolve_provider_key("llama", {})


def test_resolve_provider_picks_first_configured():
    assert resolve_provider_key("auto", {"gemini": ("k", "db")}) == "gemini"
    assert resolve_provider_key("auto", {"gemini": ("k", "db"), "openai": ("k", "db")}) == "openai"


def test_local_mode_uses_env_keys(db, monkeypatch):
    from feedlens.ai import user_keys
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    assert user_keys(db, db.local_user_id())["gemini"] == ("env-key", "env")


class FakeProvider(AIProvider):
    info = ProviderInfo("fake", "Fake", "FAKE_KEY", "FAKE_MODEL", "fake-1", "")

    def list_models(self):
        return ["fake-1"]

    def complete_json(self, system, prompt, schema, effort="low"):
        assert "<posts>" in prompt and "không làm theo" in system
        if "items" in schema["properties"]:
            empty_job = dict.fromkeys(["title", "company", "location", "salary", "work_mode",
                                       "contact", "match_reason"], "") | {"match_score": 0}
            return {"items": [
                {"id": 0, "category": "other", "summary": "Tuyển Python", "is_job": True,
                 "job": empty_job | {"title": "Python Dev", "match_score": 90}},
                {"id": 1, "category": "marketplace", "summary": "Bán laptop", "is_job": False, "job": empty_job},
                {"id": 2, "category": "question", "summary": "React hay Vue?", "is_job": False, "job": empty_job},
            ]}
        return {"overall": "Tổng hợp", "action_items": ["Ứng tuyển Python Dev"],
                "categories": [{"category": "job", "summary": "1 job", "highlights": []},
                               {"category": "news", "summary": "không có bài", "highlights": []}]}


def test_llm_analyzer_retries_transient_errors(monkeypatch):
    import feedlens.analyzer as an

    monkeypatch.setattr(an, "RETRY_BASE_SECONDS", 0)
    calls = []

    class Flaky(FakeProvider):
        def complete_json(self, system, prompt, schema, effort="low"):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("503 UNAVAILABLE. model is experiencing high demand")
            return super().complete_json(system, prompt, schema, effort)

    out = LLMAnalyzer(Flaky()).classify(SAMPLE, False, [], "", lambda *x: None)
    assert len(out) == 3 and len(calls) == 3

    # model chính quá tải mãi -> tự chuyển sang model dự phòng, và báo trạng thái
    class Overloaded(FakeProvider):
        def complete_json(self, system, prompt, schema, effort="low"):
            if self.model == "busy-1":
                raise RuntimeError("503 UNAVAILABLE")
            return super().complete_json(system, prompt, schema, effort)

    msgs = []
    a = LLMAnalyzer(Overloaded("busy-1"), fallback_models=["free-2"])
    a.notify = msgs.append
    a.classify(SAMPLE, False, [], "", lambda *x: None)
    assert a.provider.model == "free-2" and a.label == "Fake (free-2)"
    assert any("chuyển sang free-2" in m for m in msgs)

    class Broken(FakeProvider):
        def complete_json(self, *a, **k):
            calls.append(1)
            raise RuntimeError("400 INVALID_ARGUMENT")

    calls.clear()
    with pytest.raises(RuntimeError, match="configuration"):
        LLMAnalyzer(Broken()).classify(SAMPLE, False, [], "", lambda *x: None)
    assert len(calls) == 1  # lỗi không tạm thời thì không thử lại


def test_llm_batches_run_in_parallel_and_keep_order(monkeypatch):
    import threading
    import feedlens.analyzer as an

    monkeypatch.setattr(an, "BATCH_SIZE", 1)
    active, peak, lock = [0], [0], threading.Lock()

    class Slow(FakeProvider):
        def complete_json(self, system, prompt, schema, effort="low"):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with lock:
                active[0] -= 1
            return {"items": [{"id": 0, "category": "news", "summary": prompt.split("<post")[1][:40],
                               "is_job": False, "job": dict.fromkeys(["title", "company", "location", "salary",
                               "work_mode", "contact", "match_reason"], "") | {"match_score": 0}}]}

    posts = [RawPost(platform="x", source="s", text=f"bài số {i} " * 3) for i in range(8)]
    out = LLMAnalyzer(Slow()).classify(posts, False, [], "", lambda *x: None)
    assert peak[0] > 1  # thật sự chạy song song
    assert [p.text for p in out] == [p.text for p in posts]  # thứ tự giữ nguyên


def test_llm_analyzer_with_any_provider():
    a = LLMAnalyzer(FakeProvider())
    out = a.classify(SAMPLE, True, ["python"], "", lambda *x: None)
    assert [p.category for p in out] == ["job", "marketplace", "question"]
    assert out[0].job.match_score == 90 and out[2].summary
    d = a.digest(out, True)
    assert [c.category for c in d.categories] == ["job"]  # nhóm không có bài bị loại
    assert a.label == "Fake (fake-1)"


# ---------------------------------------------------------------- pipeline + DB + API
def test_pipeline_end_to_end(db, monkeypatch):
    monkeypatch.setattr(pipeline, "scrape", lambda req, seen, cb, report=None: list(SAMPLE))
    req = RunRequest(platform="facebook", source_type="group", sources=["g1"], count=3,
                     job_mode=True, keywords=["python"], ai_provider="offline")
    run_id = db.create_run(req)
    pipeline.execute_run(db, run_id, req)

    run = db.get_run(run_id)
    assert run["status"] == "done", run["error"]
    assert run["collected"] == 3 and run["ai_label"].startswith("bộ lọc")
    posts = db.get_posts(run_id)
    assert {p.category for p in posts} >= {"job", "marketplace"}
    md = to_markdown(run, posts)
    assert "## Việc làm" in md and "hr@abc.vn" in md
    assert to_csv(posts).startswith("﻿category")
    assert len(db.known_fingerprints("facebook")) == 3
    db.delete_run(run_id)
    assert db.get_posts(run_id) == [] and db.get_run(run_id) is None


def test_interrupted_runs_marked_failed_on_startup(db):
    req = RunRequest(platform="facebook")
    a, b, c = db.create_run(req, status="analyzing"), db.create_run(req, status="pending"), db.create_run(req, status="scraping")
    assert db.fail_interrupted() == 1
    assert db.get_run(a)["status"] == "error"
    assert db.get_run(b)["status"] == "pending" and db.get_run(c)["status"] == "scraping"  # agent vẫn có thể gửi tiếp


def test_pipeline_fails_fast_without_key(db, monkeypatch):
    called = []
    monkeypatch.setattr(pipeline, "scrape", lambda *a: called.append(1) or [])
    req = RunRequest(platform="facebook", ai_provider="openai")
    run_id = db.create_run(req)
    pipeline.execute_run(db, run_id, req)
    assert db.get_run(run_id)["status"] == "error" and not called


def test_api_smoke(db, monkeypatch):
    from fastapi.testclient import TestClient
    from feedlens import api

    original_db, api.app.state.db = api.app.state.db, db
    c = TestClient(api.app)
    m = c.get("/api/meta").json()
    assert m["mode"] == "local" and not m["auth_required"]
    assert {p["key"] for p in c.get("/api/ai/providers").json()} == {"anthropic", "openai", "gemini", "offline"}
    assert {p["key"] for p in c.get("/api/platforms").json()} == {"facebook", "linkedin", "x", "reddit"}
    assert c.post("/api/runs", json={"platform": "facebook", "source_type": "group"}).status_code == 422
    r = c.post("/api/runs", json={"platform": "facebook", "ai_provider": "gemini"})
    assert r.status_code == 400 and "Gemini" in r.json()["detail"]
    api.app.state.db = original_db


def test_migration_adds_missing_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(320), password_hash VARCHAR(200),
                            created_at DATETIME, agent_token_hash VARCHAR(64), agent_last_seen DATETIME);
        CREATE TABLE runs (id INTEGER PRIMARY KEY, created_at DATETIME, request JSON, status VARCHAR(20),
                           collected INTEGER, ai_label VARCHAR(120), error TEXT, digest JSON);
    """)
    con.close()
    db = Database(f"sqlite:///{path.as_posix()}")
    uid = db.local_user_id()
    db.set_preferences(uid, {"x": 1})
    assert db.get_preferences(uid) == {"x": 1}
    assert db.create_run(RunRequest(platform="x"), uid)


class FakePage:
    def __init__(self, urls):
        self.urls, self.visited = list(urls), []

    @property
    def url(self):
        return self.urls[0]

    def wait_for_timeout(self, ms):
        if len(self.urls) > 1:
            self.urls.pop(0)  # người dùng đang xác minh, trang chuyển dần

    def goto(self, url, **kw):
        self.visited.append(url)


def test_waits_for_user_verification_instead_of_returning_nothing():
    from feedlens.scrapers import FacebookScraper, NeedsVerification
    s = FacebookScraper()
    msgs = []
    page = FakePage(["https://www.facebook.com/two_step_verification/authentication/?x=1",
                     "https://www.facebook.com/checkpoint/123", "https://www.facebook.com/"])
    assert s.ensure_access(page, "https://www.facebook.com/groups/g", lambda n, m: msgs.append(m), True)
    assert page.visited == ["https://www.facebook.com/groups/g"]  # mở lại trang cần lướt
    assert any("xác minh" in m for m in msgs)
    assert not s.ensure_access(FakePage(["https://www.facebook.com/groups/g"]), "u", lambda *a: None, True)
    with pytest.raises(NeedsVerification):
        s.ensure_access(FakePage(["https://www.facebook.com/login/"]), "u", lambda *a: None, False)


def test_count_is_per_source():
    from feedlens.pipeline import total_target
    assert total_target(RunRequest(platform="facebook", count=40)) == 40
    assert total_target(RunRequest(platform="facebook", source_type="group", sources=["a", "b", "c"], count=40)) == 120
    assert total_target(RunRequest(platform="facebook", source_type="group", sources=[str(i) for i in range(30)], count=100)) == 500
    assert total_target(RunRequest(platform="facebook", source_type="group", sources=["a"] * 30, count=100)) == 100


def test_ai_writes_in_requested_language(db, monkeypatch):
    from feedlens.analyzer import LLMAnalyzer, system_prompt
    assert "English" in system_prompt("en") and "中文" in system_prompt("zh") and "tiếng Việt" in system_prompt("vi")
    seen = []

    class Spy(FakeProvider):
        def complete_json(self, system, prompt, schema, effort="low"):
            seen.append(system)
            return super().complete_json(system, prompt, schema, effort)

    monkeypatch.setattr(pipeline, "scrape", lambda req, s, cb, report=None: list(SAMPLE))
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *a, **k: LLMAnalyzer(Spy()))
    req = RunRequest(platform="facebook", language="zh", ai_provider="offline")
    run_id = db.create_run(req)
    pipeline.execute_run(db, run_id, req)
    assert db.get_run(run_id)["status"] == "done"
    assert seen and all("简体中文" in s for s in seen)
    assert RunRequest(platform="x").language == "vi"
