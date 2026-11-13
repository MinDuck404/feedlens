"""Băm mật khẩu, mã hóa API key, sinh/kiểm tra token. Chỉ dùng thư viện chuẩn + cryptography."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

# ------------------------------------------------------------------ mật khẩu (scrypt)
_N, _R, _P = 2**14, 8, 1


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got.hex(), dk)


# ------------------------------------------------------------------ API key (Fernet, khóa suy ra từ FEEDLENS_SECRET)
def _fernet() -> Fernet:
    if not settings.secret:
        raise RuntimeError("Thiếu FEEDLENS_SECRET để mã hóa API key")
    raw = hashlib.sha256(b"feedlens/api-keys/v1:" + settings.secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None  # secret đã đổi -> key cũ không giải mã được


def key_hint(value: str) -> str:
    return f"…{value[-4:]}" if len(value) >= 8 else "…"


# ------------------------------------------------------------------ token
AGENT_PREFIX = "fla_"


def new_agent_token() -> str:
    return AGENT_PREFIX + secrets.token_urlsafe(32)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
