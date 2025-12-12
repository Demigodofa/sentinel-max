from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

from sentinel.agent_core.base import Tool
from sentinel.tools.tool_schema import ToolSchema


@dataclass
class WebSearchTool(Tool):
    name: str = "web_search"
    description: str = "Search the web (DuckDuckGo HTML) and return top results."
    permissions: tuple[str, ...] = ("net:web",)

    def __post_init__(self) -> None:
        super().__init__(self.name, self.description, deterministic=False)
        self.schema = ToolSchema(
            name=self.name,
            version="1.0.0",
            description=self.description,
            input_schema={"query": {"type": "string", "required": True}, "max_results": {"type": "integer", "required": False}},
            output_schema={"type": "object"},
            permissions=list(self.permissions),
            deterministic=False,
        )

    def execute(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        return self.run(query=query, max_results=max_results)

    def run(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        url = "https://duckduckgo.com/html/"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.post(url, data={"q": query}, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results: List[Dict[str, str]] = []
        for anchor in soup.select("a.result__a")[:max_results]:
            href = anchor.get("href") or ""
            title = anchor.get_text(" ", strip=True)
            results.append({"title": title, "url": href})
        return {"ok": True, "query": query, "results": results}

WEB_SEARCH_TOOL = WebSearchTool()

