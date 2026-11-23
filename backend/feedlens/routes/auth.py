"""Auth routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from ..auth import CurrentUser as User, current_user
from .. import api

public = APIRouter()
private = APIRouter()


@public.get("/health")
def health():
    out = {"ok": True, "mode": api.settings.mode, "db": api.db().engine.dialect.name}
    if api.settings.is_cloud and api.settings.server_scrape:
        out["browser"] = api._browser_installed()
    return out


def _browser_installed() -> bool:
    return not api.browser.browser_status(headless=True)["missing"]


@public.get("/meta")
def meta():
    return {"mode": api.settings.mode, "auth_required": api.settings.auth_enabled, "config_error": api.misconfigured(),
            "config_error_code": "error.config" if api.misconfigured() else None,
            "signup_open": api.settings.allow_signup, "server_scrape": api.settings.is_cloud and api.settings.server_scrape,
            "categories": api.CATEGORIES, "max_posts": api.settings.max_posts}


class Credentials(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


@public.post("/auth/register")
def register(body: Credentials, request: Request):
    if err := api.misconfigured():
        raise api.HTTPException(503, err)
    if not api.settings.is_cloud:
        raise api.HTTPException(409, "Chế độ local không cần tài khoản.")
    if not api.settings.allow_signup:
        raise api.HTTPException(403, "Server này đang đóng đăng ký.")
    ip = request.client.host if request.client else "?"
    api._throttle(f"reg:{ip}")
    email = body.email.strip().lower()
    if not api.EMAIL_RE.match(email):
        raise api.HTTPException(400, "Email không hợp lệ.")
    if len(body.password) < 8:
        raise api.HTTPException(400, "Mật khẩu cần ít nhất 8 ký tự.")
    api._fail_attempt(f"reg:{ip}")  # giới hạn số tài khoản tạo từ một IP
    try:
        uid = api.db().create_user(email, api.hash_password(body.password))
    except api.EmailTaken:
        raise api.HTTPException(409, "Email này đã có tài khoản. Hãy đăng nhập.")
    return {"token": api.issue_token(uid), "email": email}


@public.post("/auth/login")
def login(body: Credentials, request: Request):
    if err := api.misconfigured():
        raise api.HTTPException(503, err)
    if not api.settings.is_cloud:
        return {"token": "", "email": "local"}
    ip = request.client.host if request.client else "?"
    email = body.email.strip().lower()
    api._throttle(f"ip:{ip}", f"email:{email}")
    u = api.db().get_user_by_email(email)
    if not u or not api.verify_password(body.password, u.password_hash):
        api._fail_attempt(f"ip:{ip}", f"email:{email}")
        raise api.HTTPException(401, "Sai email hoặc mật khẩu.")
    return {"token": api.issue_token(u.id), "email": u.email}


@private.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email, "agent": api._agent_info(user.id)}
