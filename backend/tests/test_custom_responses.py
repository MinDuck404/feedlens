"""Custom endpoint normalization and protocol selection use synthetic transports only."""
import json
import socket

import httpx
import pytest
from openai import APIStatusError
from sqlalchemy import create_engine, inspect, text

from feedlens.ai.providers import custom
from feedlens.ai.providers.custom import CustomProvider
from feedlens.ai.base import AIError, AIOutputTruncated
from feedlens.db.repository import Database
from feedlens.db.tables import RunRow, UserRow
from feedlens.ai import registry
from feedlens.routes import dependencies
from tests.test_cloud import cloud, _signup


@pytest.fixture(autouse=True)
def isolate_endpoint_detection(monkeypatch):
    monkeypatch.setattr(custom, "_API_STYLES", {}, raising=False)
    monkeypatch.setattr(custom, "_BASE_URLS", {}, raising=False)


@pytest.fixture
def fake_endpoint(monkeypatch):
    clients = []

    def install(reply):
        def client():
            value = httpx.Client(transport=httpx.MockTransport(reply), timeout=30,
                                 follow_redirects=False, trust_env=False)
            clients.append(value)
            return value
        monkeypatch.setattr(custom, "_http_client", client)

    yield install
    for client in clients:
        client.close()


def responses_payload(text='{"ok":true}', *, status="completed", reason=None):
    payload = {"id": "resp_test", "object": "response", "created_at": 0, "model": "chosen-model",
               "status": status, "output": []}
    if text is not None:
        payload["output"] = [{"id": "msg_test", "type": "message", "status": "completed", "role": "assistant",
                              "content": [{"type": "output_text", "text": text, "annotations": []}]}]
    if reason:
        payload["incomplete_details"] = {"reason": reason}
    return payload


@pytest.mark.parametrize("suffix,style", [
    ("responses", "responses"), ("chat/completions", "chat"),
    ("completions", "chat"), ("models", "auto"),
])
@pytest.mark.parametrize("trailing", ["", "/"])
def test_full_endpoint_url_is_normalized_before_checking_models(fake_endpoint, suffix, style, trailing):
    requests = []

    def reply(request):
        requests.append((request.method, request.url.path))
        return httpx.Response(200, json={"data": [{"id": "chosen-model"}]})

    fake_endpoint(reply)
    provider = CustomProvider("chosen-model", "synthetic-key",
                              base_url=f"https://gateway.example/v1/{suffix}{trailing}")
    assert provider.base_url == "https://gateway.example/v1"
    assert provider.api_style == style
    provider.check_connection()
    assert requests == [("GET", "/v1/models")]


@pytest.mark.parametrize("failed_formats", [0, 1, 2])
def test_responses_endpoint_generates_structured_json_without_chat(fake_endpoint, failed_formats):
    requests = []

    def reply(request):
        requests.append((request.url.path, json.loads(request.content)))
        if request.url.path != "/v1/responses":
            return httpx.Response(404, json={"error": {"message": "Endpoint not found"}})
        if len(requests) <= failed_formats:
            return httpx.Response(400, json={"error": {"message": "Unsupported text format"}})
        return httpx.Response(200, json=responses_payload())

    fake_endpoint(reply)
    provider = CustomProvider("chosen-model", "synthetic-key", base_url="https://gateway.example/v1/responses")
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    assert provider.complete_json("Use only the input", "Hello", schema) == {"ok": True}
    assert [path for path, _ in requests] == ["/v1/responses"] * (failed_formats + 1)
    assert all(body["model"] == "chosen-model" and body["instructions"] == "Use only the input" and body["input"] == "Hello"
               and body["max_output_tokens"] == 8192 for _, body in requests)
    expected = [{"type": "json_schema", "name": "feedlens_output", "schema": schema, "strict": True}, {"type": "json_object"}, None]
    assert [body.get("text", {}).get("format") for _, body in requests] == expected[:failed_formats + 1]


