from __future__ import annotations

import json
import os

from .base import AIError, AIProvider, Effort, ProviderInfo


class GeminiProvider(AIProvider):
    info = ProviderInfo(
        key="gemini", name="Gemini", env_key="GEMINI_API_KEY", model_env="GEMINI_MODEL",
        default_model="gemini-2.5-flash",
        suggested_models=("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"),
    )

    def __init__(self, model: str | None = None):
        super().__init__(model)
        from google import genai

        self.genai = genai
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

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
