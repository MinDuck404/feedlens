"""Platforms routes."""
from __future__ import annotations


import threading
import json
import feedlens.browser.profiles as browser_profiles

import feedlens.core.config as config
import feedlens.browser.cookies as cookie_helpers
import feedlens.core.crypto as crypto
import fastapi as fastapi
import fastapi.concurrency as fastapi_concurrency
import feedlens.core.messages as messages
import feedlens.routes.dependencies as dependencies
import feedlens.runs.pipeline as run_pipeline

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from feedlens.core.auth import CurrentUser as User
from feedlens.core.auth import current_user

private = APIRouter()


_login_state: dict[str, str] = {}

_login_errors: dict[str, str] = {}

_login_finish: dict[str, threading.Event] = {}

_login_finish_lock = threading.Lock()

_session_cache: dict[str, bool | None] = {}

_session_checks: dict[str, str] = {}

_session_start_lock = threading.Lock()

_session_started = False

def _local_only():
    if config.settings.is_cloud:
        raise fastapi.HTTPException(409, "Server cloud không có trình duyệt. Hãy bật agent trên máy bạn.")

def _platform_or_404(p: str):
    if p not in browser_profiles.PLATFORMS:
        raise fastapi.HTTPException(404, "Nền tảng không hỗ trợ")
    return browser_profiles.PLATFORMS[p]


def _session_dict(r) -> dict:
    return {"platform": r.platform, "hint": r.hint, "saved_at": r.saved_at.isoformat(),
            "status": r.status, "status_message": r.status_message,
            "status_message_code": {"ok": "ck.statusOk", "invalid": "ck.statusInvalid"}.get(r.status, "ck.statusUnchecked"),
            "checked_at": r.checked_at.isoformat() if r.checked_at else None}


def _server_scrape_on():
    if not (config.settings.is_cloud and config.settings.server_scrape):
        raise fastapi.HTTPException(409, "Chế độ lướt trên server chỉ có ở bản cloud và đang bị tắt.")


@private.get("/sessions")
def list_sessions(user: User = Depends(current_user)):
    return [_session_dict(r) for r in dependencies.db().list_sessions(user.id)]


class CookieBody(BaseModel):
    cookies: str = Field(min_length=10, max_length=200_000)


@private.put("/sessions/{p}")
def save_session(p: str, body: CookieBody, user: User = Depends(current_user)):
    """Nhận cookie (dán trên web hoặc `feedlens cookies push`), kiểm tra định dạng, mã hóa rồi lưu."""
    _server_scrape_on()
    _platform_or_404(p)
    try:
        cookies = cookie_helpers.parse_cookies(body.cookies, p)
    except cookie_helpers.CookieError as e:
        raise fastapi.HTTPException(400, str(e))
    dependencies.db().upsert_session(user.id, p, crypto.encrypt(json.dumps(cookies)), cookie_helpers.cookie_hint(cookies, p))
    return _session_dict(dependencies.db().get_session(user.id, p))


@private.delete("/sessions/{p}")
def delete_session(p: str, user: User = Depends(current_user)):
    _platform_or_404(p)
    dependencies.db().delete_session(user.id, p)
    return {"ok": True}


@private.post("/sessions/{p}/check")
async def check_session_cookie(p: str, user: User = Depends(current_user)):
    """Thử mở trang chủ bằng cookie từ server (mất ~10 giây, chờ nếu server đang lướt)."""
    from feedlens.core.crypto import decrypt
    from feedlens.runs.server_runner import check_cookies

    _server_scrape_on()
    row = dependencies.db().get_session(user.id, p)
    cookies = json.loads(decrypt(row.ciphertext) or "null") if row else None
    if not cookies:
        raise fastapi.HTTPException(404, "Chưa có cookie cho nền tảng này.")
    try:
        ok, msg = await fastapi_concurrency.run_in_threadpool(check_cookies, p, cookies)
    except Exception as e:  # noqa: BLE001 — trình duyệt trên server lỗi (hết RAM...)
        raise fastapi.HTTPException(502, f"Server không mở được trình duyệt để kiểm tra: {str(e)[:200]}")
    dependencies.db().set_session_status(user.id, p, "ok" if ok else "invalid", msg)
    return _session_dict(dependencies.db().get_session(user.id, p))


def _check_platform(p: str) -> bool | None:
    _session_checks[p] = "checking"
    try:
        with run_pipeline._platform_locks[p]:
            ok = browser_profiles.check_session(p)
            _session_cache[p] = ok
            return ok
    finally:
        _session_checks.pop(p, None)


def _start_session_checks() -> None:
    global _session_started
    with _session_start_lock:
        if _session_started or config.settings.is_cloud:
            return
        _session_started = True
        platforms = [p for p in browser_profiles.PLATFORMS if browser_profiles.profile_dir(p).exists() and p not in _session_cache]
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
    if config.settings.is_cloud:
        return []
    _start_session_checks()
    browser_states = browser_profiles.browser_statuses()
    return [{"key": k, "name": v.name, "logged_in": _session_cache.get(k),
             "has_profile": browser_profiles.profile_dir(k).exists(),
             "checking": k in _session_checks,
             **browser_states[k],
             "login_error": _login_errors.get(k),
             "login_error_code": ("error.browser_missing" if messages.error_code(_login_errors[k]) == "error.browser_missing"
                                  else "error.browser_failed") if k in _login_errors else None,
             "login_state": _login_state.get(k, "idle")} for k, v in browser_profiles.PLATFORMS.items()]


@private.post("/platforms/{p}/check")
async def check(p: str, user: User = Depends(current_user)):
    _local_only()
    _platform_or_404(p)
    await fastapi_concurrency.run_in_threadpool(browser_profiles.clear_browser_status_cache)
    state = await fastapi_concurrency.run_in_threadpool(browser_profiles.browser_status, p)
    ok = None if state["missing"] else await fastapi_concurrency.run_in_threadpool(_check_platform, p)
    return {"logged_in": ok, **state}


@private.post("/platforms/{p}/login")
def login_platform(p: str, user: User = Depends(current_user)):
    _local_only()
    _platform_or_404(p)
    if _login_state.get(p) != "waiting":
        browser_profiles.clear_browser_status_cache()
        try:
            browser_profiles.detect_browser(p)
        except browser_profiles.BrowserNotFoundError as e:
            raise fastapi.HTTPException(503, str(e)) from e
        with _login_finish_lock:
            if _login_state.get(p) == "waiting":
                return {"status": "waiting"}
            _login_errors.pop(p, None)
            _login_state[p] = "waiting"
            finish_event = _login_finish[p] = threading.Event()
        def worker():
            try:
                with run_pipeline._platform_locks[p]:
                    _session_cache[p] = browser_profiles.interactive_login(
                        p, on_window_closed=lambda: _session_checks.__setitem__(p, "checking"), finish_event=finish_event)
            except Exception as e:
                _login_errors[p] = str(e)[:1500]
                _session_cache[p] = None
            finally:
                browser_profiles.clear_browser_status_cache()
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
            raise fastapi.HTTPException(409, "Không có cửa sổ đăng nhập đang chờ.")
        _session_checks[p] = "checking"
        event.set()  # The worker owns the process and platform lock; it closes and verifies the session.
    return {"status": "checking"}


@private.post("/platforms/{p}/logout")
def logout_platform(p: str, user: User = Depends(current_user)):
    _local_only()
    _platform_or_404(p)
    with run_pipeline._platform_locks[p]:
        browser_profiles.logout(p)
        _session_cache[p] = False
        _login_errors.pop(p, None)
        browser_profiles.clear_browser_status_cache()
    return {"ok": True}