@pytest.mark.parametrize("payload,error,reason", [
    (responses_payload(status="incomplete", reason="max_output_tokens"), AIOutputTruncated, "token limit"),
    (responses_payload(None), AIError, "no content"),
])
def test_responses_output_errors_preserve_truncation_and_empty_result_semantics(fake_endpoint, payload, error, reason):
    fake_endpoint(lambda request: httpx.Response(200, json=payload))
    provider = CustomProvider("chosen-model", "synthetic-key", base_url="https://gateway.example/v1/responses")
    with pytest.raises(error, match=reason):
        provider.complete_json("system", "prompt", {"type": "object"})


@pytest.mark.parametrize("status,message", [
    (404, "Endpoint not found"), (405, "Method not allowed"),
    (400, "Unsupported endpoint /v1/chat/completions"),
])
def test_auto_style_detects_responses_and_reuses_it_across_keys(fake_endpoint, status, message):
    paths = []

    def reply(request):
        paths.append(request.url.path)
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(status, json={"error": {"message": message}})
        return httpx.Response(200, json=responses_payload())

    fake_endpoint(reply)
    provider = CustomProvider("chosen-model", "first-key", base_url="https://gateway.example/v1")
    assert provider.complete_json("system", "prompt", {}) == {"ok": True}
    assert provider.complete_json("system", "prompt", {}) == {"ok": True}
    second = CustomProvider("chosen-model", "second-key", base_url="https://gateway.example/v1/")
    assert second.complete_json("system", "prompt", {}) == {"ok": True}
    assert provider.api_style == "auto" and second.api_style == "auto"
    assert paths == ["/v1/chat/completions", "/v1/responses", "/v1/responses", "/v1/responses"]


def test_models_retry_v1_and_return_the_normalized_endpoint_for_later_requests(fake_endpoint):
    paths = []

    def reply(request):
        paths.append(request.url.path)
        if request.url.path == "/models":
            return httpx.Response(404, json={"error": {"message": "Not found"}})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "z-model"}, {"id": "a-model"}, {"id": "z-model"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]})

    fake_endpoint(reply)
    result = CustomProvider.discover_models("https://gateway.example", "synthetic-key")
    assert paths == ["/models", "/v1/models"]
    assert result.base_url == "https://gateway.example/v1" and result.api_style == "auto"
    assert result.models == ["a-model", "z-model"]
    provider = CustomProvider("chosen-model", "another-key", base_url="https://gateway.example")
    assert provider.base_url == result.base_url
    assert provider.complete_json("system", "prompt", {}) == {"ok": True}
    assert paths[-1] == "/v1/chat/completions"


def test_auto_root_gateway_with_working_models_can_find_v1_responses_and_cache_the_base(fake_endpoint):
    paths = []

    def reply(request):
        paths.append(request.url.path)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "chosen-model"}]})
        if request.url.path == "/v1/responses":
            return httpx.Response(200, json=responses_payload())
        return httpx.Response(404, json={"error": {"message": "Endpoint not found"}})

    fake_endpoint(reply)
    provider = CustomProvider("chosen-model", "first-key", base_url="https://gateway.example")
    provider.check_connection()
    assert provider.complete_json("system", "prompt", {}) == {"ok": True}
    assert provider.complete_json("system", "prompt", {}) == {"ok": True}
    second = CustomProvider("chosen-model", "second-key", base_url="https://gateway.example")
    assert second.complete_json("system", "prompt", {}) == {"ok": True}
    assert provider.base_url == second.base_url == "https://gateway.example/v1"
    assert paths == ["/models", "/chat/completions", "/responses", "/v1/chat/completions",
                     "/v1/responses", "/v1/responses", "/v1/responses"]


@pytest.mark.parametrize("style", ["auto", "chat", "responses"])
@pytest.mark.parametrize("status", [429, 500, 503])
def test_rate_and_service_errors_do_not_retry_formats_protocols_or_versions(fake_endpoint, style, status):
    paths = []

    def reply(request):
        paths.append(request.url.path)
        return httpx.Response(status, json={"error": {"message": "Unsupported endpoint"}})

    fake_endpoint(reply)
    provider = CustomProvider("chosen-model", "synthetic-key", base_url="https://gateway.example", api_style=style)
    with pytest.raises(APIStatusError) as failed:
        provider.complete_json("system", "prompt", {})
    assert failed.value.status_code == status
    assert paths == ["/responses" if style == "responses" else "/chat/completions"]


