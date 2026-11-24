from __future__ import annotations

import os
import threading
import logging

from feedlens.ai.base import AIError
from feedlens.ai.base import AIOutputTruncated
from feedlens.ai.base import AIProvider
from feedlens.ai.base import Effort
from feedlens.ai.base import MAX_OUTPUT_TOKENS
from feedlens.ai.base import ProviderInfo
from feedlens.ai.base import decode_output

TIMEOUT_MS = 180_000
DEFAULT_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash")
logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    info = ProviderInfo(
        key="gemini", name="Gemini", env_key="GEMINI_API_KEY", model_env="GEMINI_MODEL",
        default_model="gemini-3.5-flash-lite", key_url="https://aistudio.google.com/apikey",
    )

    def __init__(self, model: str | None = None, api_key: str | None = None):
        super().__init__(model, api_key)
        self._response = threading.local()
        from google import genai

        self.genai = genai
        self.client = genai.Client(
            api_key=api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
            http_options=genai.types.HttpOptions(timeout=TIMEOUT_MS, retry_options=genai.types.HttpRetryOptions(attempts=1)),
        )

    @property
    def served_model(self):
        return getattr(getattr(self, "_response", None), "model", self.model)

    def complete_json(self, system: str, prompt: str, schema: dict, effort: Effort = "low") -> dict:
        types = self.genai.types
        thinking = {}
        if self.model.removeprefix("models/").startswith("gemini-3"):
            level = "high" if effort == "high" else "minimal" if "flash-lite" in self.model else "low"
            thinking["thinking_config"] = types.ThinkingConfig(thinking_level=level)
        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                response_mime_type="application/json",
                response_json_schema=schema,
                **thinking,
            ),
        )
        if not hasattr(self, "_response"):
            self._response = threading.local()
        self._response.model = getattr(resp, "model_version", None) or self.model
        reason = resp.candidates[0].finish_reason if resp.candidates else "unknown"
        usage = getattr(resp, "usage_metadata", None)
        def log_response(items=None, invalid=False):
            log = logger.warning if invalid or items == 0 or reason == "MAX_TOKENS" else logger.info
            log("Gemini response requested=%s served=%s finish_reason=%s items=%s invalid_json=%s input_tokens=%s output_tokens=%s thinking_tokens=%s",
                self.model, self.served_model, reason, items, invalid, getattr(usage, "prompt_token_count", None),
                getattr(usage, "candidates_token_count", None), getattr(usage, "thoughts_token_count", None))
        if reason == "MAX_TOKENS":
            log_response()
            raise AIOutputTruncated("Gemini output reached MAX_TOKENS")
        if not resp.text:
            log_response(0)
            raise AIError(f"AI returned empty analysis: Gemini returned no content (finish_reason={reason})")
        try:
            data = decode_output(resp.text)
        except AIOutputTruncated:
            log_response(invalid=True)
            raise
        log_response(len(data["items"]) if isinstance(data.get("items"), list) else None)
        return data

    def list_models(self) -> list[str]:
        out = []
        for m in self.client.models.list():
            name = (m.name or "").removeprefix("models/")
            actions = m.supported_actions or []
            if name.startswith("gemini") and "generateContent" in actions and "embedding" not in name:
                out.append(name)
        return sorted(out, reverse=True)
