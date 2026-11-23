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
from .analyzer import HeuristicAnalyzer, estimate_classification_requests_for_count
from .ai import (PROVIDERS, forget_models, list_models, pick_default, provider_status, resolve_provider_key,
                 user_keys)
from .auth import CurrentUser, agent_user, current_user, issue_token, misconfigured
from .config import BACKEND_DIR, settings
from .crypto import encrypt, hash_password, key_hint, new_agent_token, sha256, verify_password
from .db import Database, EmailTaken
from .export import to_csv, to_json, to_markdown
from .models import CATEGORIES, RawPost, RunRequest
from .messages import error_code, progress_message
from .job_profile import load_profile
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


# ================================================================== public
@public.get("/health")
def health():
    out = {"ok": True, "mode": settings.mode, "db": db().engine.dialect.name}
    if settings.is_cloud and settings.server_scrape:
        out["browser"] = _browser_installed()
    return out


def _browser_installed() -> bool:
    return not browser.browser_status(headless=True)["missing"]


@public.get("/meta")
def meta():
    return {"mode": settings.mode, "auth_required": settings.auth_enabled, "config_error": misconfigured(),
            "config_error_code": "error.config" if misconfigured() else None,
            "signup_open": settings.allow_signup, "server_scrape": settings.is_cloud and settings.server_scrape,
            "categories": CATEGORIES, "max_posts": settings.max_posts}


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


PREFS_MAX_BYTES = 64_000


@private.get("/preferences")
def get_preferences(user: User = Depends(current_user)):
    return db().get_preferences(user.id)


@private.put("/preferences")
async def put_preferences(request: Request, user: User = Depends(current_user)):
    """Lưu cài đặt của form "Lướt mới" và danh sách group. Frontend quyết định cấu trúc; server chỉ giới hạn kích thước."""
    raw = await request.body()
    if len(raw) > PREFS_MAX_BYTES:
        raise HTTPException(413, "Cài đặt quá lớn.")
    try:
        prefs = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "JSON không hợp lệ.")
    if not isinstance(prefs, dict):
        raise HTTPException(400, "Cài đặt phải là một object JSON.")
    db().set_preferences(user.id, prefs)
    return {"ok": True}


# ================================================================== cookie để lướt trên server
def _session_dict(r) -> dict:
    return {"platform": r.platform, "hint": r.hint, "saved_at": r.saved_at.isoformat(),
            "status": r.status, "status_message": r.status_message,
            "status_message_code": {"ok": "ck.statusOk", "invalid": "ck.statusInvalid"}.get(r.status, "ck.statusUnchecked"),
            "checked_at": r.checked_at.isoformat() if r.checked_at else None}


def _server_scrape_on():
    if not (settings.is_cloud and settings.server_scrape):
        raise HTTPException(409, "Chế độ lướt trên server chỉ có ở bản cloud và đang bị tắt.")


@private.get("/sessions")
def list_sessions(user: User = Depends(current_user)):
    return [_session_dict(r) for r in db().list_sessions(user.id)]


class CookieBody(BaseModel):
    cookies: str = Field(min_length=10, max_length=200_000)


@private.put("/sessions/{p}")
def save_session(p: str, body: CookieBody, user: User = Depends(current_user)):
    """Nhận cookie (dán trên web hoặc `feedlens cookies push`), kiểm tra định dạng, mã hóa rồi lưu."""
    _server_scrape_on()
    _platform_or_404(p)
    try:
        cookies = parse_cookies(body.cookies, p)
    except CookieError as e:
        raise HTTPException(400, str(e))
    db().upsert_session(user.id, p, encrypt(json.dumps(cookies)), cookie_hint(cookies, p))
    return _session_dict(db().get_session(user.id, p))


@private.delete("/sessions/{p}")
def delete_session(p: str, user: User = Depends(current_user)):
    _platform_or_404(p)
    db().delete_session(user.id, p)
    return {"ok": True}


@private.post("/sessions/{p}/check")
async def check_session_cookie(p: str, user: User = Depends(current_user)):
    """Thử mở trang chủ bằng cookie từ server (mất ~10 giây, chờ nếu server đang lướt)."""
    from .crypto import decrypt
    from .server_runner import check_cookies

    _server_scrape_on()
    row = db().get_session(user.id, p)
    cookies = json.loads(decrypt(row.ciphertext) or "null") if row else None
    if not cookies:
        raise HTTPException(404, "Chưa có cookie cho nền tảng này.")
    try:
        ok, msg = await run_in_threadpool(check_cookies, p, cookies)
    except Exception as e:  # noqa: BLE001 — trình duyệt trên server lỗi (hết RAM...)
        raise HTTPException(502, f"Server không mở được trình duyệt để kiểm tra: {str(e)[:200]}")
    db().set_session_status(user.id, p, "ok" if ok else "invalid", msg)
    return _session_dict(db().get_session(user.id, p))


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


