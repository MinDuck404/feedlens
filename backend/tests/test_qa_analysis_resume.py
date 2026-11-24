import json
import re
from types import SimpleNamespace

import pytest
from feedlens import api, pipeline
from feedlens.analysis.prompts import CLASSIFY_SCHEMA
from feedlens.analysis.heuristic import HeuristicAnalyzer
from feedlens.analysis.llm import LLMAnalyzer
from feedlens.models import RawPost, RunRequest
from tests.test_cloud import cloud, _signup


class BatchQuotaAI(HeuristicAnalyzer):
    """Giả lập AI phân tích theo từng batch, ném lỗi quota tại batch chỉ định."""

    def __init__(self, label: str = "Mock AI", fail_at_batch: int = -1, batch_size: int = 2):
        self.label = label
        self.fail_at_batch = fail_at_batch
        self.batch_size = batch_size
        self.batch_index = 0
        self.calls = 0
        self.seen: list[list[str]] = []

    def classify(self, posts, job_mode, keywords, profile, progress):
        self.calls += 1
        out = []
        for i in range(0, len(posts), self.batch_size):
            batch = posts[i:i + self.batch_size]
            self.seen.append([p.text for p in batch])
            if self.batch_index == self.fail_at_batch:
                raise RuntimeError("429 quota exceeded: Rate limit or daily allowance reached")
            classified = super().classify(batch, job_mode, keywords, profile, progress)
            for p in classified:
                p.analyzed_by = self.label
            out.extend(classified)
            if getattr(self, "on_batch", None):
                self.on_batch(classified)
            self.batch_index += 1
        return out


# =====================================================================
# 1. Hết hạn mức ở batch đầu, giữa và cuối
# =====================================================================

@pytest.mark.parametrize("fail_at,expected_ai,expected_pending", [
    (0, 0, 6),  # Batch đầu: chưa lưu bài nào
    (1, 2, 4),  # Batch giữa: batch 0 lưu 2 bài, batch 1 lỗi
    (2, 4, 2),  # Batch cuối: batch 0,1 lưu 4 bài, batch 2 lỗi
])
def test_quota_exhausted_at_different_batches(cloud, monkeypatch, fail_at, expected_ai, expected_pending):
    """Kiểm tra hết hạn mức ở batch đầu, giữa, cuối: checkpoint lưu đúng số bài, trạng thái failed, gửi tiếp thành công."""
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    database = api.db()

    req = RunRequest(platform="facebook", ai_provider="openai")
    rid = database.create_run(req, user_id)
    raw = [RawPost(platform="facebook", source="feed", text=f"Bài tuyển dụng Python số {i}") for i in range(6)]
    database.save_raw_posts(rid, raw)

    # Chạy lần đầu với AI gặp lỗi quota ở batch chỉ định
    fake_quota = BatchQuotaAI(label="OpenAI GPT", fail_at_batch=fail_at, batch_size=2)
    monkeypatch.setattr(api, "_check_ai", lambda *args: "openai")
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: fake_quota)
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    monkeypatch.setattr(pipeline, "scrape", lambda *args: pytest.fail("Không được cào web"))

    pipeline.execute_analysis(database, rid, req, raw, user_id)

    detail = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert detail["status"] == "analysis_failed"
    assert detail["can_continue_analysis"] is True
    assert detail["analysis_counts"] == {"ai": expected_ai, "offline": 0, "pending": expected_pending, "total": 6}

    saved_posts = [p for p in database.get_posts(rid) if p.analyzed]
    assert len(saved_posts) == expected_ai
    for p in saved_posts:
        assert p.analyzed_by == "OpenAI GPT"

    # Gửi tiếp với AI đã hồi phục quota
    fake_working = BatchQuotaAI(label="OpenAI GPT", fail_at_batch=-1, batch_size=2)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: fake_working)

    response = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "openai"})
    assert response.status_code == 200

    detail_done = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert detail_done["status"] == "done"
    assert detail_done["can_continue_analysis"] is False
    assert detail_done["analysis_counts"] == {"ai": 6, "offline": 0, "pending": 0, "total": 6}
    assert len(database.get_posts(rid)) == 6


