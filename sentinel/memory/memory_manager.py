"""Memory management for Sentinel MAX."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any
from datetime import datetime


@dataclass
class MemoryRecord:
    category: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class MemoryManager:
    """Simple in-memory store for agent observations and reflections."""

    def __init__(self) -> None:
        self.records: List[MemoryRecord] = []

    def add(self, category: str, content: str, **metadata: Any) -> MemoryRecord:
        record = MemoryRecord(category=category, content=content, metadata=metadata)
        self.records.append(record)
        return record

    def query(self, category: str | None = None) -> List[MemoryRecord]:
        if category is None:
            return list(self.records)
        return [rec for rec in self.records if rec.category == category]

    def latest(self, category: str | None = None) -> MemoryRecord | None:
        for rec in reversed(self.records):
            if category is None or rec.category == category:
                return rec
        return None

    def export_state(self) -> Dict[str, Any]:
        return {
            "records": [
                {
                    "category": rec.category,
                    "content": rec.content,
                    "metadata": rec.metadata,
                    "timestamp": rec.timestamp.isoformat(),
                }
                for rec in self.records
            ]
        }