class DefaultAIBody(BaseModel):
    provider: str = Field(max_length=40)


@private.put("/ai/default")
def set_default_ai(body: DefaultAIBody, user: User = Depends(current_user)):
    _provider_or_404(body.provider)
    try:
        resolve_provider_key(body.provider, user_keys(db(), user.id))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db().set_default_ai(user.id, body.provider)
    return {"ok": True}


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
    if db().get_default_ai(user.id) == p:
        db().set_default_ai(user.id, None)
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
def _check_platform(p: str) -> bool | None:
    _session_checks[p] = "checking"
    try:
        with _platform_locks[p]:
            ok = browser.check_session(p)
            _session_cache[p] = ok
            return ok
    finally:
        _session_checks.pop(p, None)


def _start_session_checks() -> None:
    global _session_started
    with _session_start_lock:
        if _session_started or settings.is_cloud:
            return
        _session_started = True
        platforms = [p for p in browser.PLATFORMS if browser.profile_dir(p).exists() and p not in _session_cache]
        _session_checks.update({p: "queued" for p in platforms})
    def worker():
        for p in platforms:
            try:
                _check_platform(p)
            except Exception:
                # Network/browser failures leave the session unknown, not expired.
                _session_cache.pop(p, None)
    threading.Thread(target=worker, daemon=True).start()


@private.get("/platforms")
def platforms(user: User = Depends(current_user)):
    if settings.is_cloud:
        return []
    _start_session_checks()
    browser_states = browser.browser_statuses()
    return [{"key": k, "name": v.name, "logged_in": _session_cache.get(k),
             "has_profile": browser.profile_dir(k).exists(),
             "checking": k in _session_checks,
             **browser_states[k],
             "login_error": _login_errors.get(k),
             "login_error_code": ("error.browser_missing" if error_code(_login_errors[k]) == "error.browser_missing"
                                  else "error.browser_failed") if k in _login_errors else None,
             "login_state": _login_state.get(k, "idle")} for k, v in browser.PLATFORMS.items()]


@private.post("/platforms/{p}/check")
async def check(p: str, user: User = Depends(current_user)):
    _local_only()
    _platform_or_404(p)
    await run_in_threadpool(browser.clear_browser_status_cache)
    state = await run_in_threadpool(browser.browser_status, p)
    ok = None if state["missing"] else await run_in_threadpool(_check_platform, p)
    return {"logged_in": ok, **state}


@private.post("/platforms/{p}/login")
def login_platform(p: str, user: User = Depends(current_user)):
    _local_only()
    _platform_or_404(p)
    if _login_state.get(p) != "waiting":
        browser.clear_browser_status_cache()
        try:
            browser.detect_browser(p)
        except browser.BrowserNotFoundError as e:
            raise HTTPException(503, str(e)) from e
        with _login_finish_lock:
            if _login_state.get(p) == "waiting":
                return {"status": "waiting"}
            _login_errors.pop(p, None)
            _login_state[p] = "waiting"
            finish_event = _login_finish[p] = threading.Event()
        def worker():
            try:
                with _platform_locks[p]:
                    _session_cache[p] = browser.interactive_login(
                        p, on_window_closed=lambda: _session_checks.__setitem__(p, "checking"), finish_event=finish_event)
            except Exception as e:
                _login_errors[p] = str(e)[:1500]
                _session_cache[p] = None
            finally:
                browser.clear_browser_status_cache()
                with _login_finish_lock:
                    _session_checks.pop(p, None)
                    _login_state[p] = "idle"
                    _login_finish.pop(p, None)
        threading.Thread(target=worker, daemon=True).start()
    return {"status": "waiting"}


@private.post("/platforms/{p}/login/finish")
def finish_login_platform(p: str, user: User = Depends(current_user)):
    _local_only()
    _platform_or_404(p)
    with _login_finish_lock:
        event = _login_finish.get(p)
        if _login_state.get(p) != "waiting" or event is None:
            raise HTTPException(409, "Không có cửa sổ đăng nhập đang chờ.")
        _session_checks[p] = "checking"
        event.set()  # The worker owns the process and platform lock; it closes and verifies the session.
    return {"status": "checking"}


@private.post("/platforms/{p}/logout")
def logout_platform(p: str, user: User = Depends(current_user)):
    _local_only()
    _platform_or_404(p)
    with _platform_locks[p]:
        browser.logout(p)
        _session_cache[p] = False
        _login_errors.pop(p, None)
        browser.clear_browser_status_cache()
    return {"ok": True}


