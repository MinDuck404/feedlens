import json
import socket

import httpx
import pytest
from openai import OpenAI

from feedlens.ai.providers.custom import CustomProvider, validate_base_url
from tests.test_cloud import cloud, _signup
from feedlens.routes import dependencies
from feedlens.ai import registry


def test_chat_json_falls_back_only_for_400(monkeypatch):
    bodies = []
    def reply(request):
        body = json.loads(request.content); bodies.append(body)
        if len(bodies) == 1:
            return httpx.Response(400, json={"error": {"message": "unsupported response_format"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]})
    provider = CustomProvider("local-model", "", base_url="http://localhost:11434/v1")
    provider.client = OpenAI(base_url=provider.base_url, api_key="local", max_retries=0,
                             http_client=httpx.Client(transport=httpx.MockTransport(reply)))
    assert provider.complete_json("Classify", "Hello", {"type": "object"}) == {"ok": True}
    assert [body["response_format"]["type"] for body in bodies] == ["json_schema", "json_object"]
    assert all(body["model"] == "local-model" for body in bodies)


@pytest.mark.parametrize("url", ["https://127.0.0.1/v1", "https://169.254.169.254/v1", "https://10.0.0.2/v1", "http://example.com/v1", "https://[::1]/v1", "https://user:secret@example.com/v1"])
def test_cloud_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        validate_base_url(url, cloud=True)


def test_url_normalizes_local_and_checks_all_dns_answers(monkeypatch):
    assert validate_base_url("http://localhost:11434/v1/", cloud=False) == "http://localhost:11434/v1"
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 443)), (socket.AF_INET, 0, 0, "", ("10.0.0.2", 443))])
    with pytest.raises(ValueError):
        validate_base_url("https://public.example/v1", cloud=True)


def test_custom_key_saves_encrypted_optional_secret_and_uses_its_own_config(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 443))])
    monkeypatch.setattr(CustomProvider, "check_connection", lambda self: None)
    monkeypatch.setattr(CustomProvider, "list_models", lambda self: [self.model, "other-model"])
    result = client.post("/api/ai/keys", headers=headers, json={"provider": "custom", "api_key": "", "label": "Local compatible",
        "base_url": "https://public.example/v1/", "default_model": "my-model"})
    assert result.status_code == 200, result.text
    row = result.json()
    assert row["base_url"] == "https://public.example/v1" and row["default_model"] == "my-model"
    assert "api_key" not in row and "ciphertext" not in row
    uid = dependencies.db().get_user_by_email("a@x.io").id
    stored = dependencies.db().list_keys(uid)[0]
    assert stored.ciphertext and stored.ciphertext != ""
    credentials = registry.user_keys(dependencies.db(), uid)
    credential = registry.selected_key(credentials, row["id"], "custom")
    assert credential.api_key == "" and credential.default_model == "my-model"
    models = client.get(f'/api/ai/models/custom?ai_key_id={row["id"]}', headers=headers)
    assert models.status_code == 200 and models.json()["default"] == "my-model"
    providers = client.get("/api/ai/providers", headers=headers).json()
    assert next(p for p in providers if p["key"] == "custom")["configured"] is True


@pytest.mark.parametrize("status", [503, 429])
def test_custom_http_failures_rotate_only_custom_keys(status, monkeypatch):
    import openai
    from feedlens.analysis.analyzer import get_analyzer
    from feedlens.ai.scheduler import QuotaScheduler
    from feedlens.ai.limits import Limits
    from tests.test_ai_quota import Clock
    calls = []
    def reply(request):
        calls.append((request.url.host, json.loads(request.content)["model"]))
        if request.url.host == "first.example":
            return httpx.Response(status, json={"error": {"message": "try later"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]})
    def client(**kwargs):
        kwargs["http_client"].close()
        kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(reply))
        return OpenAI(**kwargs)
    monkeypatch.setattr(openai, "OpenAI", client)
    keys = [registry.KeyCredential(1, "custom", "", base_url="http://first.example/v1", default_model="first-model"),
            registry.KeyCredential(2, "custom", "secret", base_url="http://backup.example/v1", default_model="backup-model"),
            registry.KeyCredential(3, "gemini", "unused")]
    analyzer = get_analyzer("custom", None, keys)
    clock = Clock(); analyzer.scheduler = QuotaScheduler(clock=clock.clock, sleep=clock.sleep)
    assert analyzer.scheduler.limits(analyzer.candidates[0]) == Limits()
    assert analyzer.complete_json("", "", {}) == {"ok": True}
    assert calls == [("first.example", "first-model")] * (3 if status == 429 else 1) + [("backup.example", "backup-model")]
    calls.clear()
    pinned = get_analyzer("custom", "fixed-model", keys, ai_key_id=2)
    assert pinned.complete_json("", "", {}) == {"ok": True}
    assert calls == [("backup.example", "fixed-model")]


