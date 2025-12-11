"""Deterministic mock web search tool."""
from __future__ import annotations

from typing import List


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


def search(query: str) -> List[str]:
    key = query.lower().strip()
    return list(_PRESEEDED_RESULTS.get(key, [f"No indexed results for '{query}'."]))
