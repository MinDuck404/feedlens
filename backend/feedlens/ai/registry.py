from __future__ import annotations

import os

from ..config import settings
from .anthropic_provider import AnthropicProvider
from .base import AIProvider
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider

PROVIDERS: dict[str, type[AIProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}
_EXTRA_KEYS = {"anthropic": ["ANTHROPIC_AUTH_TOKEN"], "gemini": ["GOOGLE_API_KEY"]}


def is_configured(key: str) -> bool:
    cls = PROVIDERS[key]
    return any(os.getenv(k) for k in [cls.info.env_key, *_EXTRA_KEYS.get(key, [])])


def resolve_provider_key(requested: str | None) -> str:
    """'auto'/None -> provider mặc định trong .env, hoặc provider đầu tiên có key, hoặc 'offline'."""
    key = requested or "auto"
    if key == "auto":
        key = settings.default_ai
    if key == "auto":
        key = next((k for k in PROVIDERS if is_configured(k)), "offline")
    if key != "offline" and key not in PROVIDERS:
        raise ValueError(f"Nhà cung cấp AI không hỗ trợ: {key}")
    if key != "offline" and not is_configured(key):
        raise ValueError(f"Chưa có API key cho {PROVIDERS[key].info.name} ({PROVIDERS[key].info.env_key} trong backend/.env)")
    return key


def get_provider(key: str, model: str | None = None) -> AIProvider:
    return PROVIDERS[key](model or None)


def list_providers() -> list[dict]:
    out = []
    for k, cls in PROVIDERS.items():
        i = cls.info
        out.append({"key": k, "name": i.name, "configured": is_configured(k),
                    "default_model": os.getenv(i.model_env) or i.default_model,
                    "models": list(i.suggested_models), "env_key": i.env_key})
    out.append({"key": "offline", "name": "Offline (từ khóa)", "configured": True,
                "default_model": "", "models": [], "env_key": ""})
    return out
