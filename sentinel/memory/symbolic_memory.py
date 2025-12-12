"""Symbolic memory for structured facts with persistence and namespacing."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class SymbolicMemory:
    """Structured, namespaced memory with reliable persistence.

    Facts are organized by namespace and keyed entries. All operations are
    thread-safe and persisted to disk using atomic file replacement to avoid
    corruption on crash or interruption.
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        base_path = Path(__file__).resolve().parent
        self.storage_path = Path(storage_path) if storage_path else base_path / "symbolic_store.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._namespaces: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            content = self.storage_path.read_text(encoding="utf-8")
            data = json.loads(content) if content else {}
            namespaces = data.get("namespaces", {})
            if isinstance(namespaces, dict):
                self._namespaces = namespaces
        except Exception as exc:  # pragma: no cover - defensive load
            logger.warning("Failed to load symbolic memory: %s", exc)
            self._namespaces = {}

    def _persist(self) -> None:
        payload = {
            "namespaces": self._json_safe(self._namespaces),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        temp_path = self.storage_path.with_suffix(".tmp")
        try:
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp_path, self.storage_path)
        except Exception as exc:  # pragma: no cover - defensive persistence
            logger.error("Failed to persist symbolic memory: %s", exc)
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    logger.debug("Could not remove temp file after persistence failure")

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_namespace(self, namespace: str) -> Dict[str, Dict[str, Any]]:
        return self._namespaces.setdefault(namespace, {})

    def _json_safe(self, value: Any) -> Any:
        """Recursively convert values into JSON-serializable forms."""

        if isinstance(value, dict):
            return {k: self._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe(v) for v in value]
        if isinstance(value, set):
            return [self._json_safe(v) for v in sorted(value, key=lambda x: str(x))]
        if isinstance(value, datetime):
            return value.isoformat()
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    def create(
        self,
        namespace: str,
        key: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
        allow_overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Create a fact; optionally prevent overwriting existing entries."""
        with self._lock:
            ns = self._ensure_namespace(namespace)
            if not allow_overwrite and key in ns:
                raise KeyError(f"Fact '{namespace}:{key}' already exists")
            record = ns.get(key, {})
            created_at = record.get("created_at", self._timestamp())
            stored = {
                "key": key,
                "namespace": namespace,
                "value": self._json_safe(value),
                "metadata": self._json_safe(metadata or {}),
                "created_at": created_at,
                "updated_at": self._timestamp(),
            }
            ns[key] = stored
            self._persist()
            return dict(stored)

    def read(self, namespace: str, key: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            ns = self._namespaces.get(namespace, {})
            if key is None:
                return [dict(item) for item in ns.values()]
            return [dict(ns[key])] if key in ns else []

    def update(
        self,
        namespace: str,
        key: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            ns = self._ensure_namespace(namespace)
            if key not in ns:
                raise KeyError(f"Cannot update missing fact '{namespace}:{key}'")
            stored = ns[key]
            stored.update(
                {
                    "value": self._json_safe(value),
                    "metadata": self._json_safe(metadata or stored.get("metadata", {})),
                    "updated_at": self._timestamp(),
                }
            )
            ns[key] = stored
            self._persist()
            return dict(stored)

    def delete(self, namespace: str, key: str) -> bool:
        with self._lock:
            ns = self._namespaces.get(namespace)
            if ns is None or key not in ns:
                return False
            ns.pop(key)
            if not ns:
                self._namespaces.pop(namespace, None)
            self._persist()
            return True

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def list_namespaces(self) -> List[str]:
        with self._lock:
            return list(self._namespaces.keys())

    def add_fact(self, fact: Dict[str, Any]) -> Dict[str, Any]:
        """Compat wrapper that stores a fact using namespace + key metadata."""
        namespace = fact.get("namespace", "default")
        key = fact.get("key") or fact.get("id") or self._timestamp()
        value = fact.get("value", fact)
        metadata = fact.get("metadata", {})
        return self.create(namespace, key, value, metadata=metadata, allow_overwrite=True)

    def export_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "namespaces": self._json_safe(self._namespaces),
                "last_updated": self._timestamp(),
            }