# ================================================================== runs
def _check_ai(req: RunRequest, user_id: int):
    try:
        return resolve_provider_key(preferred_provider(db(), user_id, req.ai_provider), user_keys(db(), user_id))
    except ValueError as e:
        raise HTTPException(400, str(e))


def _own_run(run_id: int, user: User) -> dict:
    r = db().get_run(run_id, user.id)
    if not r:
        raise HTTPException(404, "Không tìm thấy lượt này.")
    return r


@private.post("/runs")
def create_run(req: RunRequest, user: User = Depends(current_user)):
    from .source_modes import normalize
    try:
        normalize(req)
    except ValueError as exc:
        raise HTTPException(422, f"Invalid source mode/options: {exc}") from exc
    req = req.model_copy(update={"count": min(req.count, run_cap(req))})
    _check_ai(req, user.id)
    if settings.is_cloud and req.runner == "server":
        if not settings.server_scrape:
            raise HTTPException(403, "Server này đã tắt chế độ lướt bằng cookie. Hãy chạy bằng agent.")
        s = db().get_session(user.id, req.platform)
        if not s:
            raise HTTPException(400, f"Chưa có cookie {req.platform}. Thêm trong Cài đặt → Lướt trên server.")
        if s.status == "invalid":
            raise HTTPException(400, f"Cookie {req.platform} đã hết hiệu lực: {s.status_message} Hãy gửi cookie mới.")
        req = req.model_copy(update={"headless": True})
        run_id = start_server_run(db(), req, user.id)
        return {"id": run_id}
    if settings.is_cloud:
        run_id = db().create_run(req, user.id, status="pending")
        from .pipeline import total_target
        PROGRESS[run_id] = {"phase": "pending", "done": 0, "target": total_target(req), "message": "Đang chờ agent nhận việc…"}
        return {"id": run_id, "agent": _agent_info(user.id)}
    return {"id": start_run(db(), req, user.id)}


@private.get("/runs")
def runs(user: User = Depends(current_user)):
    return [{**r, "progress": progress_message(PROGRESS.get(r["id"])), "error_code": error_code(r["error"], run_error=True, analysis_error=r["status"] == "analysis_failed") if r.get("error") else None} for r in db().list_runs(user.id)]


@private.get("/runs/{run_id}")
def run_detail(run_id: int, user: User = Depends(current_user), posts: bool = True):
    r = _own_run(run_id, user)
    counts = db().analysis_counts(run_id)
    active = r["status"] in {"pending", "queued", "scraping", "analyzing"}
    can_continue = not active and db().can_continue_analysis(run_id)
    analysis_used_ai = r["request"].get("analysis_used_ai", r.get("ai_label") not in {"", HeuristicAnalyzer.label})
    can_reprocess_ai = (not active and analysis_used_ai and r["status"] in {"done", "analysis_failed"}
                        and counts["total"] > 0)
    topic_count = len(db().list_topics(user.id, enabled_only=True)) if not active else 0
    has_cv = load_profile(db(), user.id) is not None if not active else bool(r["request"].get("job_mode"))
    result = {**r, "progress": progress_message(PROGRESS.get(run_id)),
              "posts_version": counts["offline"] + 2 * counts["ai"],
              "analysis_counts": counts,
              "can_continue_analysis": can_continue,
              "can_reanalyze_ai": (not can_continue and not analysis_used_ai and r["status"] == "done"
                                   and counts["total"] > 0),
              "can_reprocess_ai": can_reprocess_ai,
              "reanalyze_requests_estimate": estimate_classification_requests_for_count(
                  counts["total"], r["request"].get("job_mode", False), r["request"].get("keywords", []),
                  r["request"].get("profile", ""), topic_count, has_cv=has_cv),
              "reanalysis_active": bool(r["request"].get("reanalysis_active")),
              "error_code": error_code(r["error"], run_error=True, analysis_error=r["status"] == "analysis_failed") if r.get("error") else None}
    if posts:
        result["posts"] = [p.model_dump() for p in db().get_posts(run_id, include_raw=True)]
    return result


class AnalysisBody(BaseModel):
    ai_provider: str = Field("auto", max_length=40)
    ai_model: str = Field("", max_length=200)
    mode: Literal["continue", "reanalyze_all"] = "continue"


@private.post("/runs/{run_id}/analysis/stop", status_code=202)
def stop_analysis(run_id: int, body: AnalysisBody | None = None, user: User = Depends(current_user)):
    run = _own_run(run_id, user)
    if run["status"] != "analyzing":
        raise HTTPException(409, "AI analysis is not running.")
    replacement = None
    if body is not None:
        if body.mode != "continue":
            raise HTTPException(422, "Model changes must continue saved analysis.")
        replacement = RunRequest(**{**run["request"], "ai_provider": body.ai_provider, "ai_model": body.ai_model})
        _check_ai(replacement, user.id)
    if not request_stop(run_id, replacement):
        raise HTTPException(409, "AI analysis is not running or is already stopping.")
    return {"ok": True, "stopping": True, "will_continue": replacement is not None}


