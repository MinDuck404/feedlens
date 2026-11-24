"""Agent routes."""
from __future__ import annotations


import feedlens.core.crypto as crypto
import datetime as datetime_module
import fastapi as fastapi
import feedlens.core.models as models
import feedlens.routes.dependencies as dependencies
import feedlens.routes.runs as run_routes
import feedlens.runs.pipeline as run_pipeline

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from feedlens.core.auth import CurrentUser as User
from feedlens.core.auth import agent_user
from feedlens.core.auth import current_user
from feedlens.core.models import RawPost
from feedlens.core.models import RunRequest

private = APIRouter()


AGENT_ONLINE_SECONDS = 30

def _agent_info(user_id: int) -> dict:
    u = dependencies.db().get_user(user_id)
    seen = u.agent_last_seen if u else None
    if seen and seen.tzinfo is None:
        seen = seen.replace(tzinfo=datetime_module.timezone.utc)
    online = bool(seen and (datetime_module.datetime.now(datetime_module.timezone.utc) - seen).total_seconds() < AGENT_ONLINE_SECONDS)
    return {"has_token": bool(u and u.agent_token_hash), "online": online,
            "last_seen": seen.isoformat() if seen else None}


@private.post("/agent/token")
def create_agent_token(user: User = Depends(current_user)):
    """Tạo token mới cho agent (token cũ mất hiệu lực). Token chỉ hiện một lần."""
    if user.via_agent:
        raise fastapi.HTTPException(403)
    token = crypto.new_agent_token()
    dependencies.db().set_agent_token_hash(user.id, crypto.sha256(token))
    return {"token": token}


class PostsBody(BaseModel):
    posts: list[RawPost] = Field(default_factory=list)


def _clean_posts(posts: list[RawPost], cap: int) -> list[RawPost]:
    if len(posts) > cap:
        raise fastapi.HTTPException(413, f"Tối đa {cap} bài mỗi lượt.")
    return [p.model_copy(update={"text": p.text[:20_000]}) for p in posts]


@private.get("/agent/next")
def agent_next(user: User = Depends(agent_user), protocol_version: int = Query(1, ge=1, le=2)):
    """Agent hỏi việc mỗi vài giây; đồng thời là tín hiệu 'agent đang bật'."""
    dependencies.db().touch_agent(user.id)
    job = dependencies.db().claim_next_pending(user.id, protocol_version=protocol_version)
    if not job:
        return {"job": None}
    from feedlens.runs.pipeline import total_target
    run_pipeline.PROGRESS[job["id"]] = {"phase": "scraping", "done": 0, "target": total_target(models.RunRequest(**job["request"])),
                           "message": "Agent đã nhận việc, đang mở trình duyệt…"}
    return {"job": {"id": job["id"], "request": job["request"]}}


class ProgressBody(BaseModel):
    done: int = 0
    target: int = 0
    message: str = Field("", max_length=300)


@private.post("/agent/runs/{run_id}/progress")
def agent_progress(run_id: int, body: ProgressBody, user: User = Depends(agent_user)):
    r = run_routes._own_run(run_id, user)
    if r["status"] != "scraping":
        raise fastapi.HTTPException(409, "Lượt này không còn ở trạng thái đang lướt.")
    dependencies.db().touch_agent(user.id)
    run_pipeline.PROGRESS[run_id] = {"phase": "scraping", **body.model_dump()}
    return {"ok": True}


@private.post("/agent/runs/{run_id}/posts")
def agent_posts(run_id: int, body: PostsBody, user: User = Depends(agent_user)):
    r = run_routes._own_run(run_id, user)
    if r["status"] != "scraping":
        raise fastapi.HTTPException(409, "Lượt này không còn ở trạng thái đang lướt.")
    req = models.RunRequest(**r["request"])
    run_pipeline.start_analysis(dependencies.db(), run_id, req, _clean_posts(body.posts, run_pipeline.run_cap(req)), user.id)
    return {"ok": True}


class FailBody(BaseModel):
    error: str = Field(max_length=2000)


@private.post("/agent/runs/{run_id}/fail")
def agent_fail(run_id: int, body: FailBody, user: User = Depends(agent_user)):
    run_routes._own_run(run_id, user)
    run_pipeline.fail_run(dependencies.db(), run_id, f"Agent báo lỗi: {body.error}")
    return {"ok": True}


class IngestBody(BaseModel):
    request: RunRequest
    posts: list[RawPost] = Field(..., min_length=1)


@private.post("/ingest")
def ingest(body: IngestBody, user: User = Depends(current_user)):
    """`feedlens push`: gửi một lượt đã lướt xong, không qua hàng đợi."""
    run_routes._check_ai(body.request, user.id)
    return {"id": run_pipeline.start_ingest(dependencies.db(), body.request, _clean_posts(body.posts, run_pipeline.run_cap(body.request)), user.id)}
