from __future__ import annotations

import json

from .base import AIError, AIProvider, Effort, ProviderInfo


class OpenAIProvider(AIProvider):
    info = ProviderInfo(
        key="openai", name="ChatGPT", env_key="OPENAI_API_KEY", model_env="OPENAI_MODEL",
        default_model="gpt-5-mini",
        suggested_models=("gpt-5-mini", "gpt-5", "gpt-4.1-mini"),
    )

    def __init__(self, model: str | None = None):
        super().__init__(model)
        from openai import OpenAI

        self.client = OpenAI()  # đọc OPENAI_API_KEY và OPENAI_BASE_URL từ môi trường

    def complete_json(self, system: str, prompt: str, schema: dict, effort: Effort = "low") -> dict:
        resp = self.client.responses.create(
            model=self.model,
            instructions=system,
            input=prompt,
            text={"format": {"type": "json_schema", "name": "feedlens_output",
                             "schema": schema, "strict": True}},
        )
        if resp.status == "incomplete":
            raise AIError(f"OpenAI trả về chưa hoàn chỉnh: {resp.incomplete_details}")
        text = resp.output_text
        if not text:
            raise AIError("OpenAI không trả nội dung (có thể đã từ chối)")
        return json.loads(text)