def test_explicit_chat_style_overrides_a_cached_responses_detection(fake_endpoint):
    paths = []
    chat_available = [False]

    def reply(request):
        paths.append(request.url.path)
        if request.url.path == "/v1/chat/completions":
            if not chat_available[0]:
                return httpx.Response(404, json={"error": {"message": "Endpoint not found"}})
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]})
        return httpx.Response(200, json=responses_payload())

    fake_endpoint(reply)
    auto = CustomProvider("chosen-model", "synthetic-key", base_url="https://gateway.example/v1")
    assert auto.complete_json("system", "prompt", {}) == {"ok": True}
    chat_available[0] = True
    chat = CustomProvider("chosen-model", "synthetic-key", base_url="https://gateway.example/v1", api_style="chat")
    assert chat.complete_json("system", "prompt", {}) == {"ok": True}
    assert paths == ["/v1/chat/completions", "/v1/responses", "/v1/chat/completions"]


@pytest.mark.parametrize("url,expected_paths", [
    ("https://gateway.example/v1/responses", ["/v1/models", "/v1/responses"]),
    ("https://gateway.example", ["/models", "/v1/models", "/chat/completions", "/responses", "/v1/chat/completions", "/v1/responses"]),
])
def test_save_check_uses_a_one_token_probe_in_the_detected_style_when_models_are_missing(fake_endpoint, url, expected_paths):
    requests = []

    def reply(request):
        body = json.loads(request.content) if request.content else None
        requests.append((request.url.path, body))
        if request.url.path == "/v1/responses":
            return httpx.Response(200, json=responses_payload('{"', status="incomplete", reason="max_output_tokens"))
        return httpx.Response(404, json={"error": {"message": "Endpoint not found"}})

    fake_endpoint(reply)
    provider = CustomProvider("chosen-model", "synthetic-key", base_url=url)
    provider.check_connection()
    assert [path for path, _ in requests] == expected_paths
    for path, body in requests:
        if body:
            assert body["max_output_tokens" if path.endswith("responses") else "max_tokens"] == 1
            assert "text" not in body and "response_format" not in body
    assert provider.base_url == "https://gateway.example/v1"


@pytest.mark.parametrize("legacy_unique,existing_style", [(False, None), (True, None), (True, "responses")])
def test_api_style_migration_preserves_keys_requests_and_existing_style(tmp_path, legacy_unique, existing_style):
    url = f"sqlite:///{tmp_path / 'old-style.db'}"
    engine = create_engine(url)
    UserRow.__table__.create(engine)
    RunRow.__table__.create(engine)
    request = {"platform": "facebook", "ai_provider": "custom", "ai_key_id": 8, "ai_model": "saved-model"}
    with engine.begin() as connection:
        connection.execute(UserRow.__table__.insert().values(id=1, email="old@example.test", password_hash="!"))
        connection.execute(RunRow.__table__.insert().values(id=9, user_id=1, request=request))
        extra = ", api_style VARCHAR(16) NOT NULL DEFAULT 'auto'" if existing_style else ""
        unique = ", UNIQUE(user_id,provider)" if legacy_unique else ""
        connection.execute(text("CREATE TABLE api_keys (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), "
            "provider VARCHAR(20), ciphertext TEXT, hint VARCHAR(16), created_at DATETIME, label VARCHAR(80), priority INTEGER, "
            "enabled BOOLEAN, tier VARCHAR(8), base_url TEXT, default_model VARCHAR(200)" + extra + unique + ")"))
        fields = "id,user_id,provider,ciphertext,hint,created_at,label,priority,enabled,tier,base_url,default_model"
        values = "8,1,'custom','unchanged-ciphertext','hint','2026-11-18','Saved',2,TRUE,'paid','https://old.example/v1','saved-model'"
        if existing_style:
            fields += ",api_style"; values += ",:style"
        connection.execute(text(f"INSERT INTO api_keys ({fields}) VALUES ({values})"), {"style": existing_style})
    engine.dispose()

    database = Database(url)
    row = database.list_keys(1)[0]
    assert (row.id, row.ciphertext, row.label, row.priority, row.enabled, row.tier, row.base_url, row.default_model, row.api_style) == (
        8, "unchanged-ciphertext", "Saved", 2, True, "paid", "https://old.example/v1", "saved-model", existing_style or "auto")
    assert database.get_run(9)["request"] == request
    column = next(column for column in inspect(database.engine).get_columns("api_keys") if column["name"] == "api_style")
    assert column["type"].length == 16 and not column["nullable"] and column["default"].strip("'") == "auto"
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    database.engine.dispose()
    reopened = Database(url)
    assert reopened.list_keys(1)[0].api_style == (existing_style or "auto")
    assert reopened.get_run(9)["request"] == request
    reopened.engine.dispose()


