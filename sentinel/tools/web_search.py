"""Deterministic mock web search tool."""
from __future__ import annotations

from typing import List

from sentinel.agent_core.base import Tool
from sentinel.tools.tool_schema import ToolSchema

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
        super().__init__("web_search", "Deterministic local search index", deterministic=True)
        self.schema = ToolSchema(
            name="web_search",
            version="1.0.0",
            description="Deterministic local search index",
            input_schema={"query": {"type": "string", "required": True}},
            output_schema={"type": "array", "items": "string"},
            permissions=["net:read"],
            deterministic=True,
        )

    def execute(self, query: str) -> List[str]:
        key = query.lower().strip()
        return list(_PRESEEDED_RESULTS.get(key, [f"No indexed results for '{query}'."]))


WEB_SEARCH_TOOL = WebSearchTool()
