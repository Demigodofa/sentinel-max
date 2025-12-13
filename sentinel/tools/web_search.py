from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from sentinel.agent_core.base import Tool
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.tool_schema import ToolSchema
from sentinel.logging.logger import get_logger


logger = get_logger(__name__)


@dataclass
class WebSearchTool(Tool):
    name: str = "web_search"
    description: str = "Search the web (DuckDuckGo HTML) and return top results."
    permissions: tuple[str, ...] = ("net:web",)
    memory_manager: Optional[MemoryManager] = None

    def __post_init__(self) -> None:
        super().__init__(self.name, self.description, deterministic=True)
        self.schema = ToolSchema(
            name=self.name,
            version="1.0.0",
            description=self.description,
            input_schema={"query": {"type": "string", "required": True}, "max_results": {"type": "integer", "required": False}},
            output_schema={"type": "object"},
            permissions=list(self.permissions),
            deterministic=True,
        )

    def execute(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        return self.run(query=query, max_results=max_results)

    def run(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        url = "https://duckduckgo.com/html/"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            response = requests.post(url, data={"q": query}, headers=headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            results: List[Dict[str, str]] = []
            for anchor in soup.select("a.result__a")[:max_results]:
                href = anchor.get("href") or ""
                title = anchor.get_text(" ", strip=True)
                results.append({"title": title, "url": href})
            payload = {"ok": True, "query": query, "results": results}
            self._record_evidence(payload)
            return payload
        except requests.RequestException as exc:
            logger.warning("Web search failed, returning simulated results: %s", exc)
            fallback_count = max(1, min(max_results, 3))
            simulated_results = [
                {"title": f"Simulated result {idx + 1} for {query}", "url": f"https://example.invalid/{idx + 1}"}
                for idx in range(fallback_count)
            ]
            payload = {"ok": False, "query": query, "results": simulated_results, "error": str(exc)}
            self._record_evidence(payload)
            return payload

    def _record_evidence(self, payload: Dict[str, Any]) -> None:
        if not self.memory_manager:
            return
        query = payload.get("query", "")
        results = payload.get("results", [])
        content = json.dumps({"query": query, "results": results}, ensure_ascii=False, indent=2)
        metadata = {
            "tool": self.name,
            "source_type": "search",
            "ok": payload.get("ok", False),
            "error": payload.get("error"),
        }
        try:
            self.memory_manager.store_external_source(
                source_type="search",
                content=content,
                metadata=metadata,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to record web search evidence: %s", exc)

WEB_SEARCH_TOOL = WebSearchTool()

