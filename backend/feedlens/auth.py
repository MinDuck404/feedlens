"""Xác thực đơn giản cho một người dùng.

- Đăng nhập bằng FEEDLENS_PASSWORD -> nhận token phiên ký HMAC (hết hạn sau 14 ngày).
- Bot ở máy (`feedlens push`) dùng FEEDLENS_API_TOKEN cố định.
Chế độ cloud mà thiếu mật khẩu hoặc secret thì khóa toàn bộ API (fail closed).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import Header, HTTPException

from .config import settings

TOKEN_TTL = 14 * 24 * 3600


def _sign(payload: str) -> str:
    return hmac.new(settings.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_token() -> str:
    exp = str(int(time.time()) + TOKEN_TTL)
    raw = f"{exp}.{_sign(exp)}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _valid_session(token: str) -> bool:
    try:
        exp, sig = base64.urlsafe_b64decode(token.encode()).decode().split(".", 1)
    except Exception:  # noqa: BLE001
        return False
    return hmac.compare_digest(sig, _sign(exp)) and int(exp) > time.time()


def misconfigured() -> str | None:
    if not settings.auth_enabled:
        return None
    missing = [n for n, v in (("FEEDLENS_PASSWORD", settings.password), ("FEEDLENS_SECRET", settings.secret)) if not v]
    if missing:
        return f"Server chưa cấu hình {', '.join(missing)} — API bị khóa để bảo vệ dữ liệu."
    if len(settings.secret) < 32:
        return "FEEDLENS_SECRET cần ít nhất 32 ký tự."
    return None


def check_password(pw: str) -> bool:
    return bool(settings.password) and hmac.compare_digest(pw.encode(), settings.password.encode())


def require_auth(authorization: str = Header(default="")) -> None:
    """Dependency cho mọi endpoint cần đăng nhập."""
    if not settings.auth_enabled:
        return
    if err := misconfigured():
        raise HTTPException(503, err)
    token = authorization.removeprefix("Bearer ").strip()
    if settings.api_token and hmac.compare_digest(token.encode(), settings.api_token.encode()):
        return
    if token and _valid_session(token):
        return
    raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
