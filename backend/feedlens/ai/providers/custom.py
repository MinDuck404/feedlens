"""OpenAI-compatible chat endpoints with per-key settings and cloud SSRF protection."""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import re
import socket
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from feedlens.core import config
from feedlens.ai.base import AIError, AIOutputTruncated, AIProvider, Effort, MAX_OUTPUT_TOKENS, ProviderInfo, decode_output

APIStyle = Literal["auto", "chat", "responses"]
_API_STYLES: dict[str, APIStyle] = {}
_BASE_URLS: dict[str, str] = {}


@dataclass(frozen=True)
class ModelDiscovery:
    base_url: str
    api_style: APIStyle
    models: list[str]


class EndpointError(ValueError):
    code = "error.custom_endpoint"


def _public_addresses(host: str, port: int) -> list[str]:
    try:
        addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise EndpointError("Custom endpoint must resolve to public IP addresses")
        return addresses
    except (OSError, ValueError):
        raise EndpointError("Custom endpoint must resolve to public IP addresses") from None


def validate_base_url(value: str, *, cloud: bool | None = None) -> str:
    cloud = config.settings.is_cloud if cloud is None else cloud
    try:
        value = value.strip()
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or any(ord(char) <= 32 for char in value) or "\\" in value or parsed.port == 0):
            raise ValueError()
        if cloud:
            if parsed.scheme != "https" or parsed.hostname.rstrip(".").lower() == "localhost" or parsed.hostname.lower().endswith(".localhost"):
                raise ValueError()
            _public_addresses(parsed.hostname, parsed.port or 443)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    except (ValueError, OSError):
        raise EndpointError("Invalid or unsafe custom endpoint URL") from None


def normalize_endpoint(value: str, api_style: APIStyle = "auto") -> tuple[str, APIStyle]:
    base_url = validate_base_url(value)
    if api_style not in {"auto", "chat", "responses"}:
        raise ValueError("Invalid custom API style")
    path = urlsplit(base_url).path
    for suffix, implied in (("/responses", "responses"), ("/chat/completions", "chat"),
                            ("/completions", "chat"), ("/models", "auto")):
        if path.endswith(suffix):
            base_url = base_url[:-len(suffix)].rstrip("/")
            if implied != "auto":
                api_style = implied
            break
    return (_BASE_URLS.get(base_url, base_url) if api_style == "auto" else base_url), api_style


def _has_v1(base_url: str) -> bool:
    return "v1" in urlsplit(base_url).path.split("/")


