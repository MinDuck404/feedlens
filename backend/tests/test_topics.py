from types import SimpleNamespace

from feedlens import api, topics_api
from feedlens.analysis.heuristic import HeuristicAnalyzer
from feedlens.analysis.llm import LLMAnalyzer
from feedlens.analysis.topics import heuristic_topics
from feedlens.models import AnalyzedPost, RawPost, Topic
from tests.test_cloud import cloud, _signup  # noqa: F401 — fixture


def fake_llm(handler):
    prompts = []

    def complete(system, prompt, schema, effort):
        prompts.append((prompt, schema))
        return handler(prompt, schema)

    return LLMAnalyzer(SimpleNamespace(complete_json=complete, model="fake", info=SimpleNamespace(name="Fake"))), prompts


def test_retag_skips_pending_rows_before_applying_the_post_limit(cloud, monkeypatch):
    from feedlens.models import RunRequest
    client = cloud()
    _signup(client)
    db = api.db()
    uid = db.get_user_by_email("a@x.io").id
    req = RunRequest(platform="facebook")
    read_run = db.create_run(req, uid)
    db.save_posts(read_run, [AnalyzedPost(platform="facebook", source="feed", text="AI read", analyzed_by="Fake AI"),
                             AnalyzedPost(platform="facebook", source="feed", text="Offline read", analyzed_by="offline")])
    pending_run = db.create_run(req, uid)
    db.save_posts(pending_run, [AnalyzedPost(platform="facebook", source="feed", text="Pending reanalysis", analyzed_by="Fake AI")])
    db.mark_posts_pending(pending_run)
    db.create_topic(uid, Topic(name="Python"))
    captured = []
    analyzer = SimpleNamespace(tag_topics=lambda posts, topics, progress: captured.extend(posts) or {})
    monkeypatch.setattr(topics_api, "_analyzer", lambda *args: analyzer)
    monkeypatch.setattr(topics_api, "RETAG_JOBS", {uid: {"state": "running", "done": 0, "total": 0, "error": ""}})
    topics_api.run_retag(db, uid)
    assert {p.text for p in captured} == {"AI read", "Offline read"}
    assert topics_api.RETAG_JOBS[uid]["total"] == 2
    assert [p.text for p in db.user_posts(uid, limit=1)] == ["Offline read"]
    assert db.get_posts(pending_run)[0].analyzed is False


def test_topic_crud_isolation_and_limit(cloud):
    client = cloud()
    a, b = _signup(client, "t-a@example.test"), _signup(client, "t-b@example.test")
    assert client.get("/api/topics").status_code == 401
    r = client.post("/api/topics", headers=a, json={"name": "  Claude skills ", "description": "Skills for Claude Code",
                                                     "include_keywords": ["skill", " "], "color": "nope"})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["name"] == "Claude skills" and t["include_keywords"] == ["skill"] and t["color"] == "red"
    assert client.get("/api/topics", headers=b).json()["topics"] == []
    assert client.put(f"/api/topics/{t['id']}", headers=b, json={"name": "hijack"}).status_code == 404
    assert client.delete(f"/api/topics/{t['id']}", headers=b).status_code == 404
    r = client.put(f"/api/topics/{t['id']}", headers=a, json={"name": "GitHub repos", "enabled": False})
    assert r.json()["name"] == "GitHub repos" and r.json()["enabled"] is False
    for i in range(11):
        assert client.post("/api/topics", headers=a, json={"name": f"t{i}"}).status_code == 200
    r = client.post("/api/topics", headers=a, json={"name": "too many"})
    assert r.status_code == 409 and r.json()["code"] == "error.topics_limit"
    assert client.delete(f"/api/topics/{t['id']}", headers=a).status_code == 200
    assert len(client.get("/api/topics", headers=a).json()["topics"]) == 11


def test_heuristic_topic_match_respects_exclude():
    topics = [Topic(id=1, name="GitHub", include_keywords=["github.com"], exclude_keywords=["tuyển"]),
              Topic(id=2, name="Claude")]
    assert heuristic_topics("Repo hay: github.com/foo/bar", topics) == [1]
    assert heuristic_topics("Tuyển dev, xem github.com/acme", topics) == []
    assert heuristic_topics("Mẹo dùng claude code", topics) == [2]
    analyzer = HeuristicAnalyzer()
    analyzer.topics = topics
    posts = analyzer.classify([RawPost(platform="facebook", source="g", text="Repo hay: github.com/foo/bar")],
                              False, [], "", lambda n, m: None)
    assert posts[0].topic_ids == [1]
    digest = analyzer.digest([posts[0].model_copy(update={"id": 7})], False)
    assert [(t.topic_id, t.count, t.post_ids) for t in digest.topics] == [(1, 1, [7]), (2, 0, [])]


