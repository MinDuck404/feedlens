"""Chọn nhà cung cấp AI theo API key của từng user.

Key lấy từ DB (đã mã hóa, user tự nhập trong phần Cài đặt). Chế độ local còn dùng thêm
key trong biến môi trường; chế độ cloud thì KHÔNG, để người khác không tiêu quota của chủ server.
"""
from __future__ import annotations

import os
import re
import time

from ..config import settings
from ..crypto import decrypt
from .anthropic_provider import AnthropicProvider
from .base import AIProvider
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider

PROVIDERS: dict[str, type[AIProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}
_EXTRA_ENV = {"anthropic": ["ANTHROPIC_AUTH_TOKEN"], "gemini": ["GOOGLE_API_KEY"]}


def _env_key(key: str) -> str | None:
    cls = PROVIDERS[key]
    return next((os.getenv(k) for k in [cls.info.env_key, *_EXTRA_ENV.get(key, [])] if os.getenv(k)), None)


def user_keys(db, user_id: int) -> dict[str, tuple[str, str]]:
    """provider -> (api_key, nguồn: 'db' | 'env')."""
    out: dict[str, tuple[str, str]] = {}
    for row in db.list_keys(user_id):
        val = decrypt(row.ciphertext)
        if val:
            out[row.provider] = (val, "db")
    if not settings.is_cloud:
        for k in PROVIDERS:
            if k not in out and (v := _env_key(k)):
                out[k] = (v, "env")
    return out


def resolve_provider_key(requested: str | None, keys: dict[str, tuple[str, str]]) -> str:
    """'auto'/None -> provider mặc định, hoặc provider đầu tiên có key, hoặc 'offline'."""
    key = requested or "auto"
    if key == "auto" and settings.default_ai in keys:
        key = settings.default_ai
    if key == "auto":
        key = next((k for k in PROVIDERS if k in keys), "offline")
    if key != "offline" and key not in PROVIDERS:
        raise ValueError(f"Nhà cung cấp AI không hỗ trợ: {key}")
    if key != "offline" and key not in keys:
        raise ValueError(f"Chưa có API key cho {PROVIDERS[key].info.name}. Thêm key trong phần Cài đặt.")
    return key


def get_provider(key: str, model: str | None = None, api_key: str | None = None) -> AIProvider:
    return PROVIDERS[key](model or None, api_key)


def provider_status(db, user_id: int) -> list[dict]:
    keys = user_keys(db, user_id)
    hints = {r.provider: r.hint for r in db.list_keys(user_id)}
    out = []
    for k, cls in PROVIDERS.items():
        i = cls.info
        out.append({"key": k, "name": i.name, "configured": k in keys,
                    "source": keys[k][1] if k in keys else None, "hint": hints.get(k, ""),
                    "default_model": os.getenv(i.model_env) or i.default_model, "key_url": i.key_url})
    out.append({"key": "offline", "name": "Offline (từ khóa)", "configured": True, "source": None,
                "hint": "", "default_model": "", "key_url": ""})
    return out


# Cache danh sách model 10 phút theo (user, provider) để không gọi API mỗi lần mở form
_MODEL_CACHE: dict[tuple[int, str], tuple[float, list[str]]] = {}
_TTL = 600


def list_models(user_id: int, key: str, api_key: str, refresh: bool = False) -> list[str]:
    hit = _MODEL_CACHE.get((user_id, key))
    if hit and not refresh and time.time() - hit[0] < _TTL:
        return hit[1]
    models = get_provider(key, api_key=api_key).list_models()
    _MODEL_CACHE[(user_id, key)] = (time.time(), models)
    return models


def forget_models(user_id: int, key: str) -> None:
    _MODEL_CACHE.pop((user_id, key), None)


# Khi user không chọn model:
#  1. model đặt qua biến môi trường (ANTHROPIC_MODEL/OPENAI_MODEL/GEMINI_MODEL), nếu có;
#  2. model mới nhất thuộc dòng "nhanh, rẻ" của nhà cung cấp trong danh sách key dùng được;
#  3. model đầu danh sách; 4. mặc định ghi trong code nếu không lấy được danh sách.
# Không tin vào việc model có tên trong danh sách: Google vẫn liệt kê model đã khóa với user mới.
_PREFER = {"gemini": ("flash",), "openai": ("mini",), "anthropic": ("opus",)}
_AVOID = ("lite", "preview", "exp", "nano", "thinking", "image", "tts", "live")


def _version_key(name: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", name))


def default_candidates(key: str, models: list[str]) -> list[str]:
    """Các model nên thử theo thứ tự khi user để 'Mặc định' (model đầu là lựa chọn chính)."""
    cls = PROVIDERS[key]
    if (env := os.getenv(cls.info.model_env)):
        return [env]
    if not models:
        return [cls.info.default_model]
    good = sorted((m for m in models
                   if any(p in m for p in _PREFER.get(key, ())) and not any(a in m for a in _AVOID)),
                  key=_version_key, reverse=True)
    return good or models[:1]


def pick_default(key: str, models: list[str]) -> str:
    return default_candidates(key, models)[0]


def resolve_models(user_id: int, key: str, api_key: str, requested: str | None, limit: int = 3) -> list[str]:
    """Model sẽ dùng + model dự phòng khi model chính quá tải. User đã chọn model thì không đổi."""
    if requested:
        return [requested]
    try:
        return default_candidates(key, list_models(user_id, key, api_key))[:limit]
    except Exception:  # noqa: BLE001 — không lấy được danh sách thì dùng mặc định cấu hình sẵn
        return default_candidates(key, [])