def _missing_path(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in {404, 405}:
        return True
    if status is not None and status != 400:
        return False
    return bool(re.search(
        r"(?:unsupported|not\s+found|not\s+supported)\s+(?:api\s+)?(?:endpoint|route|path)"
        r"|(?:endpoint|route|path)\s+(?:['\"]?[/\w.-]+['\"]?\s+)?(?:is\s+)?(?:not\s+found|unsupported|not\s+supported)"
        r"|(?:chat/completions|/responses)['\"]?\s+(?:is\s+)?(?:not\s+found|unsupported|not\s+supported)"
        r"|(?:unsupported|not\s+found|not\s+supported)\s+['\"]?/[\w./-]*(?:chat/completions|responses)\b", str(exc), re.I))


class PublicEndpointTransport(httpx.HTTPTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        # Pin the validated address for this connection, preserving TLS hostname verification.
        if request.url.scheme != "https" or request.url.username or request.url.password:
            raise EndpointError("Invalid or unsafe custom endpoint URL")
        host = request.url.host
        addresses = _public_addresses(host, request.url.port or 443)
        request.extensions["sni_hostname"] = host
        request.url = request.url.copy_with(host=addresses[0])
        return super().handle_request(request)


def _http_client() -> httpx.Client:
    transport = PublicEndpointTransport() if config.settings.is_cloud else httpx.HTTPTransport()
    return httpx.Client(transport=transport, follow_redirects=False, trust_env=False, timeout=30)


def _read_models(client: httpx.Client, base_url: str, api_key: str) -> tuple[str, list[str]]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    resolved = base_url
    response = client.get(f"{resolved}/models", headers=headers)
    if response.status_code == 404 and not _has_v1(base_url):
        resolved = f"{base_url}/v1"
        response = client.get(f"{resolved}/models", headers=headers)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Invalid custom model list")
    models = sorted({item["id"].strip() for item in payload["data"]
                     if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip()
                     and (not api_key or api_key not in item["id"])})[:500]
    if resolved != base_url:
        _BASE_URLS[base_url] = resolved
    return resolved, models


class CustomProvider(AIProvider):
    info = ProviderInfo("custom", "Custom (OpenAI-compatible)", "", "", "", "")

    def __init__(self, model: str | None = None, api_key: str | None = None, *, base_url: str = "", api_style: APIStyle = "auto"):
        if not model or not model.strip():
            raise ValueError("Custom endpoints require a default model")
        super().__init__(model.strip(), api_key)
        self.base_url, self.api_style = normalize_endpoint(base_url, api_style)
        from openai import OpenAI
        self.client = OpenAI(base_url=self.base_url, api_key=api_key or "local", max_retries=0,
                             http_client=_http_client())

    @staticmethod
    def discover_models(base_url: str, api_key: str = "", api_style: APIStyle = "auto") -> ModelDiscovery:
        base_url, api_style = normalize_endpoint(base_url, api_style)
        with _http_client() as client:
            try:
                base_url, models = _read_models(client, base_url, api_key)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                models = []
        return ModelDiscovery(base_url, api_style, models)

    def _use_base(self, base_url: str) -> None:
        self.base_url = base_url
        self.client.base_url = base_url

    def _load_models(self) -> list[str]:
        base_url, models = _read_models(self.client._client, self.base_url, self.api_key or "")
        self._use_base(base_url)
        return models

    def _chat_request(self, system: str, prompt: str, schema: dict | None, max_tokens: int = MAX_OUTPUT_TOKENS):
        messages = [{"role": "user", "content": prompt}]
        if schema is not None:
            messages.insert(0, {"role": "system", "content": system + "\nReturn only a JSON object matching this schema:\n" + json.dumps(schema)})
        formats = [{"type": "json_schema", "json_schema": {"name": "feedlens_output", "schema": schema, "strict": True}},
                   {"type": "json_object"}, None] if schema is not None else [None]
        for index, response_format in enumerate(formats):
            try:
                return self.client.chat.completions.create(model=self.model, messages=messages,
                    max_tokens=max_tokens, **({"response_format": response_format} if response_format else {}))
            except Exception as exc:
                if (getattr(exc, "status_code", None) != 400 or index == len(formats) - 1
                        or self.api_style == "auto" and _missing_path(exc)):
                    raise

    def _responses_request(self, system: str, prompt: str, schema: dict | None, max_tokens: int = MAX_OUTPUT_TOKENS):
        formats = [{"type": "json_schema", "name": "feedlens_output", "schema": schema, "strict": True},
                   {"type": "json_object"}, None] if schema is not None else [None]
        for index, response_format in enumerate(formats):
            try:
                return self.client.responses.create(model=self.model, instructions=system, input=prompt,
                    max_output_tokens=max_tokens, **({"text": {"format": response_format}} if response_format else {}))
            except Exception as exc:
                if (getattr(exc, "status_code", None) != 400 or index == len(formats) - 1
                        or self.api_style == "auto" and _missing_path(exc)):
                    raise

    def _request(self, system: str, prompt: str, schema: dict | None, max_tokens: int = MAX_OUTPUT_TOKENS):
        if self.api_style == "auto":
            self._use_base(_BASE_URLS.get(self.base_url, self.base_url))
        original = self.base_url
        preferred = self.api_style if self.api_style != "auto" else _API_STYLES.get(self.base_url, "chat")
        styles = (preferred, "responses" if preferred == "chat" else "chat") if self.api_style == "auto" else (preferred,)
        bases = (original, f"{original}/v1") if self.api_style == "auto" and not _has_v1(original) else (original,)
        last_error = None
        for base_url in bases:
            self._use_base(base_url)
            for style in styles:
                try:
                    send = self._responses_request if style == "responses" else self._chat_request
                    response = send(system, prompt, schema, max_tokens)
                except Exception as exc:
                    if self.api_style != "auto" or not _missing_path(exc):
                        raise
                    last_error = exc
                    continue
                if base_url != original:
                    _BASE_URLS[original] = base_url
                _API_STYLES[base_url] = style
                return style, response
        raise last_error

    def complete_json(self, system: str, prompt: str, schema: dict, effort: Effort = "low") -> dict:
        style, response = self._request(system, prompt, schema)
        if style == "responses":
            if response.status == "incomplete" and getattr(response.incomplete_details, "reason", None) == "max_output_tokens":
                raise AIOutputTruncated("Custom endpoint output reached its token limit")
            text = response.output_text
        else:
            if not response.choices:
                raise AIError("Custom endpoint returned no choices")
            choice = response.choices[0]
            if choice.finish_reason == "length":
                raise AIOutputTruncated("Custom endpoint output reached its token limit")
            text = choice.message.content
        if not text:
            raise AIError("Custom endpoint returned no content")
        return decode_output(text)

    def list_models(self) -> list[str]:
        try:
            return list(dict.fromkeys([self.model, *self._load_models()]))
        except Exception:
            return [self.model]

    def check_connection(self) -> None:
        try:
            self._load_models()
        except EndpointError:
            raise
        except Exception:
            self._request("", "Hi", None, 1)
