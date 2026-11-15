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


def test_search_applies_salary_location_match_type_and_validates_dates(cloud):
    client = cloud(); headers = _signup(client, "job-search@example.test")
    db = api.db(); user = db.get_user_by_email("job-search@example.test")
    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [AnalyzedPost(platform="facebook", source="feed", text=f"React salary {i}", category="job", job=JobInfo(title="React", salary=salary, location="Hà Nội", work_mode="远程", match_type="primary")) for i,salary in enumerate(["35-45M VND", "25 triệu/tháng", "2000 USD", "35M VND annually", "35000000USD", "9" * 500 + "M VND"])])
    result = client.get("/api/search?min_salary_vnd=30000000&locations=Hanoi&match_type=primary&work_modes=remote", headers=headers).json()
    assert result["total"] == 1
    assert result["posts"][0]["job"]["salary"] == "35-45M VND"
    assert client.get("/api/search?min_score=101", headers=headers).status_code == 422
    assert client.get("/api/search?date_from=2026-12-01&date_to=2026-01-01", headers=headers).status_code == 422


def test_fts_keeps_owned_ids_in_sql_and_pagination_counts_all_matches(cloud):
    from sqlalchemy import event
    client = cloud(); headers = _signup(client, "sql-search@example.test")
    db = api.db(); user = db.get_user_by_email("sql-search@example.test")
    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [AnalyzedPost(platform="facebook", source="feed", text=f"React test-{i}") for i in range(6)])
    statements = []
    def capture(_conn, _cursor, statement, parameters, _context, _many):
        if "posts_fts MATCH" in statement: statements.append(statement)
    event.listen(db.engine, "before_cursor_execute", capture)
    try:
        posts, total = db.search_posts(user.id, q="React", limit=2, offset=2)
        assert total == 6 and len(posts) == 2
        assert [p["id"] for p in posts] == sorted([p.id for p in db.get_posts(run)], reverse=True)[2:4]
        assert statements and all("r.user_id" in statement for statement in statements)
    finally: event.remove(db.engine, "before_cursor_execute", capture)


def test_ask_edited_filters_skip_parser_and_provider_errors_are_codes(cloud, monkeypatch):
    client = cloud(); headers = _signup(client, "edited-ask@example.test")
    db = api.db(); user = db.get_user_by_email("edited-ask@example.test")
    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [AnalyzedPost(platform="facebook", source="feed", text="React sample", summary="React")])
    post = db.get_posts(run)[0]
    llm, calls = fake_llm(lambda prompt, schema: {"answer": f"React [#{post.id}]"})
    monkeypatch.setattr(search_api, "get_analyzer", lambda *a, **k: llm)
    monkeypatch.setattr(search_api, "resolve_provider_key", lambda *a, **k: "gemini")
    response = client.post("/api/ask", headers=headers, json={"question": "React?", "filters": {"q": "React"}})
    assert response.status_code == 200 and response.json()["applied_filters"]["q"] == "React"
    assert len(calls) == 1 and "query_terms" not in calls[0][2]["properties"]
    def fail(*args, **kwargs): raise RuntimeError("429 quota; secret=DO_NOT_EXPOSE")
    llm.provider.complete_json = fail
    failed = client.post("/api/ask", headers=headers, json={"question": "React?"})
    assert failed.status_code == 502 and failed.json()["code"] == "error.ai_quota"
    assert "DO_NOT_EXPOSE" not in failed.text


def test_unknown_ai_topic_does_not_broaden_search_and_snippet_markers_do_not_nest(cloud, monkeypatch):
    from feedlens.db.repository import _make_snippet
    snippet = _make_snippet("ReactJS and React", "", ["React", "ReactJS"])
    assert "««" not in snippet and "«ReactJS»" in snippet
    client = cloud(); headers = _signup(client, "invalid-topic-ask@example.test")
    llm, calls = fake_llm(lambda prompt, schema: {"topics": ["Not my topic"]})
    monkeypatch.setattr(search_api, "get_analyzer", lambda *a, **k: llm)
    monkeypatch.setattr(search_api, "resolve_provider_key", lambda *a, **k: "gemini")
    response = client.post("/api/ask", headers=headers, json={"question": "Topic?"})
    assert response.status_code == 502 and response.json()["code"] == "error.ask_filters_invalid"
    assert len(calls) == 1


def test_chinese_substring_search_uses_like_when_unicode61_cannot_segment(cloud):
    client = cloud(); headers = _signup(client, "chinese-search@example.test")
    db = api.db(); user = db.get_user_by_email("chinese-search@example.test")
    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [AnalyzedPost(platform="facebook", source="feed", text="招聘支持远程工作的开发人员")])
    result = client.get("/api/search", params={"q": "远程"}, headers=headers).json()
    assert result["total"] == 1 and "«远程»" in result["posts"][0]["snippet"]


def test_fts_repairs_old_row_ids_and_metadata_updates_do_not_reindex(cloud):
    from sqlalchemy import text
    client = cloud(); headers = _signup(client, "fts-migrate@example.test")
    db = api.db(); user = db.get_user_by_email("fts-migrate@example.test")
    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [AnalyzedPost(platform="facebook", source="feed", text="React repair")])
    post = db.get_posts(run)[0]
    with db.engine.begin() as conn:
        conn.execute(text("CREATE VIRTUAL TABLE posts_fts USING fts5(post_id UNINDEXED, text, summary, author, source)"))
        conn.execute(text("INSERT INTO posts_fts(rowid,post_id,text) VALUES(9000,:post_id,'React repair')"), {"post_id": post.id})
    assert db.init_search_index()
    with db.engine.begin() as conn:
        assert conn.execute(text("SELECT rowid FROM posts_fts")).scalar() == post.id
        before = conn.execute(text("SELECT total_changes()")).scalar()
        conn.execute(text("UPDATE posts SET topic_reason='metadata only' WHERE id=:id"), {"id": post.id})
        assert conn.execute(text("SELECT total_changes()")).scalar() - before == 1
    assert client.get("/api/search?q=React", headers=headers).json()["total"] == 1


def test_symbol_search_is_literal_instead_of_match_all(cloud):
    client = cloud(); headers = _signup(client, "symbol-search@example.test")
    db = api.db(); user = db.get_user_by_email("symbol-search@example.test")
    run = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run, [AnalyzedPost(platform="facebook", source="feed", text="100% remote"), AnalyzedPost(platform="facebook", source="feed", text="ordinary post notgithub.com/spam")])
    result = client.get("/api/search", params={"q": "%"}, headers=headers).json()
    assert result["total"] == 1 and result["posts"][0]["text"] == "100% remote"
    assert client.get("/api/search?has_github=true", headers=headers).json()["total"] == 0
