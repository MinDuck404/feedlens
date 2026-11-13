"""Lớp AI đa nhà cung cấp. Mọi provider chỉ cần một việc: trả JSON đúng schema."""
from __future__ import annotations

from .base import AIProvider, ProviderInfo
from .registry import PROVIDERS, get_provider, list_providers, resolve_provider_key

__all__ = ["AIProvider", "ProviderInfo", "PROVIDERS", "get_provider", "list_providers", "resolve_provider_key"]