def test_custom_plain_json_fallback_and_model_discovery_failure():
    bodies = []
    def reply(request):
        if request.method == "GET":
            return httpx.Response(404, json={"error": {"message": "No models API"}})
        bodies.append(json.loads(request.content))
        if "response_format" in bodies[-1]:
            return httpx.Response(400, json={"error": {"message": "unsupported format"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]})
    provider = CustomProvider("model", "secret", base_url="http://localhost:11434/v1")
    provider.client = OpenAI(base_url=provider.base_url, api_key="secret", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(reply)))
    assert provider.list_models() == ["model"]
    assert provider.complete_json("Classify", "hi", {"type": "object"}) == {"ok": True}
    assert len(bodies) == 3 and "response_format" not in bodies[-1]
    assert "JSON" in bodies[-1]["messages"][0]["content"]


def test_cloud_transport_pins_public_ip_and_rechecks_dns(monkeypatch):
    from feedlens.ai.providers.custom import PublicEndpointTransport
    calls = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 443))])
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda self, request: calls.append(request) or httpx.Response(200))
    transport = PublicEndpointTransport()
    transport.handle_request(httpx.Request("GET", "https://public.example/v1/models"))
    assert calls[0].url.host == "8.8.8.8" and calls[0].headers["host"] == "public.example"
    assert calls[0].extensions["sni_hostname"] == "public.example"
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("127.0.0.1", 443))])
    with pytest.raises(ValueError):
        transport.handle_request(httpx.Request("GET", "https://public.example/v1/models"))
    assert len(calls) == 1


@pytest.mark.parametrize("body,code", [
    ({"base_url": "https://127.0.0.1/v1", "default_model": "model"}, "error.custom_endpoint"),
    ({"base_url": "https://169.254.169.254/v1", "default_model": "model"}, "error.custom_endpoint"),
    ({"base_url": "https://10.0.0.1/v1", "default_model": "model"}, "error.custom_endpoint"),
    ({"base_url": "https://public.example/v1", "default_model": "  "}, "error.custom_model"),
])
def test_invalid_custom_configuration_is_rejected_before_http(cloud, monkeypatch, body, code):
    client = cloud(); headers = _signup(client)
    monkeypatch.setattr(CustomProvider, "check_connection", lambda self: pytest.fail("unsafe config must not reach HTTP"))
    result = client.post("/api/ai/keys", headers=headers, json={"provider": "custom", "api_key": "private-secret", **body})
    assert result.status_code == 422 and result.json()["code"] == code
    assert "private-secret" not in result.text


def test_cloud_client_does_not_follow_redirects_or_use_environment_proxy(monkeypatch):
    from feedlens.core import config
    import dataclasses
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, mode="cloud"))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 443))])
    provider = CustomProvider("model", "secret", base_url="https://public.example/v1")
    assert provider.client._client.follow_redirects is False
    assert not provider.client._client._trust_env
    provider.client.close()


def test_old_key_database_migrates_without_changing_keys_or_requests(tmp_path):
    from feedlens.db.repository import Database
    from sqlalchemy import create_engine, text
    from feedlens.core.models import RunRequest
    url = f"sqlite:///{tmp_path / 'old.db'}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, password_hash TEXT, created_at DATETIME)"))
        connection.execute(text("INSERT INTO users VALUES (1, 'legacy@example.test', 'hash', CURRENT_TIMESTAMP)"))
        connection.execute(text("CREATE TABLE api_keys (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), provider VARCHAR(20), ciphertext TEXT, hint VARCHAR(16), created_at DATETIME, UNIQUE(user_id,provider))"))
        connection.execute(text("INSERT INTO api_keys VALUES (8, 1, 'gemini', 'unchanged-ciphertext', 'hint', CURRENT_TIMESTAMP)"))
    engine.dispose()
    database = Database(url)
    row = database.list_keys(1)[0]
    assert (row.id, row.provider, row.ciphertext, row.base_url, row.default_model) == (8, "gemini", "unchanged-ciphertext", "", "")
    request = RunRequest.model_validate({"platform": "facebook"})
    assert request.ai_provider == "auto" and request.ai_key_id is None
    database.engine.dispose()


def test_unsaved_custom_model_discovery_is_private_sorted_and_never_saves_a_key(cloud, monkeypatch, caplog):
    import logging
    client = cloud(); headers = _signup(client)
    secret = "synthetic-discovery-secret"
    requests = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 443))])
    def reply(self, request):
        requests.append(request)
        assert set(request.extensions["timeout"].values()) == {30}
        return httpx.Response(200, json={"data": [{"id": "z-model"}, {"id": "a-model"}, {"id": "z-model"},
            {"id": ""}, {"id": 7}, {}, "not a model", {"id": secret}, {"id": f"diagnostic-{secret}"}]})
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reply)
    body = {"base_url": "https://public.example/v1/", "api_key": secret}
    assert client.post("/api/ai/custom/models", json=body).status_code == 401
    with caplog.at_level(logging.INFO):
        result = client.post("/api/ai/custom/models", headers=headers, json=body)
    assert result.status_code == 200, result.text
    assert result.json() == {"models": ["a-model", "z-model"]}
    assert len(requests) == 1
    assert requests[0].method == "GET" and requests[0].url.path == "/v1/models"
    assert not requests[0].url.query
    assert requests[0].headers["authorization"] == f"Bearer {secret}"
    assert secret not in result.text and secret not in caplog.text
    assert client.get("/api/ai/keys", headers=headers).json() == []


