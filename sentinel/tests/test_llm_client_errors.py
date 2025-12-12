import io
import urllib.error
import urllib.request

from sentinel.llm.client import ChatMessage, LLMClient
from sentinel.llm.config import LLMConfig


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

    cfg = LLMConfig(backend="ollama", base_url="http://localhost:11434/v1", api_key="token", model="test-model")
    client = LLMClient(cfg)
    reply = client.chat([ChatMessage("user", "hello")])

    assert reply is not None
    assert "LLM request failed" in reply