# =====================================================================
# 2. Gửi tiếp hai lần liên tiếp khi vẫn hết hạn mức
# =====================================================================

def test_repeated_continue_while_still_exhausted_maintains_counts_and_labels(cloud, monkeypatch):
    """Gửi tiếp 2 lần liên tiếp khi vẫn hết hạn mức: không lệch count, không mất nhãn AI."""
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    database = api.db()

    req = RunRequest(platform="facebook", ai_provider="openai")
    rid = database.create_run(req, user_id)
    raw = [RawPost(platform="facebook", source="feed", text=f"Bài đăng test {i}") for i in range(6)]
    database.save_raw_posts(rid, raw)

    # Lần đầu: Lưu được batch 0 (2 bài), ném lỗi ở batch 1
    fake_initial = BatchQuotaAI(label="OpenAI GPT", fail_at_batch=1, batch_size=2)
    monkeypatch.setattr(api, "_check_ai", lambda *args: "openai")
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: fake_initial)
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    monkeypatch.setattr(pipeline, "scrape", lambda *args: pytest.fail("Không được cào web"))

    pipeline.execute_analysis(database, rid, req, raw, user_id)
    d1 = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert d1["status"] == "analysis_failed"
    assert d1["analysis_counts"] == {"ai": 2, "offline": 0, "pending": 4, "total": 6}
    assert d1["ai_label"] == "OpenAI GPT"

    # Lần gửi tiếp 1 (vẫn hết quota ngay lập tức):
    fake_still_blocked = BatchQuotaAI(label="OpenAI GPT", fail_at_batch=0, batch_size=2)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: fake_still_blocked)
    resp1 = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "openai"})
    assert resp1.status_code == 200

    d2 = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert d2["status"] == "analysis_failed"
    assert d2["analysis_counts"] == {"ai": 2, "offline": 0, "pending": 4, "total": 6}
    assert d2["ai_label"] == "OpenAI GPT"

    # Lần gửi tiếp 2 (vẫn hết quota):
    resp2 = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "openai"})
    assert resp2.status_code == 200

    d3 = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert d3["status"] == "analysis_failed"
    assert d3["analysis_counts"] == {"ai": 2, "offline": 0, "pending": 4, "total": 6}
    assert d3["ai_label"] == "OpenAI GPT"
    assert sum(p.analyzed for p in database.get_posts(rid)) == 2


# =====================================================================
# 3. Đổi model giữa hai lần gửi tiếp
# =====================================================================

def test_change_model_on_continue_analyzes_remaining_and_merges_label(cloud, monkeypatch):
    """Đổi model giữa 2 lần: chỉ gửi các bài chưa đọc, gộp ai_label và hoàn tất."""
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    database = api.db()

    req = RunRequest(platform="facebook", ai_provider="gemini", ai_model="gemini-2.5-flash")
    rid = database.create_run(req, user_id)
    raw = [RawPost(platform="facebook", source="feed", text=f"Bài IT tuyển dụng {i}") for i in range(4)]
    database.save_raw_posts(rid, raw)

    # Lần 1: Chạy Gemini, phân tích được 2 bài (batch 0) thì hết quota ở batch 1
    gemini_ai = BatchQuotaAI(label="Gemini (gemini-2.5-flash)", fail_at_batch=1, batch_size=2)
    monkeypatch.setattr(api, "_check_ai", lambda *args: "gemini")
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: gemini_ai)
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    monkeypatch.setattr(pipeline, "scrape", lambda *args: pytest.fail("Không được cào web"))

    pipeline.execute_analysis(database, rid, req, raw, user_id)
    d1 = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert d1["status"] == "analysis_failed"
    assert d1["analysis_counts"] == {"ai": 2, "offline": 0, "pending": 2, "total": 4}

    # Lần 2: Người dùng đổi sang OpenAI GPT-4o-mini, xử lý thành công 2 bài còn lại
    openai_ai = BatchQuotaAI(label="OpenAI (gpt-4o-mini)", fail_at_batch=-1, batch_size=2)
    monkeypatch.setattr(api, "_check_ai", lambda *args: "openai")
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: openai_ai)

    response = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "openai", "ai_model": "gpt-4o-mini"})
    assert response.status_code == 200

    d2 = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert d2["status"] == "done"
    assert d2["can_continue_analysis"] is False
    assert d2["analysis_counts"] == {"ai": 4, "offline": 0, "pending": 0, "total": 4}

    saved = database.get_posts(rid)
    assert len(saved) == 4
    assert [p.analyzed_by for p in saved] == [
        "Gemini (gemini-2.5-flash)", "Gemini (gemini-2.5-flash)",
        "OpenAI (gpt-4o-mini)", "OpenAI (gpt-4o-mini)"
    ]
    # ai_label gộp cả hai model
    assert "Gemini (gemini-2.5-flash)" in d2["ai_label"]
    assert "OpenAI (gpt-4o-mini)" in d2["ai_label"]


