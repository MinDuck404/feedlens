"""Lớp AI đa nhà cung cấp. Mọi provider cần: trả JSON đúng schema và liệt kê model."""
from __future__ import annotations

from .base import AIError, AIProvider, ProviderInfo
from .registry import (PROVIDERS, forget_models, get_provider, list_models, pick_default, provider_status,
                       resolve_models, resolve_provider_key, user_keys)

__all__ = ["AIError", "AIProvider", "ProviderInfo", "PROVIDERS", "forget_models", "get_provider",
           "list_models", "pick_default", "provider_status", "resolve_models", "resolve_provider_key", "user_keys"]