def test_llm_sends_topics_once_per_batch_and_drops_unknown_ids():
    topics = [Topic(id=5, name="UNIQUE_TOPIC_MARKER", description="Claude skills")]

    def handler(prompt, schema):
        item = schema["properties"]["items"]["items"]
        assert "topic_ids" in item["required"]
        n = prompt.count("<post id=")
        return {"items": [{"id": i, "category": "tech", "summary": "s", "is_job": False,
                           "job": {k: "" for k in ("title", "company", "location", "salary", "work_mode", "contact", "match_reason")}
                           | {"match_score": 0, "match_type": "none", "gaps": [], "constraint_flags": []},
                           "topic_ids": [5, 99] if i == 0 else [], "topic_reason": "about skills"} for i in range(n)]}

    analyzer, prompts = fake_llm(handler)
    analyzer.topics = topics
    raw = [RawPost(platform="facebook", source="g", text=f"post {i}") for i in range(61)]
    out = analyzer.classify(raw, False, [], "", lambda n, m: None)
    assert len(prompts) == 2
    assert all(p.count("UNIQUE_TOPIC_MARKER") == 1 for p, _ in prompts)
    assert out[0].topic_ids == [5] and out[0].topic_reason == "about skills"
    assert out[1].topic_ids == [] and out[1].topic_reason == ""


def test_llm_without_topics_keeps_old_schema():
    def handler(prompt, schema):
        assert "topic_ids" not in schema["properties"]["items"]["items"]["properties"]
        assert "<user_topics>" not in prompt
        return {"items": []}

    analyzer, _ = fake_llm(handler)
    analyzer.classify([RawPost(platform="facebook", source="g", text="x")], False, [], "", lambda n, m: None)


def test_topic_digest_lists_empty_topics_and_summarizes_only_matched():
    topics = [Topic(id=1, name="A"), Topic(id=2, name="B")]

    def handler(prompt, schema):
        assert 'name="A"' in prompt and 'name="B"' not in prompt
        return {"topics": [{"topic_id": 1, "summary": "Tóm tắt A"}]}

    analyzer, prompts = fake_llm(handler)
    analyzer.topics = topics
    posts = [AnalyzedPost(id=3, platform="facebook", source="g", text="x", summary="s", topic_ids=[1])]
    result = analyzer.topic_digest(posts)
    assert [(t.topic_id, t.count, t.summary, t.post_ids) for t in result] == [(1, 1, "Tóm tắt A", [3]), (2, 0, "", [])]
    assert len(prompts) == 1


def test_apply_retags_old_posts_and_test_endpoint(cloud):
    client = cloud()
    h = _signup(client, "retag@example.test")
    user = api.db().get_user_by_email("retag@example.test")
    db = api.db()
    from feedlens.models import RunRequest
    run_id = db.create_run(RunRequest(platform="facebook"), user.id, status="done")
    db.save_batch(run_id, [AnalyzedPost(platform="facebook", source="g", text="Repo hay github.com/x/y", summary="repo"),
                           AnalyzedPost(platform="facebook", source="g", text="Bán xe máy", summary="xe")])
    db.update_run(run_id, digest={"overall": "o", "categories": [], "action_items": []})  # bản tin cũ, chưa có topics
    t = client.post("/api/topics", headers=h, json={"name": "GitHub", "include_keywords": ["github.com"]}).json()
    # Chạy đồng bộ để test ổn định (API thật chạy nền)
    topics_api.RETAG_JOBS[user.id] = {"state": "running", "done": 0, "total": 0, "error": ""}
    topics_api.run_retag(db, user.id)
    assert topics_api.RETAG_JOBS[user.id]["state"] == "done"
    tagged = {p.summary: p.topic_ids for p in db.get_posts(run_id)}
    assert tagged == {"repo": [t["id"]], "xe": []}
    repo_id = next(p.id for p in db.get_posts(run_id) if p.summary == "repo")
    topics_digest = db.get_run(run_id)["digest"]["topics"]
    assert [(d["topic_id"], d["count"], d["post_ids"]) for d in topics_digest] == [(t["id"], 1, [repo_id])]
    r = client.post("/api/topics/test", headers=h, json={"text": "xem github.com/abc"})
    assert r.status_code == 200 and r.json()["matches"][0]["topic_id"] == t["id"]
    # Xóa chủ đề thì gỡ nhãn khỏi bài
    assert client.delete(f"/api/topics/{t['id']}", headers=h).status_code == 200
    assert all(p.topic_ids == [] for p in db.get_posts(run_id))
    assert db.get_run(run_id)["digest"]["topics"] == []
