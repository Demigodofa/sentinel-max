"""Lightweight vector memory stub for similarity search."""
from __future__ import annotations

from typing import List, Tuple
import math


class VectorMemory:
    def __init__(self) -> None:
        self.entries: List[Tuple[str, List[float]]] = []

    def add(self, text: str) -> None:
        vector = self._embed(text)
        self.entries.append((text, vector))

    def search(self, query: str, top_k: int = 3) -> List[str]:
        if not self.entries:
            return []
        q_vec = self._embed(query)
        scored = [
            (self._cosine_similarity(q_vec, vec), text)
            for text, vec in self.entries
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for _, text in scored[:top_k]]

    def _embed(self, text: str) -> List[float]:
        # Simple deterministic hashing-based embedding
        return [((ord(c) % 13) / 13.0) for c in text[:32]]

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0
        length = min(len(a), len(b))
        dot = sum(a[i] * b[i] for i in range(length))
        norm_a = math.sqrt(sum(x * x for x in a[:length]))
        norm_b = math.sqrt(sum(x * x for x in b[:length]))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def export_state(self):
        return {"entries": [text for text, _ in self.entries]}
