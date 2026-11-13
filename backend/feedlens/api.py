"""REST API cho frontend và cho agent chạy trên máy người dùng.

Chế độ local (mặc định): một người dùng ngầm định; API điều khiển trình duyệt trên chính máy này.
Chế độ cloud (FEEDLENS_MODE=cloud): nhiều tài khoản; server không có trình duyệt. Bấm "Bắt đầu lướt"
tạo lượt ở trạng thái `pending`, agent trên máy người dùng (`feedlens agent`) nhận việc, lướt và gửi bài lên.
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import browser
from .ai import (PROVIDERS, forget_models, list_models, pick_default, provider_status, resolve_provider_key,
                 user_keys)
from .auth import CurrentUser, agent_user, current_user, issue_token, misconfigured
from .config import BACKEND_DIR, settings
from .crypto import encrypt, hash_password, key_hint, new_agent_token, sha256, verify_password
from .db import Database, EmailTaken
from .export import to_csv, to_json, to_markdown
from .models import CATEGORIES, RawPost, RunRequest
from .pipeline import PROGRESS, fail_run, start_analysis, start_ingest, start_run

app = FastAPI(title="FeedLens API", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])
app.state.db = Database(settings.database_url)
app.state.db.fail_interrupted()

public = APIRouter(prefix="/api")
private = APIRouter(prefix="/api")

User = CurrentUser
AGENT_ONLINE_SECONDS = 30
_login_state: dict[str, str] = {}   # platform -> idle | waiting (chỉ local)
_session_cache: dict[str, bool] = {}
_attempts: dict[str, deque] = defaultdict(deque)
LOGIN_WINDOW, LOGIN_MAX_FAILS = 15 * 60, 10
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def db() -> Database:
    return app.state.db


def _local_only():
    if settings.is_cloud:
        raise HTTPException(409, "Server cloud không có trình duyệt. Hãy bật agent trên máy bạn.")


def _platform_or_404(p: str):
    if p not in browser.PLATFORMS:
        raise HTTPException(404, "Nền tảng không hỗ trợ")
    return browser.PLATFORMS[p]


def _throttle(*keys: str) -> None:
    now = time.time()
    for k in keys:
        q = _attempts[k]
        while q and q[0] < now - LOGIN_WINDOW:
            q.popleft()
        if len(q) >= LOGIN_MAX_FAILS:
            raise HTTPException(429, "Thử quá nhiều lần. Đợi 15 phút rồi thử lại.")


def _fail_attempt(*keys: str) -> None:
    for k in keys:
        _attempts[k].append(time.time())


def _agent_info(user_id: int) -> dict:
    u = db().get_user(user_id)
    seen = u.agent_last_seen if u else None
    if seen and seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    online = bool(seen and (datetime.now(timezone.utc) - seen).total_seconds() < AGENT_ONLINE_SECONDS)
    return {"has_token": bool(u and u.agent_token_hash), "online": online,
            "last_seen": seen.isoformat() if seen else None}


# ================================================================== public
@public.get("/health")
def health():
    return {"ok": True, "mode": settings.mode, "db": db().engine.dialect.name}


@public.get("/meta")
def meta():
    return {"mode": settings.mode, "auth_required": settings.auth_enabled, "config_error": misconfigured(),
            "signup_open": settings.allow_signup, "categories": CATEGORIES, "max_posts": settings.max_posts}


class Credentials(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


@public.post("/auth/register")
def register(body: Credentials, request: Request):
    if err := misconfigured():
        raise HTTPException(503, err)
    if not settings.is_cloud:
        raise HTTPException(409, "Chế độ local không cần tài khoản.")
    if not settings.allow_signup:
        raise HTTPException(403, "Server này đang đóng đăng ký.")
    ip = request.client.host if request.client else "?"
    _throttle(f"reg:{ip}")
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Email không hợp lệ.")
    if len(body.password) < 8:
        raise HTTPException(400, "Mật khẩu cần ít nhất 8 ký tự.")
    _fail_attempt(f"reg:{ip}")  # giới hạn số tài khoản tạo từ một IP
    try:
        uid = db().create_user(email, hash_password(body.password))
    except EmailTaken:
        raise HTTPException(409, "Email này đã có tài khoản. Hãy đăng nhập.")
    return {"token": issue_token(uid), "email": email}


@public.post("/auth/login")
def login(body: Credentials, request: Request):
    if err := misconfigured():
        raise HTTPException(503, err)
    if not settings.is_cloud:
        return {"token": "", "email": "local"}
    ip = request.client.host if request.client else "?"
    email = body.email.strip().lower()
    _throttle(f"ip:{ip}", f"email:{email}")
    u = db().get_user_by_email(email)
    if not u or not verify_password(body.password, u.password_hash):
        _fail_attempt(f"ip:{ip}", f"email:{email}")
        raise HTTPException(401, "Sai email hoặc mật khẩu.")
    return {"token": issue_token(u.id), "email": u.email}


# ================================================================== tài khoản + agent
@private.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email, "agent": _agent_info(user.id)}


@private.post("/agent/token")
def create_agent_token(user: User = Depends(current_user)):
    """Tạo token mới cho agent (token cũ mất hiệu lực). Token chỉ hiện một lần."""
    if user.via_agent:
        raise HTTPException(403)
    token = new_agent_token()
    db().set_agent_token_hash(user.id, sha256(token))
    return {"token": token}


# ================================================================== AI keys + models
@private.get("/ai/providers")
def ai_providers(user: User = Depends(current_user)):
    return provider_status(db(), user.id)


class KeyBody(BaseModel):
    api_key: str = Field(min_length=8, max_length=500)


def _provider_or_404(p: str):
    if p not in PROVIDERS:
        raise HTTPException(404, "Nhà cung cấp AI không hỗ trợ")


@private.put("/ai/keys/{p}")
async def save_key(p: str, body: KeyBody, user: User = Depends(current_user)):
    """Kiểm tra key bằng cách lấy danh sách model, đúng thì mã hóa và lưu."""
    _provider_or_404(p)
    key = body.api_key.strip()
    try:
        models = await run_in_threadpool(list_models, user.id, p, key, True)
    except Exception as e:  # noqa: BLE001 — lỗi xác thực của nhà cung cấp
        forget_models(user.id, p)
        raise HTTPException(400, f"Key không dùng được với {PROVIDERS[p].info.name}: {str(e)[:200]}")
    db().upsert_key(user.id, p, encrypt(key), key_hint(key))
    return {"ok": True, "models": models}


@private.delete("/ai/keys/{p}")
def delete_key(p: str, user: User = Depends(current_user)):
    _provider_or_404(p)
    db().delete_key(user.id, p)
    forget_models(user.id, p)
    return {"ok": True}


@private.get("/ai/models/{p}")
async def models(p: str, refresh: bool = False, user: User = Depends(current_user)):
    _provider_or_404(p)
    keys = user_keys(db(), user.id)
    if p not in keys:
        raise HTTPException(400, f"Chưa có API key cho {PROVIDERS[p].info.name}.")
    try:
        items = await run_in_threadpool(list_models, user.id, p, keys[p][0], refresh)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Không lấy được danh sách model: {str(e)[:200]}")
    return {"models": items, "default": pick_default(p, items)}


# ================================================================== platforms (chỉ local)
@private.get("/platforms")
def platforms(user: User = Depends(current_user)):
    if settings.is_cloud:
        return []
    return [{"key": k, "name": v.name, "logged_in": _session_cache.get(k),
             "has_profile": browser.profile_dir(k).exists(),
             "login_state": _login_state.get(k, "idle")} for k, v in browser.PLATFORMS.items()]


@private.post("/platforms/{p}/check")
async def check(p: str, user: User = Depends(current_user)):
    _local_only()
    _platform_or_404(p)
    ok = await run_in_threadpool(browser.check_session, p)
    _session_cache[p] = ok
    return {"logged_in": ok}


@private.post("/platforms/{p}/login")
def login_platform(p: str, user: User = Depends(current_user)):
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
def logout_platform(p: str, user: User = Depends(current_user)):
    _local_only()
    _platform_or_404(p)
    browser.logout(p)
    _session_cache[p] = False
    return {"ok": True}


# ================================================================== runs
def _check_ai(req: RunRequest, user_id: int):
    try:
        resolve_provider_key(req.ai_provider, user_keys(db(), user_id))
    except ValueError as e:
        raise HTTPException(400, str(e))


def _own_run(run_id: int, user: User) -> dict:
    r = db().get_run(run_id, user.id)
    if not r:
        raise HTTPException(404, "Không tìm thấy lượt này.")
    return r


@private.post("/runs")
def create_run(req: RunRequest, user: User = Depends(current_user)):
    if req.source_type != "feed" and not req.sources:
        raise HTTPException(400, "Nhập ít nhất một group hoặc từ khóa.")
    req = req.model_copy(update={"count": min(req.count, settings.max_posts)})
    _check_ai(req, user.id)
    if settings.is_cloud:
        run_id = db().create_run(req, user.id, status="pending")
        PROGRESS[run_id] = {"phase": "pending", "done": 0, "target": req.count, "message": "Đang chờ agent nhận việc…"}
        return {"id": run_id, "agent": _agent_info(user.id)}
    return {"id": start_run(db(), req, user.id)}


@private.get("/runs")
def runs(user: User = Depends(current_user)):
    return [{**r, "progress": PROGRESS.get(r["id"])} for r in db().list_runs(user.id)]


@private.get("/runs/{run_id}")
def run_detail(run_id: int, user: User = Depends(current_user)):
    r = _own_run(run_id, user)
    return {**r, "progress": PROGRESS.get(run_id), "posts": [p.model_dump() for p in db().get_posts(run_id)]}


@private.delete("/runs/{run_id}")
def delete_run(run_id: int, user: User = Depends(current_user)):
    if not db().delete_run(run_id, user.id):
        raise HTTPException(404, "Không tìm thấy lượt này.")
    PROGRESS.pop(run_id, None)
    return {"ok": True}


@private.get("/runs/{run_id}/export")
def export(run_id: int, fmt: str = "md", user: User = Depends(current_user)):
    r = _own_run(run_id, user)
    posts = db().get_posts(run_id)
    body, mime, ext = {
        "csv": (lambda: to_csv(posts), "text/csv; charset=utf-8", "csv"),
        "json": (lambda: to_json(r, posts), "application/json", "json"),
    }.get(fmt, (lambda: to_markdown(r, posts), "text/markdown; charset=utf-8", "md"))
    return PlainTextResponse(body(), media_type=mime,
                             headers={"Content-Disposition": f'attachment; filename="feedlens-{run_id}.{ext}"'})


# ================================================================== agent protocol
class PostsBody(BaseModel):
    posts: list[RawPost] = Field(default_factory=list)


def _clean_posts(posts: list[RawPost]) -> list[RawPost]:
    if len(posts) > settings.max_posts:
        raise HTTPException(413, f"Tối đa {settings.max_posts} bài mỗi lượt.")
    return [p.model_copy(update={"text": p.text[:20_000]}) for p in posts]


@private.get("/agent/next")
def agent_next(user: User = Depends(agent_user)):
    """Agent hỏi việc mỗi vài giây; đồng thời là tín hiệu 'agent đang bật'."""
    db().touch_agent(user.id)
    job = db().claim_next_pending(user.id)
    if not job:
        return {"job": None}
    PROGRESS[job["id"]] = {"phase": "scraping", "done": 0, "target": job["request"]["count"],
                           "message": "Agent đã nhận việc, đang mở trình duyệt…"}
    return {"job": {"id": job["id"], "request": job["request"]}}


class ProgressBody(BaseModel):
    done: int = 0
    target: int = 0
    message: str = Field("", max_length=300)


@private.post("/agent/runs/{run_id}/progress")
def agent_progress(run_id: int, body: ProgressBody, user: User = Depends(agent_user)):
    r = _own_run(run_id, user)
    if r["status"] != "scraping":
        raise HTTPException(409, "Lượt này không còn ở trạng thái đang lướt.")
    db().touch_agent(user.id)
    PROGRESS[run_id] = {"phase": "scraping", **body.model_dump()}
    return {"ok": True}


@private.post("/agent/runs/{run_id}/posts")
def agent_posts(run_id: int, body: PostsBody, user: User = Depends(agent_user)):
    r = _own_run(run_id, user)
    if r["status"] != "scraping":
        raise HTTPException(409, "Lượt này không còn ở trạng thái đang lướt.")
    start_analysis(db(), run_id, RunRequest(**r["request"]), _clean_posts(body.posts), user.id)
    return {"ok": True}


class FailBody(BaseModel):
    error: str = Field(max_length=2000)


@private.post("/agent/runs/{run_id}/fail")
def agent_fail(run_id: int, body: FailBody, user: User = Depends(agent_user)):
    _own_run(run_id, user)
    fail_run(db(), run_id, f"Agent báo lỗi: {body.error}")
    return {"ok": True}


class IngestBody(BaseModel):
    request: RunRequest
    posts: list[RawPost] = Field(..., min_length=1)


@private.post("/ingest")
def ingest(body: IngestBody, user: User = Depends(current_user)):
    """`feedlens push`: gửi một lượt đã lướt xong, không qua hàng đợi."""
    _check_ai(body.request, user.id)
    return {"id": start_ingest(db(), body.request, _clean_posts(body.posts), user.id)}


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
