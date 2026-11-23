"""Agent routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from ..auth import CurrentUser as User, agent_user, current_user
from ..models import RawPost, RunRequest
from .. import api

private = APIRouter()


@private.post("/agent/token")
def create_agent_token(user: User = Depends(current_user)):
    """Tạo token mới cho agent (token cũ mất hiệu lực). Token chỉ hiện một lần."""
    if user.via_agent:
        raise api.HTTPException(403)
    token = api.new_agent_token()
    api.db().set_agent_token_hash(user.id, api.sha256(token))
    return {"token": token}


class PostsBody(BaseModel):
    posts: list[RawPost] = Field(default_factory=list)


def _clean_posts(posts: list[RawPost], cap: int) -> list[RawPost]:
    if len(posts) > cap:
        raise api.HTTPException(413, f"Tối đa {cap} bài mỗi lượt.")
    return [p.model_copy(update={"text": p.text[:20_000]}) for p in posts]


@private.get("/agent/next")
def agent_next(user: User = Depends(agent_user), protocol_version: int = Query(1, ge=1, le=2)):
    """Agent hỏi việc mỗi vài giây; đồng thời là tín hiệu 'agent đang bật'."""
    api.db().touch_agent(user.id)
    job = api.db().claim_next_pending(user.id, protocol_version=protocol_version)
    if not job:
        return {"job": None}
    from ..pipeline import total_target
    api.PROGRESS[job["id"]] = {"phase": "scraping", "done": 0, "target": total_target(api.RunRequest(**job["request"])),
                           "message": "Agent đã nhận việc, đang mở trình duyệt…"}
    return {"job": {"id": job["id"], "request": job["request"]}}


class ProgressBody(BaseModel):
    done: int = 0
    target: int = 0
    message: str = Field("", max_length=300)


@private.post("/agent/runs/{run_id}/progress")
def agent_progress(run_id: int, body: ProgressBody, user: User = Depends(agent_user)):
    r = api._own_run(run_id, user)
    if r["status"] != "scraping":
        raise api.HTTPException(409, "Lượt này không còn ở trạng thái đang lướt.")
    api.db().touch_agent(user.id)
    api.PROGRESS[run_id] = {"phase": "scraping", **body.model_dump()}
    return {"ok": True}


@private.post("/agent/runs/{run_id}/posts")
def agent_posts(run_id: int, body: PostsBody, user: User = Depends(agent_user)):
    r = api._own_run(run_id, user)
    if r["status"] != "scraping":
        raise api.HTTPException(409, "Lượt này không còn ở trạng thái đang lướt.")
    req = api.RunRequest(**r["request"])
    api.start_analysis(api.db(), run_id, req, api._clean_posts(body.posts, api.run_cap(req)), user.id)
    return {"ok": True}


class FailBody(BaseModel):
    error: str = Field(max_length=2000)


@private.post("/agent/runs/{run_id}/fail")
def agent_fail(run_id: int, body: FailBody, user: User = Depends(agent_user)):
    api._own_run(run_id, user)
    api.fail_run(api.db(), run_id, f"Agent báo lỗi: {body.error}")
    return {"ok": True}


class IngestBody(BaseModel):
    request: RunRequest
    posts: list[RawPost] = Field(..., min_length=1)


@private.post("/ingest")
def ingest(body: IngestBody, user: User = Depends(current_user)):
    """`feedlens push`: gửi một lượt đã lướt xong, không qua hàng đợi."""
    api._check_ai(body.request, user.id)
    return {"id": api.start_ingest(api.db(), body.request, api._clean_posts(body.posts, api.run_cap(body.request)), user.id)}
