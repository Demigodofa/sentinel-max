from sentinel.agent_core.sandbox import Sandbox
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.internet_extractor import InternetExtractorTool
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.web_search import WebSearchTool


class DummyResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_external_calls_sandboxed_and_logged(tmp_path, monkeypatch):
    memory = MemoryManager(storage_dir=tmp_path)
    registry = ToolRegistry()
    sandbox = Sandbox()

    def fake_post(url, data, headers, timeout):
        html = '<a class="result__a" href="https://example.com">Example Domain</a>'
        return DummyResponse(html)

    monkeypatch.setattr("sentinel.tools.web_search.requests.post", fake_post)

    web_tool = WebSearchTool(memory_manager=memory)
    registry.register(web_tool)

    search_result = sandbox.execute(registry.call, "web_search", query="sentinel", max_results=1)
    assert search_result["results"][0]["url"] == "https://example.com"

    extractor = InternetExtractorTool(vector_memory=memory.vector, memory_manager=memory)
    extractor.scraper.execute = lambda url: {
        "url": url,
        "html": "<html><body>hello world</body></html>",
        "text": "hello world",
    }
    registry.register(extractor)

    extraction = sandbox.execute(registry.call, "internet_extract", url="https://example.com/article")
    assert "clean_text" in extraction and extraction["summary"]

    evidence_records = memory.query("external_sources")
    assert len(evidence_records) >= 2

    search_evidence = [r for r in evidence_records if r["metadata"].get("tool") == "web_search"]
    extract_evidence = [r for r in evidence_records if r["metadata"].get("tool") == "internet_extract"]
    assert search_evidence and extract_evidence

    reopened_memory = MemoryManager(storage_dir=tmp_path)
    persisted = reopened_memory.query("external_sources")
    assert len(persisted) >= len(evidence_records)

    # Ensure evidence content is persisted and retrievable
    search_record = search_evidence[0]
    loaded_search = reopened_memory.load_external_source(search_record["key"])
    assert loaded_search and "example.com" in (loaded_search["content"] or "")

    extract_record = extract_evidence[0]
    loaded_extract = reopened_memory.load_external_source(extract_record["key"])
    assert loaded_extract and "hello world" in (loaded_extract["content"] or "")