# =====================================================================
# 4. Bấm gửi khi đang analyzing thì nhận 409
# =====================================================================

def test_retry_analysis_returns_409_when_already_analyzing(cloud):
    """Khi run đang ở status='analyzing', gọi /analysis phải trả về HTTP 409 Conflict."""
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    database = api.db()

    rid = database.create_run(RunRequest(platform="facebook", ai_provider="openai"), user_id, status="analyzing")
    database.save_raw_posts(rid, [RawPost(platform="facebook", source="feed", text="Đang phân tích...")])

    response = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "openai"})
    assert response.status_code == 409


# =====================================================================
# 5. fail_interrupted rồi gửi tiếp
# =====================================================================

def test_fail_interrupted_run_can_be_continued(cloud, monkeypatch):
    """Run bị ngắt do server tắt (status=analyzing) được fail_interrupted chuyển sang analysis_failed và gửi tiếp thành công."""
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    database = api.db()

    rid = database.create_run(RunRequest(platform="facebook", ai_provider="openai"), user_id, status="analyzing")
    raw = [RawPost(platform="facebook", source="feed", text=f"Bài đăng trước khi tắt server {i}") for i in range(3)]
    database.save_raw_posts(rid, raw)

    # Server restart gọi fail_interrupted
    recovered_count = database.fail_interrupted()
    assert recovered_count >= 1

    interrupted_run = database.get_run(rid)
    assert interrupted_run["status"] == "analysis_failed"
    assert "Server khởi động lại" in interrupted_run["error"]

    detail = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert detail["can_continue_analysis"] is True

    # Gửi tiếp sau khi server bật lại
    fake_ai = BatchQuotaAI(label="OpenAI GPT", fail_at_batch=-1, batch_size=3)
    monkeypatch.setattr(api, "_check_ai", lambda *args: "openai")
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: fake_ai)
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    monkeypatch.setattr(pipeline, "scrape", lambda *args: pytest.fail("Không được cào web"))

    response = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "openai"})
    assert response.status_code == 200

    detail_after = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert detail_after["status"] == "done"
    assert detail_after["can_continue_analysis"] is False
    assert detail_after["analysis_counts"] == {"ai": 3, "offline": 0, "pending": 0, "total": 3}


# =====================================================================
# 6. AI trả thiếu item trong batch (analyzer.py ~dòng 326)
# =====================================================================

