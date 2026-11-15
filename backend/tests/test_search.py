import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from feedlens import api, search_api
from feedlens.analyzer import LLMAnalyzer
from feedlens.models import AnalyzedPost, JobInfo, RunRequest
from tests.test_cloud import _signup, cloud  # noqa: F401 — fixture

ROOT = Path(__file__).resolve().parents[2]


def fake_llm(handler):
    calls = []

    def complete(system, prompt, schema, effort="low"):
        calls.append((system, prompt, schema))
        return handler(prompt, schema)

    provider = SimpleNamespace(complete_json=complete, model="fake", info=SimpleNamespace(name="Fake"))
    return LLMAnalyzer(provider), calls


def test_search_user_isolation(cloud):
    client = cloud()
    a, b = _signup(client, "search-a@example.test"), _signup(client, "search-b@example.test")
    db = api.db()
    user_a = db.get_user_by_email("search-a@example.test")
    user_b = db.get_user_by_email("search-b@example.test")

    run_a = db.create_run(RunRequest(platform="facebook"), user_a.id, status="done")
    db.save_batch(run_a, [
        AnalyzedPost(platform="facebook", source="feed", text="React 19 release features", summary="React 19"),
    ])

    run_b = db.create_run(RunRequest(platform="linkedin"), user_b.id, status="done")
    db.save_batch(run_b, [
        AnalyzedPost(platform="linkedin", source="feed", text="React Native tips", summary="React Native"),
    ])

    # User A search "React"
    r_a = client.get("/api/search?q=React", headers=a)
    assert r_a.status_code == 200
    res_a = r_a.json()
    assert res_a["total"] == 1
    assert "React 19" in res_a["posts"][0]["summary"]

    # User B search "React"
    r_b = client.get("/api/search?q=React", headers=b)
    assert r_b.status_code == 200
    res_b = r_b.json()
    assert res_b["total"] == 1
    assert "React Native" in res_b["posts"][0]["summary"]


