import io
import json
import urllib.error
import urllib.request

from sentinel.llm.client import ChatMessage, LLMClient
from sentinel.llm.config import LLMConfig


class DummyResponse:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:  # pragma: no cover - trivial
        return self._body


def test_llm_client_returns_error_message(monkeypatch):
    error = urllib.error.HTTPError(
        "http://example.com/chat/completions",
        503,
        "Service Unavailable",
        hdrs=None,
        fp=io.BytesIO(b"backend down"),
    )

    def fake_urlopen(*args, **kwargs):
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    cfg = LLMConfig(base_url="https://api.openai.com/v1", api_key="token", model="test-model")
    client = LLMClient(cfg)
    reply = client.chat([ChatMessage("user", "hello")])

    assert reply is not None
    assert "LLM request failed" in reply


def test_health_check_missing_api_key():
    cfg = LLMConfig(base_url="https://api.openai.com/v1", api_key=None, model="gpt-4o")
    client = LLMClient(cfg)

    ok, message = client.health_check()

    assert not ok
    assert "OpenAI API key missing" in message


def test_chat_uses_openai_headers(monkeypatch):
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        body = json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode("utf-8")
        return DummyResponse(body, headers={"x-request-id": "req-123"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    cfg = LLMConfig(base_url="https://api.openai.com/v1", api_key="secret", model="gpt-4o")
    client = LLMClient(cfg)

    reply = client.chat([ChatMessage("user", "ping")], max_tokens=5)

    assert reply == "hi"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"
