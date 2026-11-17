from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

Effort = Literal["low", "medium", "high"]
MAX_OUTPUT_TOKENS = 8192  # Shared with quota reservations; provider output must not exceed the estimate.


class AIError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderInfo:
    key: str
    name: str
    env_key: str          # biến môi trường (chỉ dùng ở chế độ local)
    model_env: str
    default_model: str
    key_url: str          # nơi lấy API key


class AIProvider(ABC):
    info: ProviderInfo

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.getenv(self.info.model_env) or self.info.default_model
        self.api_key = api_key

    @abstractmethod
    def complete_json(self, system: str, prompt: str, schema: dict, effort: Effort = "low") -> dict:
        """Gửi prompt, ép kết quả theo JSON schema, trả về dict đã parse."""

    @abstractmethod
    def list_models(self) -> list[str]:
        """Danh sách model dùng được để sinh văn bản, mới nhất trước. Cũng dùng để kiểm tra key."""
