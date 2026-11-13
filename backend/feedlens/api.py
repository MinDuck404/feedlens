"""REST API cho frontend và cho bot ở máy (`feedlens push`).

Chế độ local (mặc định): API điều khiển trình duyệt trên chính máy này.
Chế độ cloud (FEEDLENS_MODE=cloud): không có trình duyệt; nhận bài qua /api/ingest, bắt buộc đăng nhập.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import browser
from .ai import list_providers, resolve_provider_key
from .auth import check_password, issue_token, misconfigured, require_auth
from .config import BACKEND_DIR, settings
from .db import Database
from .export import to_csv, to_json, to_markdown
from .models import CATEGORIES, RawPost, RunRequest
from .pipeline import PROGRESS, start_ingest, start_run

app = FastAPI(title="FeedLens API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])
db = Database(settings.database_url)

public = APIRouter(prefix="/api")
private = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

_login_state: dict[str, str] = {}   # platform -> idle | waiting
_session_cache: dict[str, bool] = {}
_failed_logins: dict[str, deque] = defaultdict(deque)
LOGIN_WINDOW, LOGIN_MAX_FAILS = 15 * 60, 10


def _local_only():
    if settings.is_cloud:
        raise HTTPException(409, "Server cloud không có trình duyệt. Lướt bằng `feedlens push` trên máy bạn.")


def _platform_or_404(p: str):
    if p not in browser.PLATFORMS:
        raise HTTPException(404, "Nền tảng không hỗ trợ")
    return browser.PLATFORMS[p]


# ================================================================== public
@public.get("/health")
def health():
    return {"ok": True, "mode": settings.mode, "db": db.engine.dialect.name}


@public.get("/meta")
def meta():
    try:
        default_ai = resolve_provider_key("auto")
    except ValueError:
        default_ai = "offline"
    return {"mode": settings.mode, "auth_required": settings.auth_enabled, "config_error": misconfigured(),
            "categories": CATEGORIES, "max_posts": settings.max_posts,
            "default_ai": default_ai, "ai_providers": list_providers()}


class LoginBody(BaseModel):
    password: str


@public.post("/auth/login")
def login_app(body: LoginBody, request: Request):
    if err := misconfigured():
        raise HTTPException(503, err)
    if not settings.auth_enabled:
        return {"token": ""}
    ip = request.client.host if request.client else "?"
    fails = _failed_logins[ip]
    while fails and fails[0] < time.time() - LOGIN_WINDOW:
        fails.popleft()
    if len(fails) >= LOGIN_MAX_FAILS:
        raise HTTPException(429, "Sai mật khẩu quá nhiều lần. Thử lại sau 15 phút.")
    if not check_password(body.password):
        fails.append(time.time())
        raise HTTPException(401, "Sai mật khẩu.")
    fails.clear()
    return {"token": issue_token()}


# ================================================================== platforms (chỉ local)
@private.get("/platforms")
def platforms():
    if settings.is_cloud:
        return []
    return [{"key": k, "name": v.name, "logged_in": _session_cache.get(k),
             "has_profile": browser.profile_dir(k).exists(),
             "login_state": _login_state.get(k, "idle")} for k, v in browser.PLATFORMS.items()]


@private.post("/platforms/{p}/check")
async def check(p: str):
    _local_only()
    _platform_or_404(p)
    ok = await run_in_threadpool(browser.check_session, p)
    _session_cache[p] = ok
    return {"logged_in": ok}


@private.post("/platforms/{p}/login")
def login_platform(p: str):
    _local_only()
    _platform_or_404(p)
    if _login_state.get(p) != "waiting":
        def worker():
            _login_state[p] = "waiting"
            try:
                _session_cache[p] = browser.interactive_login(p)
            finally:
                _login_state[p] = "idle"
        threading.Thread(target=worker, daemon=True).start()
    return {"status": "waiting"}


@private.post("/platforms/{p}/logout")
def logout_platform(p: str):
    _local_only()
    _platform_or_404(p)
    browser.logout(p)
    _session_cache[p] = False
    return {"ok": True}


# ================================================================== runs
def _check_ai(req: RunRequest):
    try:
        resolve_provider_key(req.ai_provider)
    except ValueError as e:
        raise HTTPException(400, str(e))


@private.post("/runs")
def create_run(req: RunRequest):
    _local_only()
    if req.source_type != "feed" and not req.sources:
        raise HTTPException(400, "Nhập ít nhất một group hoặc từ khóa.")
    _check_ai(req)
    return {"id": start_run(db, req)}


class IngestBody(BaseModel):
    request: RunRequest
    posts: list[RawPost] = Field(..., min_length=1)


@private.post("/ingest")
def ingest(body: IngestBody):
    """Nhận bài do bot ở máy người dùng lướt, rồi phân tích trên server."""
    if len(body.posts) > settings.max_posts:
        raise HTTPException(413, f"Tối đa {settings.max_posts} bài mỗi lượt.")
    _check_ai(body.request)
    posts = [p.model_copy(update={"text": p.text[:20_000]}) for p in body.posts]
    return {"id": start_ingest(db, body.request, posts)}


@private.get("/runs")
def runs():
    return [{**r, "progress": PROGRESS.get(r["id"])} for r in db.list_runs()]


@private.get("/runs/{run_id}")
def run_detail(run_id: int):
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404)
    return {**r, "progress": PROGRESS.get(run_id),
            "posts": [p.model_dump() for p in db.get_posts(run_id)]}


@private.delete("/runs/{run_id}")
def delete_run(run_id: int):
    db.delete_run(run_id)
    return {"ok": True}


@private.get("/runs/{run_id}/export")
def export(run_id: int, fmt: str = "md"):
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404)
    posts = db.get_posts(run_id)
    body, mime, ext = {
        "csv": (lambda: to_csv(posts), "text/csv; charset=utf-8", "csv"),
        "json": (lambda: to_json(r, posts), "application/json", "json"),
    }.get(fmt, (lambda: to_markdown(r, posts), "text/markdown; charset=utf-8", "md"))
    return PlainTextResponse(body(), media_type=mime,
                             headers={"Content-Disposition": f'attachment; filename="feedlens-{run_id}.{ext}"'})


app.include_router(public)
app.include_router(private)

# ================================================================== frontend build (chế độ local, tùy chọn)
DIST = BACKEND_DIR.parent / "frontend" / "dist"
if DIST.exists() and not settings.is_cloud:
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
