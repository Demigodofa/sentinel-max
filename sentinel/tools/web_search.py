"""Deterministic mock web search tool."""
from __future__ import annotations

from typing import List

from sentinel.agent_core.base import Tool

_PRESEEDED_RESULTS = {
    "sentinel": [
        "Sentinel MAX is a modular agent framework.",
        "Core modules include planning, execution, and reflection.",
    ],
    "python": [
        "Python is a high-level programming language.",
        "It emphasizes readability and developer productivity.",
    ],
}


class WebSearchTool(Tool):
    def __init__(self) -> None:
        super().__init__("web_search", "Deterministic local search index")

    def execute(self, query: str) -> List[str]:
        key = query.lower().strip()
        return list(_PRESEEDED_RESULTS.get(key, [f"No indexed results for '{query}'."]))


WEB_SEARCH_TOOL = WebSearchTool()