@pytest.mark.parametrize("status,payload,expected_status,expected", [
    (404, {"error": {"message": "Missing models API"}}, 200, {"models": []}),
    (401, {"error": {"message": "synthetic-discovery-secret invalid key"}}, 400, {"code": "error.custom_connection"}),
    (503, {"error": {"message": "Unavailable"}}, 400, {"code": "error.custom_connection"}),
    (200, None, 400, {"code": "error.custom_connection"}),
    (200, {"data": "not a list"}, 400, {"code": "error.custom_connection"}),
    (302, {}, 400, {"code": "error.custom_connection"}),
])
def test_unsaved_custom_model_discovery_handles_missing_models_and_safe_errors(cloud, monkeypatch, caplog, status, payload, expected_status, expected):
    client = cloud(); headers = _signup(client)
    requests = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 443))])
    def reply(self, request):
        requests.append(request)
        return httpx.Response(status, json=payload, headers={"location": "https://127.0.0.1/models"}) if payload is not None else httpx.Response(status, text="not JSON")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reply)
    result = client.post("/api/ai/custom/models", headers=headers, json={"base_url": "https://public.example/v1", "api_key": "synthetic-discovery-secret"})
    assert result.status_code == expected_status, result.text
    assert all(result.json().get(key) == value for key, value in expected.items())
    assert len(requests) == 1  # Redirects must not forward the key to another endpoint.
    assert "synthetic-discovery-secret" not in result.text and "synthetic-discovery-secret" not in caplog.text
    assert client.get("/api/ai/keys", headers=headers).json() == []


def test_unsaved_custom_model_discovery_limits_results_and_accepts_no_api_key(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 443))])
    def reply(self, request):
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"data": [{"id": f"model-{i:04}"} for i in reversed(range(600))] + [{"id": "model-0000"}]})
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reply)
    result = client.post("/api/ai/custom/models", headers=headers, json={"base_url": "https://public.example/v1"})
    assert result.status_code == 200, result.text
    assert result.json() == {"models": [f"model-{i:04}" for i in range(500)]}


def test_unsaved_custom_model_discovery_rejects_cloud_loopback_before_http(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *a: pytest.fail("unsafe endpoint must not reach HTTP"))
    result = client.post("/api/ai/custom/models", headers=headers, json={"base_url": "https://127.0.0.1/v1", "api_key": "synthetic-discovery-secret"})
    assert result.status_code == 422 and result.json()["code"] == "error.custom_endpoint"
    assert "synthetic-discovery-secret" not in result.text


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_unsaved_custom_model_discovery_hides_connection_failure_details(cloud, monkeypatch, caplog, error_type):
    client = cloud(); headers = _signup(client)
    secret = "synthetic-discovery-secret"
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 443))])
    def failed(self, request):
        raise error_type(f"Connection failed for {secret}", request=request)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", failed)
    result = client.post("/api/ai/custom/models", headers=headers,
                         json={"base_url": "https://public.example/v1", "api_key": secret})
    assert result.status_code == 400
    assert result.json() == {"detail": "Custom endpoint connection failed", "code": "error.custom_connection"}
    assert secret not in result.text and secret not in caplog.text
    assert client.get("/api/ai/keys", headers=headers).json() == []


def test_unsaved_custom_model_discovery_blocks_dns_rebinding_before_http(cloud, monkeypatch):
    client = cloud(); headers = _signup(client)
    addresses = iter(["8.8.8.8", "127.0.0.1"])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", (next(addresses), 443))])
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *a: pytest.fail("rebinding must not reach HTTP"))
    result = client.post("/api/ai/custom/models", headers=headers,
                         json={"base_url": "https://public.example/v1", "api_key": "synthetic-discovery-secret"})
    assert result.status_code == 422
    assert result.json() == {"detail": "Invalid or unsafe custom endpoint URL", "code": "error.custom_endpoint"}
    assert "synthetic-discovery-secret" not in result.text


@pytest.mark.parametrize("body,code", [
    ({"api_key": "synthetic-discovery-secret"}, "error.custom_endpoint"),
    ({"base_url": "", "api_key": "synthetic-discovery-secret"}, "error.custom_endpoint"),
    ({"base_url": "https://public.example/v1", "api_key": "synthetic-discovery-secret" * 30}, "error.validation"),
    ({"base_url": "https://public.example/v1", "api_key": "synthetic-discovery-secret", "synthetic-discovery-secret": True}, "error.validation"),
    ([{"api_key": "synthetic-discovery-secret"}], "error.validation"),
])
def test_unsaved_custom_model_discovery_validation_never_echoes_credentials(cloud, monkeypatch, caplog, body, code):
    client = cloud(); headers = _signup(client)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *a: pytest.fail("invalid bodies must not reach HTTP"))
    result = client.post("/api/ai/custom/models", headers=headers, json=body)
    assert result.status_code == 422 and result.json()["code"] == code
    assert "synthetic-discovery-secret" not in result.text and "synthetic-discovery-secret" not in caplog.text
    assert client.get("/api/ai/keys", headers=headers).json() == []
