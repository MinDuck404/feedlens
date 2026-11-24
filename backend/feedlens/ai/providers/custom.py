"""OpenAI-compatible chat endpoints with per-key settings and cloud SSRF protection."""
from __future__ import annotations

import ipaddress
import json
import socket
from urllib.parse import urlsplit, urlunsplit

import httpx

from feedlens.core import config
from feedlens.ai.base import AIError, AIOutputTruncated, AIProvider, Effort, MAX_OUTPUT_TOKENS, ProviderInfo, decode_output


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


class CustomProvider(AIProvider):
    info = ProviderInfo("custom", "Custom (OpenAI-compatible)", "", "", "", "")

    def __init__(self, model: str | None = None, api_key: str | None = None, *, base_url: str = ""):
        if not model or not model.strip():
            raise ValueError("Custom endpoints require a default model")
        super().__init__(model.strip(), api_key)
        self.base_url = validate_base_url(base_url)
        from openai import OpenAI
        self.client = OpenAI(base_url=self.base_url, api_key=api_key or "local", max_retries=0,
                             http_client=_http_client())

    @staticmethod
    def discover_models(base_url: str, api_key: str = "") -> list[str]:
        base_url = validate_base_url(base_url)
        with _http_client() as client:
            response = client.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"} if api_key else {})
            if response.status_code == 404:
                return []
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("Invalid custom model list")
        return sorted({item["id"].strip() for item in payload["data"]
                       if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip()
                       and (not api_key or api_key not in item["id"])})[:500]

    def complete_json(self, system: str, prompt: str, schema: dict, effort: Effort = "low") -> dict:
        messages = [{"role": "system", "content": system + "\nReturn only a JSON object matching this schema:\n" + json.dumps(schema)},
                    {"role": "user", "content": prompt}]
        formats = [{"type": "json_schema", "json_schema": {"name": "feedlens_output", "schema": schema, "strict": True}},
                   {"type": "json_object"}, None]
        for index, response_format in enumerate(formats):
            try:
                response = self.client.chat.completions.create(model=self.model, messages=messages,
                    max_tokens=MAX_OUTPUT_TOKENS, **({"response_format": response_format} if response_format else {}))
                break
            except Exception as exc:
                if getattr(exc, "status_code", None) != 400 or index == len(formats) - 1:
                    raise
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
            return list(dict.fromkeys([self.model, *(item.id for item in self.client.models.list())]))
        except Exception:
            return [self.model]

    def check_connection(self) -> None:
        try:
            self.client.models.list()
        except Exception:
            self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": "Hi"}], max_tokens=1)
