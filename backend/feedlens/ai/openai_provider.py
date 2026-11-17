from __future__ import annotations

import json

from .base import AIError, AIProvider, Effort, MAX_OUTPUT_TOKENS, ProviderInfo

# Model OpenAI không dùng được cho chat/văn bản
_SKIP = ("audio", "realtime", "tts", "transcribe", "image", "embedding", "moderation", "search", "whisper", "dall-e")


class OpenAIProvider(AIProvider):
    info = ProviderInfo(
        key="openai", name="ChatGPT", env_key="OPENAI_API_KEY", model_env="OPENAI_MODEL",
        default_model="gpt-5-mini", key_url="https://platform.openai.com/api-keys",
    )

    def __init__(self, model: str | None = None, api_key: str | None = None):
        super().__init__(model, api_key)
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, max_retries=0) if api_key else OpenAI(max_retries=0)

    def complete_json(self, system: str, prompt: str, schema: dict, effort: Effort = "low") -> dict:
        resp = self.client.responses.create(
            model=self.model,
            max_output_tokens=MAX_OUTPUT_TOKENS,
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

    def list_models(self) -> list[str]:
        models = [m for m in self.client.models.list()
                  if m.id.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")) and not any(s in m.id for s in _SKIP)]
        return [m.id for m in sorted(models, key=lambda m: m.created, reverse=True)]