@pytest.mark.parametrize("initial_reads", [0, 2])
def test_ai_retries_omitted_items_then_finishes_with_retryable_offline_jobs(cloud, monkeypatch, initial_reads):
    """Bài thiếu được gửi lại một lần; bài vẫn thiếu có kết quả offline và được gửi tiếp riêng."""
    client = cloud(); headers = _signup(client)
    user_id = api.db().get_user_by_email("a@x.io").id
    database = api.db()

    req = RunRequest(platform="facebook", ai_provider="openai", job_mode=True, keywords=["Python"])
    rid = database.create_run(req, user_id)
    raw = [RawPost(platform="facebook", source="feed", text=body) for body in (
        "Bài tin tức đã đọc", "Bài sự kiện được đọc ở lần thử lại", "Tuyển Python Developer. Lương 25 triệu/tháng.",
    )]
    database.save_raw_posts(rid, raw)

    calls = []
    read_last = False

    def reply(prompt, schema, effort):
        if schema is not CLASSIFY_SCHEMA:
            return {"overall": "Summary", "categories": [], "action_items": []}
        items = re.findall(r'<post id="(\d+)"[^>]*>\n([^\n]+)', prompt)
        calls.append([body for _, body in items])
        return {"items": [
            {"id": int(i), "category": "news", "summary": f"AI: {body}", "is_job": body == raw[2].text,
             "job": {"title": "Python Developer", "match_score": 82}}
            for i, body in items
            if read_last or (initial_reads and (body == raw[0].text or (body == raw[1].text and len(calls) > 1)))
        ]}

    analyzer = LLMAnalyzer(SimpleNamespace(info=SimpleNamespace(name="OpenAI"), model="test-lite"))
    monkeypatch.setattr(analyzer, "_json_call", reply)
    monkeypatch.setattr(api, "_check_ai", lambda *args: "openai")
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: analyzer)
    monkeypatch.setattr(pipeline, "_spawn", lambda target, run_id, *args: target(*args))
    monkeypatch.setattr(pipeline, "scrape", lambda *args: pytest.fail("Không được cào web"))

    # Lần 1: Chạy phân tích ban đầu
    pipeline.execute_analysis(database, rid, req, raw, user_id)

    detail = client.get(f"/api/runs/{rid}", headers=headers).json()
    retry_index = 1 if initial_reads else 0
    assert calls == [[p.text for p in raw], [p.text for p in raw[retry_index:]]]
    assert detail["status"] == "done" and detail["error"] is None
    assert detail["can_continue_analysis"] is True
    assert detail["can_reanalyze_ai"] is False
    assert detail["analysis_counts"] == {"ai": initial_reads, "offline": 3 - initial_reads, "pending": 0, "total": 3}
    assert (analyzer.label in detail["ai_label"]) == bool(initial_reads)
    assert HeuristicAnalyzer.label in detail["ai_label"]
    initial = detail["posts"]
    assert [p["analyzed_by"] for p in initial] == [analyzer.label] * initial_reads + ["offline"] * (3 - initial_reads)
    assert initial[2]["category"] == "job" and initial[2]["job"]["salary"] == "25 triệu/tháng"
    assert initial[2]["job"]["match_score"] >= 70

    # Lần 2: Gửi tiếp -> chỉ gửi bài chưa có AI đọc (bài số 2)
    read_last = True
    calls.clear()
    response = client.post(f"/api/runs/{rid}/analysis", headers=headers, json={"ai_provider": "openai"})
    assert response.status_code == 200
    assert calls == [[p.text for p in raw[initial_reads:]]]

    detail2 = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert detail2["status"] == "done"
    assert detail2["analysis_counts"] == {"ai": 3, "offline": 0, "pending": 0, "total": 3}
    assert detail2["can_continue_analysis"] is False
    assert detail2["ai_label"] == analyzer.label
    assert detail2["posts"][:initial_reads] == initial[:initial_reads]
    assert detail2["posts"][2]["id"] == initial[2]["id"]
    assert detail2["posts"][2]["job"]["match_score"] == 82


def test_quota_error_on_omitted_item_retry_preserves_successful_items(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    database = api.db()
    user_id = database.get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="openai")
    rid = database.create_run(req, user_id)
    raw = [RawPost(platform="facebook", source="feed", text=text) for text in ("Tin tức", "Tuyển Python Developer")]

    def reply(prompt, schema, effort):
        assert schema is CLASSIFY_SCHEMA
        if f"\n{raw[0].text}\n</post>" in prompt:
            return {"items": [{"id": 0, "category": "news", "summary": "AI summary", "is_job": False}]}
        assert raw[1].text in prompt
        raise RuntimeError("429 quota exceeded")

    analyzer = LLMAnalyzer(SimpleNamespace(info=SimpleNamespace(name="OpenAI"), model="test-lite"))
    monkeypatch.setattr(analyzer, "_json_call", reply)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: analyzer)
    pipeline.execute_analysis(database, rid, req, raw, user_id)

    detail = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert detail["status"] == "analysis_failed" and detail["error_code"] == "error.ai_quota"
    assert detail["analysis_counts"] == {"ai": 1, "offline": 0, "pending": 1, "total": 2}
    assert detail["posts"][0]["summary"] == "AI summary"
    assert detail["can_continue_analysis"] is True


