from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

Effort = Literal["low", "medium", "high"]


class AIError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderInfo:
    key: str
    name: str
    env_key: str          # biến môi trường chứa API key
    model_env: str
    default_model: str
    suggested_models: tuple[str, ...]


class AIProvider(ABC):
    info: ProviderInfo

    def __init__(self, model: str | None = None):
        import os

        self.model = model or os.getenv(self.info.model_env) or self.info.default_model

    @abstractmethod
    def complete_json(self, system: str, prompt: str, schema: dict, effort: Effort = "low") -> dict:
        """Gửi prompt, ép kết quả theo JSON schema, trả về dict đã parse."""