def test_search_filters_and_fts_vs_like(cloud):
    client = cloud()
    h = _signup(client, "filters@example.test")
    db = api.db()
    user = db.get_user_by_email("filters@example.test")

    # Tạo 1 topic
    t1 = client.post("/api/topics", headers=h, json={"name": "Frontend"}).json()

    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [
        AnalyzedPost(
            platform="facebook", source="feed", text="Tuyển dụng Senior React Engineer remote lương 40M",
            summary="Tuyển React remote", category="job", posted_at="2026-11-10T08:00:00Z",
            job=JobInfo(title="Senior React", company="Acme", location="Hanoi", salary="40M", work_mode="remote",
                        contact="@hr", match_score=85, match_reason="Khớp", match_type="primary", gaps=[], constraint_flags=[]),
            topic_ids=[t1["id"]],
        ),
        AnalyzedPost(
            platform="facebook", source="feed", text="Chia sẻ repo github.com/fastapi/fastapi rất hay",
            summary="Repo FastAPI", category="tech", posted_at="2026-11-12T10:00:00Z",
            url="https://github.com/fastapi/fastapi",
        ),
        AnalyzedPost(
            platform="facebook", source="feed", text="Thảo luận onsite tại TP HCM",
            summary="Thảo luận", category="question", posted_at="2026-11-14T12:00:00Z",
        ),
    ])

    # 1. Test FTS5 search và highlight «…»
    r = client.get("/api/search?q=React", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert "«React»" in data["posts"][0]["snippet"]
    assert data["posts"][0]["run_id"] == run

    # 2. Test Fallback LIKE branch (bằng cách gọi hàm db.search_posts với _use_fts=False)
    posts_like, tot_like = db.search_posts(user.id, q="React", _use_fts=False)
    assert tot_like == 1
    assert "«React»" in posts_like[0]["snippet"]

    # 3. Test lọc category
    r_cat = client.get("/api/search?categories=tech", headers=h)
    assert r_cat.json()["total"] == 1
    assert r_cat.json()["posts"][0]["category"] == "tech"

    # 4. Test lọc date_from, date_to
    r_date = client.get("/api/search?date_from=2026-11-11&date_to=2026-11-13", headers=h)
    assert r_date.json()["total"] == 1
    assert r_date.json()["posts"][0]["summary"] == "Repo FastAPI"

    # 5. Test lọc topic_ids
    r_top = client.get(f"/api/search?topic_ids={t1['id']}", headers=h)
    assert r_top.json()["total"] == 1
    assert r_top.json()["posts"][0]["topic_ids"] == [t1["id"]]

    # 6. Test lọc việc làm: job_only, work_modes, min_score
    r_job = client.get("/api/search?job_only=true&work_modes=remote&min_score=80", headers=h)
    assert r_job.json()["total"] == 1
    r_job_fail = client.get("/api/search?job_only=true&work_modes=onsite", headers=h)
    assert r_job_fail.json()["total"] == 0

    # 7. Test lọc has_github và has_link
    r_gh = client.get("/api/search?has_github=true", headers=h)
    assert r_gh.json()["total"] == 1
    assert r_gh.json()["posts"][0]["summary"] == "Repo FastAPI"
    r_link = client.get("/api/search?has_link=true", headers=h)
    assert r_link.json()["total"] == 1


def test_ask_needs_key_when_offline(cloud):
    client = cloud()
    h = _signup(client, "offline-ask@example.test")
    r = client.post("/api/ask", headers=h, json={"question": "Có việc gì hay?", "language": "vi"})
    assert r.status_code == 400
    assert r.json()["code"] == "error.ask_needs_key"


def test_ask_with_fixtures_and_fake_llm(cloud, monkeypatch):
    client = cloud()
    h = _signup(client, "ask-ai@example.test")
    db = api.db()
    user = db.get_user_by_email("ask-ai@example.test")

    # Tạo post mẫu
    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [
        AnalyzedPost(
            platform="facebook", source="Katalon Cloud", author="HR",
            text="Tuyển Senior Frontend React Engineer remote lương 35-45 triệu",
            summary="Senior React Remote", category="job", posted_at="2026-11-12T10:00:00Z",
            job=JobInfo(title="Senior React", company="Katalon", location="Remote", salary="35M", work_mode="remote",
                        contact="@hr", match_score=90, match_type="primary", gaps=[], constraint_flags=[]),
        ),
    ])
    real_post = db.get_posts(run)[0]

    # Đọc fixture mẫu từ ask-fixtures.json (vi-01)
    fixtures_file = ROOT / ".omc/research/ask-fixtures.json"
    with open(fixtures_file, "r", encoding="utf-8") as f:
        fixtures = json.load(f)
    f0 = fixtures[0]  # ask-vi-01: React remote lương trên 30 triệu

    step_counter = 0

    def mock_llm_handler(prompt, schema):
        nonlocal step_counter
        step_counter += 1
        if "query_terms" in schema.get("properties", {}):
            # Bước 1: Trả về expected_filter từ fixture
            return f0["expected_filter"]
        # Bước 3: Trả về câu trả lời có trích dẫn đúng [#{real_post.id}] và 1 ID bịa [#99999]
        return {
            "answer": f"Katalon đang tuyển Senior Frontend React đáp ứng yêu cầu [#{real_post.id}]. Ngoài ra có job bịa [#{99999}]."
        }

    mock_analyzer, calls = fake_llm(mock_llm_handler)
    monkeypatch.setattr(search_api, "get_analyzer", lambda *a, **k: mock_analyzer)
    monkeypatch.setattr(search_api, "resolve_provider_key", lambda *a, **k: "gemini")

    r = client.post("/api/ask", headers=h, json={"question": f0["question"], "language": "vi"})
    assert r.status_code == 200
    res = r.json()

    # Kiểm tra filters trả về
    assert res["filters"]["query_terms"] == ["React"]
    assert len(res["posts"]) == 1
    assert res["posts"][0]["id"] == real_post.id

    # Kiểm tra trích dẫn: ID có thật được giữ, ID bịa #99999 bị xóa sạch
    assert res["citations"] == [real_post.id]
    assert f"[#{real_post.id}]" in res["answer"]
    assert "[#99999]" not in res["answer"]
    assert len(calls) == 2  # Đúng 2 bước gọi AI


def test_ask_no_posts_found_does_not_call_step3(cloud, monkeypatch):
    client = cloud()
    h = _signup(client, "ask-empty@example.test")

    step_counter = 0

    def mock_llm_handler(prompt, schema):
        nonlocal step_counter
        step_counter += 1
        return {
            "query_terms": ["NonExistentKeywordXYZ"],
            "date_from": None, "date_to": None,
            "categories": [], "topics": [], "job": None,
            "has_link": None, "has_github": None, "limit": 40,
        }

    mock_analyzer, calls = fake_llm(mock_llm_handler)
    monkeypatch.setattr(search_api, "get_analyzer", lambda *a, **k: mock_analyzer)
    monkeypatch.setattr(search_api, "resolve_provider_key", lambda *a, **k: "gemini")

    r = client.post("/api/ask", headers=h, json={"question": "Tìm từ khóa không hề có", "language": "vi"})
    assert r.status_code == 200
    res = r.json()
    assert res["posts"] == []
    assert res["citations"] == []
    assert "Không tìm thấy" in res["answer"]
    # Chỉ gọi đúng 1 bước (bước 1 parser), TUYỆT ĐỐI không gọi bước 3
    assert len(calls) == 1
