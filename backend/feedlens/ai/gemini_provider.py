from __future__ import annotations

import os

from .base import AIError, AIOutputTruncated, AIProvider, Effort, MAX_OUTPUT_TOKENS, ProviderInfo, decode_output

TIMEOUT_MS = 180_000


class GeminiProvider(AIProvider):
    info = ProviderInfo(
        key="gemini", name="Gemini", env_key="GEMINI_API_KEY", model_env="GEMINI_MODEL",
        default_model="gemini-3.5-flash-lite", key_url="https://aistudio.google.com/apikey",
    )

    def __init__(self, model: str | None = None, api_key: str | None = None):
        super().__init__(model, api_key)
        from google import genai

        self.genai = genai
        self.client = genai.Client(
            api_key=api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
            http_options=genai.types.HttpOptions(timeout=TIMEOUT_MS, retry_options=genai.types.HttpRetryOptions(attempts=1)),
        )

    def complete_json(self, system: str, prompt: str, schema: dict, effort: Effort = "low") -> dict:
        types = self.genai.types
        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                response_mime_type="application/json",
                response_json_schema=schema,
            ),
        )
        reason = resp.candidates[0].finish_reason if resp.candidates else "unknown"
        if reason == "MAX_TOKENS":
            raise AIOutputTruncated("Gemini output reached MAX_TOKENS")
        if not resp.text:
            raise AIError(f"Gemini không trả nội dung (finish_reason={reason})")
        return decode_output(resp.text)

    def list_models(self) -> list[str]:
        out = []
        for m in self.client.models.list():
            name = (m.name or "").removeprefix("models/")
            actions = m.supported_actions or []
            if name.startswith("gemini") and "generateContent" in actions and "embedding" not in name:
                out.append(name)
        return sorted(out, reverse=True)
