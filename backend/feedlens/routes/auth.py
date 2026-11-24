"""Auth routes."""
from __future__ import annotations

import feedlens.db.repos.users as _ref_db_repos_users

from collections import defaultdict, deque

import time
import re
import feedlens.browser.profiles as browser_profiles

import feedlens.core.auth as auth_core
import feedlens.core.config as config
import feedlens.core.crypto as crypto
import feedlens.db as database_module
import fastapi as fastapi
import feedlens.core.models as models
import feedlens.routes.agent as agent_routes
import feedlens.routes.dependencies as dependencies

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from feedlens.core.auth import CurrentUser as User
from feedlens.core.auth import current_user

public = APIRouter()
private = APIRouter()


_attempts: dict[str, deque] = defaultdict(deque)

LOGIN_WINDOW, LOGIN_MAX_FAILS = 15 * 60, 10

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _throttle(*keys: str) -> None:
    now = time.time()
    for k in keys:
        q = _attempts[k]
        while q and q[0] < now - LOGIN_WINDOW:
            q.popleft()
        if len(q) >= LOGIN_MAX_FAILS:
            raise fastapi.HTTPException(429, "Thử quá nhiều lần. Đợi 15 phút rồi thử lại.")

def _fail_attempt(*keys: str) -> None:
    for k in keys:
        _attempts[k].append(time.time())


@public.get("/health")
def health():
    out = {"ok": True, "mode": config.settings.mode, "db": dependencies.db().engine.dialect.name}
    if config.settings.is_cloud and config.settings.server_scrape:
        out["browser"] = _browser_installed()
    return out


def _browser_installed() -> bool:
    return not browser_profiles.browser_status(headless=True)["missing"]


@public.get("/meta")
def meta():
    return {"mode": config.settings.mode, "auth_required": config.settings.auth_enabled, "config_error": auth_core.misconfigured(),
            "config_error_code": "error.config" if auth_core.misconfigured() else None,
            "signup_open": config.settings.allow_signup, "server_scrape": config.settings.is_cloud and config.settings.server_scrape,
            "categories": models.CATEGORIES, "max_posts": config.settings.max_posts}


class Credentials(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


@public.post("/auth/register")
def register(body: Credentials, request: Request):
    if err := auth_core.misconfigured():
        raise fastapi.HTTPException(503, err)
    if not config.settings.is_cloud:
        raise fastapi.HTTPException(409, "Chế độ local không cần tài khoản.")
    if not config.settings.allow_signup:
        raise fastapi.HTTPException(403, "Server này đang đóng đăng ký.")
    ip = request.client.host if request.client else "?"
    _throttle(f"reg:{ip}")
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise fastapi.HTTPException(400, "Email không hợp lệ.")
    if len(body.password) < 8:
        raise fastapi.HTTPException(400, "Mật khẩu cần ít nhất 8 ký tự.")
    _fail_attempt(f"reg:{ip}")  # giới hạn số tài khoản tạo từ một IP
    try:
        uid = dependencies.db().create_user(email, crypto.hash_password(body.password))
    except _ref_db_repos_users.EmailTaken:
        raise fastapi.HTTPException(409, "Email này đã có tài khoản. Hãy đăng nhập.")
    return {"token": auth_core.issue_token(uid), "email": email}


@public.post("/auth/login")
def login(body: Credentials, request: Request):
    if err := auth_core.misconfigured():
        raise fastapi.HTTPException(503, err)
    if not config.settings.is_cloud:
        return {"token": "", "email": "local"}
    ip = request.client.host if request.client else "?"
    email = body.email.strip().lower()
    _throttle(f"ip:{ip}", f"email:{email}")
    u = dependencies.db().get_user_by_email(email)
    if not u or not crypto.verify_password(body.password, u.password_hash):
        _fail_attempt(f"ip:{ip}", f"email:{email}")
        raise fastapi.HTTPException(401, "Sai email hoặc mật khẩu.")
    return {"token": auth_core.issue_token(u.id), "email": u.email}


@private.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email, "agent": agent_routes._agent_info(user.id)}
