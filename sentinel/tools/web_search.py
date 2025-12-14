from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import requests
from bs4 import BeautifulSoup

from sentinel.agent_core.base import Tool
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.tool_schema import ToolSchema
from sentinel.logging.logger import get_logger


logger = get_logger(__name__)


_BLOCK_PATTERNS = (
    "unusual traffic",
    "detected unusual",
    "verify you are human",
    "captcha",
    "consent",
)


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
        endpoints: Sequence[dict[str, str]] = (
            {
                "url": "https://html.duckduckgo.com/html/",
                "method": "GET",
                "source": "duckduckgo_html",
                "parser": "_parse_html_results",
            },
            {
                "url": "https://lite.duckduckgo.com/lite/",
                "method": "GET",
                "source": "duckduckgo_lite",
                "parser": "_parse_lite_results",
            },
        )

        debug: Dict[str, Any] = {}
        warnings: List[str] = []
        error_type = "parse_failed"
        last_source = endpoints[0]["source"]

        for idx, endpoint in enumerate(endpoints):
            last_source = endpoint["source"]
            try:
                response = self._request(endpoint["url"], query, method=endpoint["method"])
                status_code = getattr(response, "status_code", None)
                content = response.text or ""
            except requests.RequestException as exc:
                debug = {"endpoint": endpoint["url"], "error": str(exc)}
                logger.warning("Web search request failed for %s: %s", endpoint["url"], exc)
                error_type = "http_error"
                continue

            debug = {
                "endpoint": endpoint["url"],
                "status_code": status_code,
                "bytes": len(content),
            }
            page_hint = self._page_hint(content)
            if page_hint:
                debug["page_hint"] = page_hint

            if self._is_blocked_response(status_code, content):
                payload = {
                    "ok": False,
                    "query": query,
                    "results": [],
                    "error": "blocked",
                    "source": endpoint["source"],
                    "debug": debug,
                }
                self._record_evidence(payload)
                return payload

            parser = getattr(self, endpoint["parser"])
            results = parser(content, max_results)
            if results:
                payload = {
                    "ok": True,
                    "query": query,
                    "results": results[:max_results],
                    "source": endpoint["source"],
                    "debug": debug,
                }
                if warnings:
                    payload["warnings"] = warnings
                self._record_evidence(payload)
                return payload

            if idx < len(endpoints) - 1:
                warnings.append(f"no_results_{endpoint['source']}")
                logger.info(
                    "web_search: 0 results from %s endpoint, falling back to %s",
                    endpoint["source"],
                    endpoints[idx + 1]["source"],
                )

        payload = {
            "ok": False,
            "query": query,
            "results": [],
            "error": error_type,
            "source": last_source,
            "debug": debug,
        }
        if warnings:
            payload["warnings"] = warnings
        self._record_evidence(payload)
        return payload

    def _request(self, url: str, query: str, *, method: str = "GET"):
        headers = {"User-Agent": "Mozilla/5.0"}
        if method.upper() == "POST":
            return requests.post(url, data={"q": query}, headers=headers, timeout=30)
        return requests.get(url, params={"q": query}, headers=headers, timeout=30)

    def _is_blocked_response(self, status_code: Optional[int], content: str) -> bool:
        if status_code and status_code in {403, 429}:
            return True
        lowered = content.lower()
        return any(pattern in lowered for pattern in _BLOCK_PATTERNS)

    def _page_hint(self, content: str, limit: int = 180) -> str:
        if not content:
            return ""
        normalized = " ".join(content.split())
        return normalized[:limit]

    def _parse_html_results(self, content: str, max_results: int) -> List[Dict[str, str]]:
        soup = BeautifulSoup(content, "html.parser")
        results: List[Dict[str, str]] = []
        for anchor in soup.select("a.result__a"):
            href = anchor.get("href") or ""
            title = anchor.get_text(" ", strip=True)
            snippet = ""
            parent = anchor.find_parent("div")
            snippet_node = None
            if parent:
                snippet_node = parent.find(class_="result__snippet") or parent.find("span", class_="result__snippet")
            if not snippet_node:
                snippet_node = anchor.find_next(class_="result__snippet")
            if snippet_node:
                snippet = snippet_node.get_text(" ", strip=True)
            results.append({"title": title, "url": href, "snippet": snippet})
            if len(results) >= max_results:
                break
        return results

    def _parse_lite_results(self, content: str, max_results: int) -> List[Dict[str, str]]:
        soup = BeautifulSoup(content, "html.parser")
        results: List[Dict[str, str]] = []
        for anchor in soup.select("a[href]"):
            href = anchor.get("href") or ""
            title = anchor.get_text(" ", strip=True)
            snippet = ""
            row = anchor.find_parent("tr")
            if row:
                next_row = row.find_next_sibling("tr")
                if next_row:
                    snippet = next_row.get_text(" ", strip=True)
            results.append({"title": title, "url": href, "snippet": snippet})
            if len(results) >= max_results:
                break
        return results

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
            "source": payload.get("source"),
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

