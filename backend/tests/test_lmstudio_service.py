"""Unit tests for the LM Studio client.

No LM Studio server is needed: httpx.MockTransport plays the server and
returns mocked OpenAI-compatible responses.
"""
import json

import httpx
import pytest

from app.services.lmstudio_service import (
    LMStudioClient,
    LMStudioConnectionError,
    LMStudioDisabledError,
    LMStudioError,
    LMStudioModelError,
    LMStudioResponseError,
    LMStudioTimeoutError,
)

BASE = "http://localhost:1234/v1"
MODELS = {"data": [{"id": "text-embedding-nomic-embed-text-v1.5"}, {"id": "qwen2.5-7b-instruct"}]}


def completion(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class FakeServer:
    """Records requests and answers like LM Studio's OpenAI-compatible server."""

    def __init__(self, reply="hello", status=200, body=None, error=None, models=MODELS):
        self.reply, self.status, self.body, self.error, self.models = reply, status, body, error, models
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=self.models)
        if self.body is not None:
            return httpx.Response(self.status, content=self.body)
        return httpx.Response(self.status, json=completion(self.reply))

    @property
    def last_payload(self):
        return json.loads(self.requests[-1].content)


def make_client(server, **kwargs):
    kwargs.setdefault("enabled", True)
    kwargs.setdefault("model", "")
    return LMStudioClient(base_url=BASE, transport=httpx.MockTransport(server), **kwargs)


# -- happy path --------------------------------------------------------------------
def test_chat_uses_openai_endpoint_and_first_loaded_chat_model():
    server = FakeServer()
    assert make_client(server).chat([{"role": "user", "content": "hi"}]) == "hello"
    assert str(server.requests[-1].url) == f"{BASE}/chat/completions"
    assert server.last_payload["model"] == "qwen2.5-7b-instruct"  # embedding model skipped
    assert server.last_payload["stream"] is False
    assert server.last_payload["messages"] == [{"role": "user", "content": "hi"}]


def test_configured_model_is_used_without_listing_models():
    server = FakeServer()
    make_client(server, model="my-model").chat([])
    assert server.last_payload["model"] == "my-model"
    assert len(server.requests) == 1


@pytest.mark.anyio
async def test_async_chat_and_models():
    server = FakeServer(reply="async hello")
    client = make_client(server, model="my-model")
    assert await client.achat([{"role": "user", "content": "hi"}]) == "async hello"
    assert await client.alist_models() == ["text-embedding-nomic-embed-text-v1.5", "qwen2.5-7b-instruct"]


@pytest.mark.anyio
async def test_json_output_strips_reasoning_and_code_fences():
    server = FakeServer(reply='<think>let me think</think>```json\n{"category": "Groceries"}\n```')
    client = make_client(server, model="m")
    assert await client.achat_json([], {"type": "object"}) == {"category": "Groceries"}
    assert server.last_payload["response_format"]["type"] == "json_schema"
    assert server.last_payload["temperature"] == 0


def test_api_key_sent_only_when_configured():
    server = FakeServer()
    make_client(server, model="m", api_key="secret-token").chat([])
    assert server.requests[-1].headers["authorization"] == "Bearer secret-token"

    server = FakeServer()
    make_client(server, model="m").chat([])
    assert "authorization" not in server.requests[-1].headers


def test_repr_hides_api_key():
    assert "secret" not in repr(LMStudioClient(api_key="secret-token"))


def test_status_reports_available_models():
    status = make_client(FakeServer()).status()
    assert status["available"] is True
    assert status["reason"] is None
    assert "qwen2.5-7b-instruct" in status["models"]


# -- failures ----------------------------------------------------------------------
def test_disabled_client_never_calls_server():
    server = FakeServer()
    client = make_client(server, enabled=False)
    assert client.is_available() is False
    assert client.status()["reason"] == "disabled"
    with pytest.raises(LMStudioDisabledError):
        client.chat([])
    assert server.requests == []


def test_connection_refused():
    server = FakeServer(error=httpx.ConnectError("refused"))
    with pytest.raises(LMStudioConnectionError) as info:
        make_client(server, model="m").chat([])
    assert info.value.reason == "connection"
    assert "Is the local server running" in str(info.value)


@pytest.mark.anyio
async def test_timeout():
    server = FakeServer(error=httpx.ReadTimeout("slow"))
    with pytest.raises(LMStudioTimeoutError):
        await make_client(server, model="m").achat([])


def test_unknown_configured_model_is_reported_clearly():
    body = json.dumps({"error": {"message": "Model 'missing-model' not found"}}).encode()
    server = FakeServer(status=404, body=body)
    with pytest.raises(LMStudioModelError, match="missing-model"):
        make_client(server, model="missing-model").chat([])


def test_status_flags_configured_model_that_is_not_loaded():
    status = make_client(FakeServer(), model="not-downloaded").status()
    assert status["available"] is False
    assert status["reason"] == "model_unavailable"


def test_no_chat_model_loaded():
    server = FakeServer(models={"data": [{"id": "text-embedding-nomic"}]})
    with pytest.raises(LMStudioModelError, match="No chat model"):
        make_client(server).chat([])
    assert make_client(server).status()["reason"] == "model_unavailable"


def test_http_error_includes_lmstudio_message():
    server = FakeServer(status=500, body=json.dumps({"error": "Internal failure"}).encode())
    with pytest.raises(LMStudioResponseError, match="HTTP 500: Internal failure"):
        make_client(server, model="m").chat([])


@pytest.mark.parametrize(
    "body",
    [b"<html>not json</html>", json.dumps({"choices": []}).encode(), json.dumps(completion("   ")).encode()],
    ids=["not-json", "no-choices", "empty-content"],
)
def test_invalid_responses(body):
    with pytest.raises(LMStudioResponseError):
        make_client(FakeServer(body=body), model="m").chat([])


def test_malformed_models_list():
    server = FakeServer(models={"object": "list"})
    with pytest.raises(LMStudioResponseError):
        make_client(server).list_models()


@pytest.mark.parametrize("reply", ["not json", "[1, 2, 3]"])
def test_invalid_json_output(reply):
    with pytest.raises(LMStudioResponseError):
        make_client(FakeServer(reply=reply), model="m").chat_json([], {"type": "object"})


def test_all_errors_share_a_base_class():
    for cls in (LMStudioDisabledError, LMStudioConnectionError, LMStudioTimeoutError,
                LMStudioModelError, LMStudioResponseError):
        assert issubclass(cls, LMStudioError)


def test_real_unreachable_port():
    # connect_timeout must be > ~2.5s: Windows retries a refused localhost connection for ~2s before
    # reporting it, so a 1s timeout raises LMStudioTimeoutError there instead of a connection error.
    client = LMStudioClient(base_url="http://127.0.0.1:9/v1", model="m", timeout=5, connect_timeout=5, enabled=True)
    assert client.is_available() is False
    with pytest.raises(LMStudioConnectionError):
        client.chat([{"role": "user", "content": "hi"}])