@private.post("/runs/{run_id}/analysis")
def retry_analysis(run_id: int, body: AnalysisBody, user: User = Depends(current_user)):
    r = _own_run(run_id, user)
    raw = db().get_analysis_posts(run_id)
    reanalyze_all = body.mode == "reanalyze_all"
    if reanalyze_all and (r["status"] not in {"done", "analysis_failed"} or not raw):
        raise HTTPException(409, "Lượt này chưa có bài đã lưu để phân tích lại bằng AI.")
    if not db().can_continue_analysis(run_id, reanalyze_all=reanalyze_all):
        raise HTTPException(409, "Lượt này không có bài chờ phân tích lại.")
    req = RunRequest(**{**r["request"], "ai_provider": body.ai_provider, "ai_model": body.ai_model})
    resolved_provider = _check_ai(req, user.id)
    if reanalyze_all and resolved_provider == "offline":
        raise HTTPException(400, "Chưa có API key AI. Thêm key trong phần Cài đặt để phân tích bằng AI.")
    if not db().claim_analysis(run_id, req):
        raise HTTPException(409, "Lượt này đang được phân tích.")
    if reanalyze_all:
        request = {**req.model_dump(), "analysis_used_ai": True, "reanalysis_active": True}
        if "scrape_report" in r["request"]:
            request["scrape_report"] = r["request"]["scrape_report"]
        db().save_raw_posts(run_id, raw)  # Seed legacy runs before only_new filtering in start_analysis.
        db().mark_posts_pending(run_id)
        db().update_run(run_id, request=request)
        start_analysis(db(), run_id, req, raw, user.id, reanalyze_all=True)
    else:
        metadata = {key: r["request"][key] for key in ("scrape_report", "analysis_used_ai", "reanalysis_active")
                    if key in r["request"]}
        db().update_run(run_id, request={**req.model_dump(), **metadata})
        db().save_raw_posts(run_id, raw)  # Seed legacy runs before only_new filtering in start_analysis.
        start_analysis(db(), run_id, req, raw, user.id)
    return {"ok": True}


@private.delete("/runs/{run_id}")
def delete_run(run_id: int, user: User = Depends(current_user)):
    if not db().delete_run(run_id, user.id):
        raise HTTPException(404, "Không tìm thấy lượt này.")
    PROGRESS.pop(run_id, None)
    return {"ok": True}


@private.get("/runs/{run_id}/export")
def export(run_id: int, fmt: str = "md", user: User = Depends(current_user)):
    r = _own_run(run_id, user)
    posts = db().get_posts(run_id, include_raw=True)
    body, mime, ext = {
        "csv": (lambda: to_csv(posts, r), "text/csv; charset=utf-8", "csv"),
        "json": (lambda: to_json(r, posts), "application/json", "json"),
    }.get(fmt, (lambda: to_markdown(r, posts), "text/markdown; charset=utf-8", "md"))
    return PlainTextResponse(body(), media_type=mime,
                             headers={"Content-Disposition": f'attachment; filename="feedlens-{run_id}.{ext}"'})


# ================================================================== agent protocol
class PostsBody(BaseModel):
    posts: list[RawPost] = Field(default_factory=list)


def _clean_posts(posts: list[RawPost], cap: int) -> list[RawPost]:
    if len(posts) > cap:
        raise HTTPException(413, f"Tối đa {cap} bài mỗi lượt.")
    return [p.model_copy(update={"text": p.text[:20_000]}) for p in posts]


@private.get("/agent/next")
def agent_next(user: User = Depends(agent_user), protocol_version: int = Query(1, ge=1, le=2)):
    """Agent hỏi việc mỗi vài giây; đồng thời là tín hiệu 'agent đang bật'."""
    db().touch_agent(user.id)
    job = db().claim_next_pending(user.id, protocol_version=protocol_version)
    if not job:
        return {"job": None}
    from .pipeline import total_target
    PROGRESS[job["id"]] = {"phase": "scraping", "done": 0, "target": total_target(RunRequest(**job["request"])),
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
    req = RunRequest(**r["request"])
    start_analysis(db(), run_id, req, _clean_posts(body.posts, run_cap(req)), user.id)
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
    return {"id": start_ingest(db(), body.request, _clean_posts(body.posts, run_cap(body.request)), user.id)}


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
