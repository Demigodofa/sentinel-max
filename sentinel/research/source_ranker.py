"""Source ranking utilities for research ingestion."""
from __future__ import annotations

import math
import re
from typing import Dict, List

from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager

logger = get_logger(__name__)


class SourceRanker:
    """Score and rank documents using deterministic heuristics."""

    def __init__(self, query: str, memory: MemoryManager | None = None) -> None:
        self.query = query.lower().strip()
        self.memory = memory

    def score_document(self, doc: Dict) -> float:
        """Compute a stable score across relevance, integrity, authority, novelty, and density."""

        content: str = str(doc.get("content", ""))
        source: str = str(doc.get("source", "unknown"))
        metadata: Dict = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        tokens = re.findall(r"\w+", content.lower())
        query_tokens = set(re.findall(r"\w+", self.query))
        overlap = query_tokens.intersection(tokens)
        relevance = len(overlap) / max(1, len(query_tokens))

        spam_markers = ["ads", "sponsored", "clickbait", "tracking"]
        integrity_penalty = 0.0
        for marker in spam_markers:
            if marker in content.lower() or marker in str(metadata.get("tags", "")).lower():
                integrity_penalty += 0.1
        integrity = max(0.0, 1.0 - integrity_penalty)

        authority = 0.4
        if source.startswith("https://") or source.startswith("http://"):
            authority += 0.2
        if any(domain in source for domain in ["edu", "gov", "org"]):
            authority += 0.2
        if metadata.get("citations"):
            authority += 0.1
        authority = min(authority, 1.0)

        novelty = 1.0
        if self.memory:
            try:
                existing = self.memory.semantic_search(content[:200], top_k=1)
                novelty = 1.0 - 0.2 * len(existing)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Novelty check failed: %s", exc)
                novelty = 0.8
        novelty = max(0.2, novelty)

        unique_tokens = len(set(tokens))
        density = unique_tokens / max(1, len(tokens))
        density = min(1.0, 0.5 + density / 2)

        score = (
            0.35 * relevance
            + 0.2 * integrity
            + 0.2 * authority
            + 0.15 * novelty
            + 0.1 * density
        )
        return round(score, 4)

    def rank(self, docs: List[Dict]) -> List[Dict]:
        """Return documents sorted by score, stable on ties."""

        scored = [
            {**doc, "score": self.score_document(doc), "_idx": idx} for idx, doc in enumerate(docs)
        ]
        scored.sort(key=lambda item: (-item["score"], item["_idx"]))
        for item in scored:
            item.pop("_idx", None)
        return scored
