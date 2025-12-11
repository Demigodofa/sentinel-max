"""Vector memory for semantic similarity search with safe fallbacks."""
from __future__ import annotations

import hashlib
import importlib.util
import math
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class VectorMemory:
    """Semantic vector store built on sentence-transformers with deterministic fallback."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = model_name or "sentence-transformers/all-MiniLM-L6-v2"
        self._model = None
        self._lock = threading.RLock()
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._fallback_dim = 32

    # ------------------------------------------------------------------
    # Embedding utilities
    # ------------------------------------------------------------------
    def _load_model(self):
        if self._model is not None:
            return self._model
        if importlib.util.find_spec("sentence_transformers") is None:
            logger.warning("sentence-transformers not available; using hash embeddings")
            self._model = None
            return None
        from sentence_transformers import SentenceTransformer  # type: ignore

        try:  # pragma: no cover - model loading may fail in constrained envs
            self._model = SentenceTransformer(self.model_name, device="cpu")
            logger.info("Loaded embedding model: %s", self.model_name)
        except Exception as exc:  # pragma: no cover - fallback path
            logger.warning("Falling back to hash embeddings: %s", exc)
            self._model = None
        return self._model

    def _hash_embed(self, text: str) -> List[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # deterministically map bytes to floats between 0 and 1
        return [b / 255.0 for b in digest[: self._fallback_dim]]

    def _embed(self, text: str) -> List[float]:
        model = self._load_model()
        if model is None:
            return self._hash_embed(text)
        try:
            vector = model.encode(text, normalize_embeddings=True)
            return vector.tolist()
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Model embed failed, using hash fallback: %s", exc)
            return self._hash_embed(text)

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    def add(self, text: str, metadata: Optional[Dict[str, Any]] = None, namespace: str = "default") -> str:
        embedding = self._embed(text)
        entry_id = str(uuid4())
        timestamp = datetime.utcnow().isoformat()
        with self._lock:
            self._entries[entry_id] = {
                "id": entry_id,
                "text": text,
                "namespace": namespace,
                "metadata": metadata or {},
                "embedding": embedding,
                "created_at": timestamp,
            }
        return entry_id

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            return self._entries.pop(entry_id, None) is not None

    def search(
        self,
        query: str,
        top_k: int = 3,
        namespace: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            entries = list(self._entries.values())
        if not entries:
            return []
        q_vec = self._embed(query)
        results: List[Dict[str, Any]] = []
        for entry in entries:
            if namespace and entry["namespace"] != namespace:
                continue
            score = self._cosine_similarity(q_vec, entry["embedding"])
            results.append(
                {
                    "id": entry["id"],
                    "text": entry["text"],
                    "metadata": entry["metadata"],
                    "namespace": entry["namespace"],
                    "score": score,
                    "created_at": entry["created_at"],
                }
            )
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]

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

    def export_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "entries": [
                    {
                        "id": entry_id,
                        "text": entry["text"],
                        "metadata": entry["metadata"],
                        "namespace": entry["namespace"],
                        "created_at": entry["created_at"],
                    }
                    for entry_id, entry in self._entries.items()
                ]
            }
