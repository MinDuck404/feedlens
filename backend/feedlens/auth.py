"""Xác thực nhiều người dùng.

- Web: đăng ký/đăng nhập email + mật khẩu -> token phiên ký HMAC (hết hạn sau 14 ngày).
- Agent trên máy: token riêng `fla_...` do user tự tạo trong phần Cài đặt; DB chỉ lưu hash.
- Chế độ local: không đăng nhập, mọi request thuộc về một user ngầm định.
Chế độ cloud mà thiếu FEEDLENS_SECRET thì khóa toàn bộ API (fail closed).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request

from .config import settings
from .crypto import AGENT_PREFIX, sha256

TOKEN_TTL = 14 * 24 * 3600


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    via_agent: bool = False


def _sign(payload: str) -> str:
    return hmac.new(settings.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_token(user_id: int) -> str:
    payload = f"{user_id}.{int(time.time()) + TOKEN_TTL}"
    return base64.urlsafe_b64encode(f"{payload}.{_sign(payload)}".encode()).decode()


def _session_user_id(token: str) -> int | None:
    try:
        uid, exp, sig = base64.urlsafe_b64decode(token.encode()).decode().split(".")
    except Exception:  # noqa: BLE001
        return None
    if not hmac.compare_digest(sig, _sign(f"{uid}.{exp}")) or int(exp) < time.time():
        return None
    return int(uid)


def misconfigured() -> str | None:
    if not settings.is_cloud:
        return None
    if not settings.secret:
        return "Server chưa cấu hình FEEDLENS_SECRET — API bị khóa để bảo vệ dữ liệu."
    if len(settings.secret) < 32:
        return "FEEDLENS_SECRET cần ít nhất 32 ký tự."
    return None


def current_user(request: Request, authorization: str = Header(default="")) -> CurrentUser:
    """Dependency: trả về user đang gọi API."""
    db = request.app.state.db
    if not settings.auth_enabled:
        return CurrentUser(id=db.local_user_id(), email="local")
    if err := misconfigured():
        raise HTTPException(503, err)
    token = authorization.removeprefix("Bearer ").strip()
    if token.startswith(AGENT_PREFIX):
        u = db.user_by_agent_hash(sha256(token))
        if u:
            return CurrentUser(id=u.id, email=u.email, via_agent=True)
    elif token and (uid := _session_user_id(token)) is not None:
        u = db.get_user(uid)
        if u:
            return CurrentUser(id=u.id, email=u.email)
    raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")


def agent_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if settings.auth_enabled and not user.via_agent:
        raise HTTPException(403, "Endpoint này chỉ dành cho agent (token fla_...).")
    return user
