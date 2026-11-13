from __future__ import annotations

import json
import os

from .base import AIError, AIProvider, Effort, ProviderInfo

TIMEOUT_MS = 180_000


class GeminiProvider(AIProvider):
    info = ProviderInfo(
        key="gemini", name="Gemini", env_key="GEMINI_API_KEY", model_env="GEMINI_MODEL",
        default_model="gemini-2.5-flash", key_url="https://aistudio.google.com/apikey",
    )

    def __init__(self, model: str | None = None, api_key: str | None = None):
        super().__init__(model, api_key)
        from google import genai

        self.genai = genai
        self.client = genai.Client(
            api_key=api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
            http_options=genai.types.HttpOptions(timeout=TIMEOUT_MS),  # không để một lời gọi treo vô hạn
        )

    def complete_json(self, system: str, prompt: str, schema: dict, effort: Effort = "low") -> dict:
        types = self.genai.types
        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_json_schema=schema,
            ),
        )
        if not resp.text:
            reason = resp.candidates[0].finish_reason if resp.candidates else "unknown"
            raise AIError(f"Gemini không trả nội dung (finish_reason={reason})")
        return json.loads(resp.text)

    def list_models(self) -> list[str]:
        out = []
        for m in self.client.models.list():
            name = (m.name or "").removeprefix("models/")
            actions = m.supported_actions or []
            if name.startswith("gemini") and "generateContent" in actions and "embedding" not in name:
                out.append(name)
        return sorted(out, reverse=True)
