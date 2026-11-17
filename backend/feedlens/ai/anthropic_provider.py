from __future__ import annotations

import json

from .base import AIError, AIProvider, Effort, MAX_OUTPUT_TOKENS, ProviderInfo


class AnthropicProvider(AIProvider):
    info = ProviderInfo(
        key="anthropic", name="Claude", env_key="ANTHROPIC_API_KEY", model_env="ANTHROPIC_MODEL",
        default_model="claude-opus-5-5", key_url="https://console.anthropic.com/settings/keys",
    )

    def __init__(self, model: str | None = None, api_key: str | None = None):
        super().__init__(model, api_key)
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key, max_retries=0) if api_key else anthropic.Anthropic(max_retries=0)

    def complete_json(self, system: str, prompt: str, schema: dict, effort: Effort = "low") -> dict:
        resp = self.client.beta.messages.create(
            model=self.model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            # Nếu model chính từ chối (safety classifier), API tự chạy lại bằng model dự phòng
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            raise AIError("Claude từ chối xử lý nội dung này")
        if resp.stop_reason == "max_tokens":
            raise AIError("Phản hồi của Claude bị cắt (max_tokens)")
        return json.loads(next(b.text for b in resp.content if b.type == "text"))

    def list_models(self) -> list[str]:
        return [m.id for m in self.client.models.list(limit=100)]  # API trả mới nhất trước
