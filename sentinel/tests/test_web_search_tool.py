import pathlib
from typing import List

import pytest

from sentinel.tools.web_search import WebSearchTool


FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "web"


def load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


@pytest.fixture
def web_search_tool() -> WebSearchTool:
    return WebSearchTool()


def test_ddg_html_success(monkeypatch: pytest.MonkeyPatch, web_search_tool: WebSearchTool) -> None:
    html = load_fixture("ddg_html_success.html")

    def fake_request(url: str, query: str, method: str = "GET") -> FakeResponse:
        assert "html.duckduckgo.com" in url
        return FakeResponse(html)

    monkeypatch.setattr(web_search_tool, "_request", fake_request)
    payload = web_search_tool.run(query="OpenAI", max_results=3)

    assert payload["ok"] is True
    assert payload["source"] == "duckduckgo_html"
    assert payload["results"]
    assert payload["results"][0]["snippet"]


def test_ddg_html_fallbacks_to_lite(monkeypatch: pytest.MonkeyPatch, web_search_tool: WebSearchTool) -> None:
    html_empty = "<html></html>"
    lite = load_fixture("ddg_lite_success.html")
    responses: List[FakeResponse] = [FakeResponse(html_empty), FakeResponse(lite)]

    def fake_request(url: str, query: str, method: str = "GET") -> FakeResponse:
        assert responses, "No more responses available"
        return responses.pop(0)

    monkeypatch.setattr(web_search_tool, "_request", fake_request)
    payload = web_search_tool.run(query="OpenAI", max_results=2)

    assert payload["ok"] is True
    assert payload["source"] == "duckduckgo_lite"
    assert payload["results"]
    assert payload.get("warnings")


def test_ddg_blocked(monkeypatch: pytest.MonkeyPatch, web_search_tool: WebSearchTool) -> None:
    blocked_page = load_fixture("ddg_blocked.html")

    def fake_request(url: str, query: str, method: str = "GET") -> FakeResponse:
        return FakeResponse(blocked_page, status_code=403)

    monkeypatch.setattr(web_search_tool, "_request", fake_request)
    payload = web_search_tool.run(query="OpenAI", max_results=2)

    assert payload["ok"] is False
    assert payload["error"] == "blocked"
    assert payload["results"] == []
    assert payload["source"] == "duckduckgo_html"
    assert payload["debug"]["status_code"] == 403
    assert "page_hint" in payload["debug"]
