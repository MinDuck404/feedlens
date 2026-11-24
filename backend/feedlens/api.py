"""REST API cho frontend và cho agent chạy trên máy người dùng.

Chế độ local (mặc định): một người dùng ngầm định; API điều khiển trình duyệt trên chính máy này.
Chế độ cloud (FEEDLENS_MODE=cloud): nhiều tài khoản; server không có trình duyệt. Bấm "Bắt đầu lướt"
tạo lượt ở trạng thái `pending`, agent trên máy người dùng (`feedlens agent`) nhận việc, lướt và gửi bài lên.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import browser
from feedlens.analysis.heuristic import HeuristicAnalyzer
from feedlens.analysis.prompts import estimate_classification_requests_for_count
from feedlens.ai.registry import PROVIDERS
from feedlens.ai.registry import forget_models
from feedlens.ai.registry import list_models
from feedlens.ai.registry import pick_default
from feedlens.ai.registry import provider_status
from feedlens.ai.registry import resolve_provider_key
from feedlens.ai.registry import user_keys
from .auth import CurrentUser, agent_user, current_user, issue_token, misconfigured
from .config import BACKEND_DIR, settings
from .crypto import encrypt, hash_password, key_hint, new_agent_token, sha256, verify_password
from .db import Database, EmailTaken
from .export import to_csv, to_json, to_markdown
from .models import CATEGORIES, RawPost, RunRequest
from .messages import error_code, progress_message
from feedlens.jobs.profile import load_profile
from .cookies import CookieError, cookie_hint, parse_cookies
from .pipeline import PROGRESS, _platform_locks, fail_run, request_stop, run_cap, start_analysis, start_ingest, start_run, start_server_run
from .ai.registry import preferred_provider

app = FastAPI(title="FeedLens API", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])
app.state.db = Database(settings.database_url)
app.state.db.fail_interrupted()

@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, exc: StarletteHTTPException):
    return JSONResponse({"detail": exc.detail, "code": error_code(str(exc.detail), exc.status_code)},
                        status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    return JSONResponse({"detail": jsonable_encoder(exc.errors()), "code": "error.validation"}, status_code=422)


public = APIRouter(prefix="/api")
private = APIRouter(prefix="/api")

User = CurrentUser
AGENT_ONLINE_SECONDS = 30
_login_state: dict[str, str] = {}   # platform -> idle | waiting (chỉ local)
_login_errors: dict[str, str] = {}
_login_finish: dict[str, threading.Event] = {}
_login_finish_lock = threading.Lock()
_session_cache: dict[str, bool | None] = {}
_session_checks: dict[str, str] = {}
_session_start_lock = threading.Lock()
_session_started = False
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


# ================================================================== tài khoản + agent


PREFS_MAX_BYTES = 64_000


# Route handlers access shared state through this facade so existing patches keep working.
from .routes.auth import (
    health,
    _browser_installed,
    meta,
    Credentials,
    register,
    login,
    me,
)

from .routes.preferences import (
    get_preferences,
    put_preferences,
)

from .routes.platforms import (
    _session_dict,
    _server_scrape_on,
    list_sessions,
    CookieBody,
    save_session,
    delete_session,
    check_session_cookie,
    _check_platform,
    _start_session_checks,
    platforms,
    check,
    login_platform,
    finish_login_platform,
    logout_platform,
)

from .routes.ai_keys import (
    ai_providers,
    DefaultAIBody,
    set_default_ai,
    KeyBody,
    _provider_or_404,
    save_key,
    delete_key,
    models,
)

from .routes.runs import (
    _check_ai,
    _own_run,
    create_run,
    runs,
    run_detail,
    AnalysisBody,
    stop_analysis,
    retry_analysis,
    delete_run,
    export,
)

from .routes.agent import (
    create_agent_token,
    PostsBody,
    _clean_posts,
    agent_next,
    ProgressBody,
    agent_progress,
    agent_posts,
    FailBody,
    agent_fail,
    IngestBody,
    ingest,
)

from .routes import auth as _auth_routes
public.include_router(_auth_routes.public)
private.include_router(_auth_routes.private)
from .routes import preferences as _preferences_routes
private.include_router(_preferences_routes.private)
from .routes import platforms as _platforms_routes
private.include_router(_platforms_routes.private)
from .routes import ai_keys as _ai_keys_routes
private.include_router(_ai_keys_routes.private)
from .routes import runs as _runs_routes
private.include_router(_runs_routes.private)
from .routes import agent as _agent_routes
private.include_router(_agent_routes.private)

from .ai_keys_api import ai_keys_router
app.include_router(ai_keys_router(db))  # Fixed /order and numeric IDs must precede legacy /{provider}.
app.include_router(public)
app.include_router(private)
from .profile_api import profile_router
app.include_router(profile_router(db, lambda: settings.is_cloud))
from .topics_api import topics_router
app.include_router(topics_router(db))
from .trends_api import trends_router
app.include_router(trends_router(db))
from .search_api import search_router
app.include_router(search_router(db))

# ================================================================== frontend build (chế độ local, tùy chọn)
DIST = BACKEND_DIR.parent / "frontend" / "dist"
if DIST.exists() and not settings.is_cloud:
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        # index.html luôn lấy bản mới, để sau khi cập nhật trình duyệt không giữ giao diện cũ
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