@pytest.mark.parametrize("broken_singleton", [False, True])
def test_truncated_classification_splits_batches_and_keeps_all_posts(cloud, monkeypatch, broken_singleton):
    client = cloud(); headers = _signup(client)
    database = api.db()
    user_id = database.get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook", ai_provider="openai", job_mode=True, keywords=["Python"])
    rid = database.create_run(req, user_id)
    raw = [RawPost(platform="facebook", source="feed", text=f"Tuyển Python Developer vị trí {i}. Lương 25 triệu.")
           for i in range(4)]
    calls = []

    def reply(system, prompt, schema, effort):
        if schema is not CLASSIFY_SCHEMA:
            return {"overall": "Summary", "categories": [], "action_items": []}
        items = re.findall(r'<post id="(\d+)"[^>]*>\n([^\n]+)', prompt)
        posts = [body for _, body in items]
        calls.append(posts)
        if len(posts) > 2 or (broken_singleton and raw[-1].text in posts):
            return json.loads('{"items": [')
        return {"items": [{"id": int(i), "category": "job", "summary": "AI summary", "is_job": True,
                          "job": {"title": "Python Developer", "match_score": 82}} for i, _ in items]}

    provider = SimpleNamespace(info=SimpleNamespace(name="OpenAI"), model="test-lite", complete_json=reply)
    analyzer = LLMAnalyzer(provider)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *args: analyzer)
    pipeline.execute_analysis(database, rid, req, raw, user_id)

    expected = [raw, raw[:2], raw[2:]] + ([raw[2:3], raw[3:]] if broken_singleton else [])
    detail = client.get(f"/api/runs/{rid}", headers=headers).json()
    assert calls == [[p.text for p in batch] for batch in expected]
    assert detail["status"] == "done"
    assert detail["analysis_counts"] == {"ai": 4 - broken_singleton, "offline": int(broken_singleton),
                                          "pending": 0, "total": 4}
    assert detail["can_continue_analysis"] is broken_singleton
    assert [p["text"] for p in detail["posts"]] == [p.text for p in raw]
    if broken_singleton:
        assert detail["posts"][-1]["analyzed_by"] == "offline"
        assert detail["posts"][-1]["job"]["salary"] == "25 triệu"


# =====================================================================
# 7. User khác không gửi được run của người khác
# =====================================================================

def test_cannot_retry_analysis_of_other_user_run(cloud):
    """User B không thể tiếp tục hoặc can thiệp phân tích lượt của User A (trả về 404)."""
    client = cloud()
    headers_a = _signup(client, email="user_a@x.io")
    user_a_id = api.db().get_user_by_email("user_a@x.io").id

    # User A tạo run
    rid_a = api.db().create_run(RunRequest(platform="facebook", ai_provider="openai"), user_a_id, status="analysis_failed")
    api.db().save_raw_posts(rid_a, [RawPost(platform="facebook", source="feed", text="Dữ liệu riêng tư của User A")])

    # User B đăng nhập
    headers_b = _signup(client, email="user_b@x.io")

    # User B thử đọc run của User A -> 404
    resp_get = client.get(f"/api/runs/{rid_a}", headers=headers_b)
    assert resp_get.status_code == 404
    assert resp_get.json()["detail"] == "Không tìm thấy lượt này."

    # User B thử kích hoạt phân tích run của User A -> 404
    resp_post = client.post(f"/api/runs/{rid_a}/analysis", headers=headers_b, json={"ai_provider": "openai"})
    assert resp_post.status_code == 404
    assert resp_post.json()["detail"] == "Không tìm thấy lượt này."
