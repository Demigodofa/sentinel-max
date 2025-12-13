"""Memory management for Sentinel MAX."""
from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sentinel.memory.symbolic_memory import SymbolicMemory
from sentinel.memory.vector_memory import VectorMemory
from sentinel.logging.logger import get_logger
from sentinel.config.sandbox_config import ensure_sandbox_root_exists

logger = get_logger(__name__)


@dataclass
class MemoryRecord:
    category: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryManager:
    """Unified interface combining symbolic and vector memories."""

    def __init__(
        self,
        storage_dir: str | Path | None = None,
        embedding_model: Optional[str] = None,
    ) -> None:
        storage_root = storage_dir or os.environ.get("SENTINEL_STORAGE_DIR")
        if storage_root:
            base_dir = Path(storage_root)
        else:
            base_dir = ensure_sandbox_root_exists() / "memory"
        base_dir = base_dir.expanduser().resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        self.symbolic = SymbolicMemory(base_dir / "symbolic_store.json")
        self.vector = VectorMemory(model_name=embedding_model, storage_path=base_dir / "vector_store.json")
        self._lock = RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def store_text(
        self,
        text: str,
        namespace: str = "general",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a free-form text snippet in both symbolic and vector memories."""
        if not isinstance(text, str):
            try:
                text = json.dumps(text, ensure_ascii=False, indent=2)
            except Exception:
                text = str(text)
        timestamp = datetime.now(timezone.utc).isoformat()
        metadata = metadata or {}
        record_key = str(uuid4())
        fact_value = {
            "text": text,
            "metadata": metadata,
            "timestamp": timestamp,
            "type": "text",
        }
        symbolic_record = self.symbolic.create(namespace, record_key, fact_value, allow_overwrite=True)
        vector_id = self.vector.add(text, metadata={**metadata, "symbolic_key": record_key}, namespace=namespace)
        logger.info("Stored text entry in namespace '%s' with key %s", namespace, record_key)
        return {
            "key": record_key,
            "namespace": namespace,
            "symbolic": symbolic_record,
            "vector_id": vector_id,
        }

    def store_fact(
        self,
        namespace: str,
        key: Optional[str],
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Persist a structured fact in symbolic memory."""
        fact_key = key or str(uuid4())
        record = self.symbolic.create(namespace, fact_key, value, metadata=metadata, allow_overwrite=True)
        logger.info("Stored fact '%s:%s'", namespace, fact_key)
        return record

    def query(self, namespace: Optional[str] = None, key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query facts by namespace and optional key."""
        if namespace is None:
            all_records: List[Dict[str, Any]] = []
            for ns in self.symbolic.list_namespaces():
                all_records.extend(self.symbolic.read(ns))
            return sorted(all_records, key=lambda r: r.get("updated_at", ""))

        records = self.symbolic.read(namespace, key)
        return sorted(records, key=lambda r: r.get("updated_at", ""), reverse=True)

    def recall_recent(self, limit: int = 5, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return most recent symbolic entries, optionally filtered by namespace."""
        if namespace:
            records = self.symbolic.read(namespace)
        else:
            records = self.query()
        sorted_records = sorted(records, key=lambda r: r.get("updated_at", ""), reverse=True)
        return sorted_records[:limit]

    def semantic_search(
        self, query: str, top_k: int = 3, namespace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self.vector.search(query, top_k=top_k, namespace=namespace)

    def store_research(self, namespace: str, payload: Any, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Persist research artifacts into structured namespaces."""

        allowed = {
            "research.raw",
            "research.ranked",
            "research.domain",
            "research.tools",
            "research.models",
            "research.predictor_updates",
            "research.anomalies",
        }
        if namespace not in allowed:
            raise ValueError(f"Unsupported research namespace: {namespace}")
        return self.store_fact(namespace, key=None, value=payload, metadata=metadata)

    # ------------------------------------------------------------------
    # Compatibility helpers with legacy APIs
    # ------------------------------------------------------------------
    def add(self, category: str, content: str, **metadata: Any) -> MemoryRecord:
        record = MemoryRecord(category=category, content=content, metadata=metadata)
        self.store_text(content, namespace=category, metadata=metadata)
        return record

    def latest(self, category: str | None = None) -> MemoryRecord | None:
        recent = self.recall_recent(limit=1, namespace=category)
        if not recent:
            return None
        entry = recent[0]
        content = entry.get("value", {}).get("text") if isinstance(entry.get("value"), dict) else entry.get("value")
        if content is None:
            content = entry.get("value", "")
        timestamp_raw = entry.get("updated_at") or entry.get("created_at") or datetime.now(timezone.utc).isoformat()
        try:
            timestamp = datetime.fromisoformat(timestamp_raw)
        except Exception:
            timestamp = datetime.now(timezone.utc)
        return MemoryRecord(category=entry.get("namespace", ""), content=str(content), metadata=entry.get("metadata", {}), timestamp=timestamp)

    def export_state(self) -> Dict[str, Any]:
        return {
            "symbolic": self.symbolic.export_state(),
            "vector": self.vector.export_state(),
        }