@pytest.mark.parametrize("suffix,style", [("responses", "responses"), ("chat/completions", "chat"), ("completions", "chat"), ("models", "auto")])
def test_saved_full_url_exposes_and_restores_the_key_api_style(cloud, monkeypatch, fake_endpoint, suffix, style):
    client = cloud(); headers = _signup(client)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 443))])
    paths = []

    def reply(request):
        paths.append(request.url.path)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "chosen-model"}]})
        if request.url.path.endswith("responses"):
            return httpx.Response(200, json=responses_payload())
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]})

    fake_endpoint(reply)
    result = client.post("/api/ai/keys", headers=headers, json={"provider": "custom", "api_key": "synthetic-key",
        "base_url": f"https://gateway.example/v1/{suffix}/", "default_model": "chosen-model"})
    assert result.status_code == 200, result.text
    row = result.json()
    assert row["base_url"] == "https://gateway.example/v1" and row["api_style"] == style
    uid = dependencies.db().get_user_by_email("a@x.io").id
    credential = registry.selected_key(registry.user_keys(dependencies.db(), uid), row["id"], "custom")
    assert credential.api_style == style and credential.base_url == row["base_url"]
    provider = registry.get_provider("custom", credential=credential)
    assert provider.api_style == style and provider.complete_json("system", "prompt", {}) == {"ok": True}
    assert paths[-1] == ("/v1/responses" if style == "responses" else "/v1/chat/completions")
    assert "synthetic-key" not in result.text and "ciphertext" not in row


def test_model_discovery_metadata_preserves_responses_style_when_saving_the_normalized_url(cloud, monkeypatch, fake_endpoint):
    client = cloud(); headers = _signup(client)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 443))])
    fake_endpoint(lambda request: httpx.Response(200, json={"data": [{"id": "chosen-model"}]}))
    loaded = client.post("/api/ai/custom/models", headers=headers,
                        json={"base_url": "https://gateway.example/v1/responses/", "api_key": "synthetic-key"})
    assert loaded.status_code == 200
    assert loaded.json() == {"models": ["chosen-model"], "base_url": "https://gateway.example/v1", "api_style": "responses"}
    assert client.get("/api/ai/keys", headers=headers).json() == []
    metadata = loaded.json()
    saved = client.post("/api/ai/keys", headers=headers, json={"provider": "custom", "api_key": "synthetic-key",
        "base_url": metadata["base_url"], "api_style": metadata["api_style"], "default_model": metadata["models"][0]})
    assert saved.status_code == 200 and saved.json()["api_style"] == "responses"
    assert saved.json()["base_url"] == "https://gateway.example/v1"


def test_save_persists_the_v1_base_discovered_by_its_model_check(cloud, monkeypatch, fake_endpoint):
    client = cloud(); headers = _signup(client)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 443))])
    paths = []

    def reply(request):
        paths.append(request.url.path)
        if request.url.path == "/models":
            return httpx.Response(404, json={"error": {"message": "Not found"}})
        return httpx.Response(200, json={"data": [{"id": "chosen-model"}]})

    fake_endpoint(reply)
    saved = client.post("/api/ai/keys", headers=headers, json={"provider": "custom", "api_key": "synthetic-key",
        "base_url": "https://gateway.example", "default_model": "chosen-model"})
    assert saved.status_code == 200 and saved.json()["base_url"] == "https://gateway.example/v1"
    assert saved.json()["api_style"] == "auto" and paths == ["/models", "/v1/models"]
