"""Advanced tool generator stub."""
from __future__ import annotations

from typing import Callable


def generate_keyword_counter(keywords: list[str]) -> Callable[[str], dict[str, int]]:
    lower_keywords = [kw.lower() for kw in keywords]

    def tool(text: str) -> dict[str, int]:
        counts = {kw: 0 for kw in lower_keywords}
        words = text.lower().split()
        for word in words:
            if word in counts:
                counts[word] += 1
        return counts

    return tool
