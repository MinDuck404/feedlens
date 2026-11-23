"""Platforms routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from ..auth import CurrentUser as User, current_user
from .. import api

private = APIRouter()


def _session_dict(r) -> dict:
    return {"platform": r.platform, "hint": r.hint, "saved_at": r.saved_at.isoformat(),
            "status": r.status, "status_message": r.status_message,
            "status_message_code": {"ok": "ck.statusOk", "invalid": "ck.statusInvalid"}.get(r.status, "ck.statusUnchecked"),
            "checked_at": r.checked_at.isoformat() if r.checked_at else None}


def _server_scrape_on():
    if not (api.settings.is_cloud and api.settings.server_scrape):
        raise api.HTTPException(409, "Chế độ lướt trên server chỉ có ở bản cloud và đang bị tắt.")


@private.get("/sessions")
def list_sessions(user: User = Depends(current_user)):
    return [api._session_dict(r) for r in api.db().list_sessions(user.id)]


class CookieBody(BaseModel):
    cookies: str = Field(min_length=10, max_length=200_000)


@private.put("/sessions/{p}")
def save_session(p: str, body: CookieBody, user: User = Depends(current_user)):
    """Nhận cookie (dán trên web hoặc `feedlens cookies push`), kiểm tra định dạng, mã hóa rồi lưu."""
    api._server_scrape_on()
    api._platform_or_404(p)
    try:
        cookies = api.parse_cookies(body.cookies, p)
    except api.CookieError as e:
        raise api.HTTPException(400, str(e))
    api.db().upsert_session(user.id, p, api.encrypt(api.json.dumps(cookies)), api.cookie_hint(cookies, p))
    return api._session_dict(api.db().get_session(user.id, p))


@private.delete("/sessions/{p}")
def delete_session(p: str, user: User = Depends(current_user)):
    api._platform_or_404(p)
    api.db().delete_session(user.id, p)
    return {"ok": True}


@private.post("/sessions/{p}/check")
async def check_session_cookie(p: str, user: User = Depends(current_user)):
    """Thử mở trang chủ bằng cookie từ server (mất ~10 giây, chờ nếu server đang lướt)."""
    from ..crypto import decrypt
    from ..server_runner import check_cookies

    api._server_scrape_on()
    row = api.db().get_session(user.id, p)
    cookies = api.json.loads(decrypt(row.ciphertext) or "null") if row else None
    if not cookies:
        raise api.HTTPException(404, "Chưa có cookie cho nền tảng này.")
    try:
        ok, msg = await api.run_in_threadpool(check_cookies, p, cookies)
    except Exception as e:  # noqa: BLE001 — trình duyệt trên server lỗi (hết RAM...)
        raise api.HTTPException(502, f"Server không mở được trình duyệt để kiểm tra: {str(e)[:200]}")
    api.db().set_session_status(user.id, p, "ok" if ok else "invalid", msg)
    return api._session_dict(api.db().get_session(user.id, p))


def _check_platform(p: str) -> bool | None:
    api._session_checks[p] = "checking"
    try:
        with api._platform_locks[p]:
            ok = api.browser.check_session(p)
            api._session_cache[p] = ok
            return ok
    finally:
        api._session_checks.pop(p, None)


def _start_session_checks() -> None:
    with api._session_start_lock:
        if api._session_started or api.settings.is_cloud:
            return
        api._session_started = True
        platforms = [p for p in api.browser.PLATFORMS if api.browser.profile_dir(p).exists() and p not in api._session_cache]
        api._session_checks.update({p: "queued" for p in platforms})
    def worker():
        for p in platforms:
            try:
                api._check_platform(p)
            except Exception:
                # Network/browser failures leave the session unknown, not expired.
                api._session_cache.pop(p, None)
    api.threading.Thread(target=worker, daemon=True).start()


@private.get("/platforms")
def platforms(user: User = Depends(current_user)):
    if api.settings.is_cloud:
        return []
    api._start_session_checks()
    browser_states = api.browser.browser_statuses()
    return [{"key": k, "name": v.name, "logged_in": api._session_cache.get(k),
             "has_profile": api.browser.profile_dir(k).exists(),
             "checking": k in api._session_checks,
             **browser_states[k],
             "login_error": api._login_errors.get(k),
             "login_error_code": ("error.browser_missing" if api.error_code(api._login_errors[k]) == "error.browser_missing"
                                  else "error.browser_failed") if k in api._login_errors else None,
             "login_state": api._login_state.get(k, "idle")} for k, v in api.browser.PLATFORMS.items()]


@private.post("/platforms/{p}/check")
async def check(p: str, user: User = Depends(current_user)):
    api._local_only()
    api._platform_or_404(p)
    await api.run_in_threadpool(api.browser.clear_browser_status_cache)
    state = await api.run_in_threadpool(api.browser.browser_status, p)
    ok = None if state["missing"] else await api.run_in_threadpool(api._check_platform, p)
    return {"logged_in": ok, **state}


@private.post("/platforms/{p}/login")
def login_platform(p: str, user: User = Depends(current_user)):
    api._local_only()
    api._platform_or_404(p)
    if api._login_state.get(p) != "waiting":
        api.browser.clear_browser_status_cache()
        try:
            api.browser.detect_browser(p)
        except api.browser.BrowserNotFoundError as e:
            raise api.HTTPException(503, str(e)) from e
        with api._login_finish_lock:
            if api._login_state.get(p) == "waiting":
                return {"status": "waiting"}
            api._login_errors.pop(p, None)
            api._login_state[p] = "waiting"
            finish_event = api._login_finish[p] = api.threading.Event()
        def worker():
            try:
                with api._platform_locks[p]:
                    api._session_cache[p] = api.browser.interactive_login(
                        p, on_window_closed=lambda: api._session_checks.__setitem__(p, "checking"), finish_event=finish_event)
            except Exception as e:
                api._login_errors[p] = str(e)[:1500]
                api._session_cache[p] = None
            finally:
                api.browser.clear_browser_status_cache()
                with api._login_finish_lock:
                    api._session_checks.pop(p, None)
                    api._login_state[p] = "idle"
                    api._login_finish.pop(p, None)
        api.threading.Thread(target=worker, daemon=True).start()
    return {"status": "waiting"}


@private.post("/platforms/{p}/login/finish")
def finish_login_platform(p: str, user: User = Depends(current_user)):
    api._local_only()
    api._platform_or_404(p)
    with api._login_finish_lock:
        event = api._login_finish.get(p)
        if api._login_state.get(p) != "waiting" or event is None:
            raise api.HTTPException(409, "Không có cửa sổ đăng nhập đang chờ.")
        api._session_checks[p] = "checking"
        event.set()  # The worker owns the process and platform lock; it closes and verifies the session.
    return {"status": "checking"}


@private.post("/platforms/{p}/logout")
def logout_platform(p: str, user: User = Depends(current_user)):
    api._local_only()
    api._platform_or_404(p)
    with api._platform_locks[p]:
        api.browser.logout(p)
        api._session_cache[p] = False
        api._login_errors.pop(p, None)
        api.browser.clear_browser_status_cache()
    return {"ok": True}
