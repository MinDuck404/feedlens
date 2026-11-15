"""/api/topics: chủ đề của người dùng, thử khớp nhanh, và gắn chủ đề lại cho các lượt cũ."""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .ai import user_keys
from .ai.registry import preferred_provider
from .analyzer import get_analyzer
from .auth import CurrentUser, current_user
from .models import MAX_TOPICS, TOPIC_COLORS, AnalyzedPost, Topic

# user_id -> {"state": idle|running|done|error, "done", "total", "error"}
RETAG_JOBS: dict[int, dict] = {}
RETAG_LIMIT = 2000  # số bài gần nhất được gắn lại mỗi lần


class TestBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


def _clean(t: Topic) -> Topic:
    t.name = t.name.strip()[:80]
    t.description = t.description.strip()[:400]
    t.include_keywords = [k.strip()[:60] for k in t.include_keywords if k.strip()][:20]
    t.exclude_keywords = [k.strip()[:60] for k in t.exclude_keywords if k.strip()][:20]
    if t.color not in TOPIC_COLORS:
        t.color = TOPIC_COLORS[0]
    return t


def _err(code: str, status: int) -> JSONResponse:
    return JSONResponse({"code": code, "detail": code}, status_code=status)


def _analyzer(db, user_id: int):
    analyzer = get_analyzer(preferred_provider(db, user_id, "auto"), None, user_keys(db, user_id), user_id)
    return analyzer


def run_retag(db, user_id: int) -> None:
    job = RETAG_JOBS[user_id]
    try:
        topics = db.list_topics(user_id, enabled_only=True)
        posts = db.user_posts(user_id, RETAG_LIMIT)
        job.update(total=len(posts), done=0)
        if not topics:
            db.set_post_topics(user_id, {p.id: ([], "") for p in posts if p.topic_ids})
            job.update(state="done", done=len(posts))
            return
        analyzer = _analyzer(db, user_id)
        updates = analyzer.tag_topics(posts, topics, lambda n, _m: job.update(done=n))
        db.set_post_topics(user_id, updates)
        job.update(state="done", done=len(posts))
    except Exception as exc:  # noqa: BLE001 — trạng thái lỗi hiện trên web
        job.update(state="error", error=str(exc)[:300])


def topics_router(db):
    router = APIRouter(prefix="/api/topics")

    @router.get("")
    def list_topics(user: CurrentUser = Depends(current_user)):
        return {"topics": db().list_topics(user.id), "colors": list(TOPIC_COLORS), "max": MAX_TOPICS}

    @router.post("")
    def create_topic(topic: Topic, user: CurrentUser = Depends(current_user)):
        if len(db().list_topics(user.id)) >= MAX_TOPICS:
            return _err("error.topics_limit", 409)
        return db().create_topic(user.id, _clean(topic))

    @router.put("/{topic_id}")
    def update_topic(topic_id: int, topic: Topic, user: CurrentUser = Depends(current_user)):
        row = db().update_topic(user.id, topic_id, _clean(topic))
        return row if row else _err("error.topic_missing", 404)

    @router.delete("/{topic_id}")
    def delete_topic(topic_id: int, user: CurrentUser = Depends(current_user)):
        return {"ok": True} if db().delete_topic(user.id, topic_id) else _err("error.topic_missing", 404)

    @router.post("/test")
    def test_topics(body: TestBody, user: CurrentUser = Depends(current_user)):
        """Dán thử một đoạn bài: chủ đề nào khớp? (gọi AI một lần nếu có key)."""
        topics = db().list_topics(user.id, enabled_only=True)
        if not topics:
            return {"matches": []}
        post = AnalyzedPost(id=1, platform="test", source="test", text=body.text, summary="")
        try:
            result = _analyzer(db(), user.id).tag_topics([post], topics)
        except Exception:  # noqa: BLE001
            return _err("error.topic_test_failed", 502)
        ids, reason = result.get(1, ([], ""))
        return {"matches": [{"topic_id": i, "reason": reason} for i in ids]}

    @router.post("/apply")
    def apply_topics(user: CurrentUser = Depends(current_user)):
        job = RETAG_JOBS.get(user.id)
        if job and job.get("state") == "running":
            return job
        RETAG_JOBS[user.id] = {"state": "running", "done": 0, "total": 0, "error": ""}
        threading.Thread(target=run_retag, args=(db(), user.id), daemon=True).start()
        return RETAG_JOBS[user.id]

    @router.get("/apply")
    def apply_status(user: CurrentUser = Depends(current_user)):
        return RETAG_JOBS.get(user.id, {"state": "idle", "done": 0, "total": 0, "error": ""})

    return router
