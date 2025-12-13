"""Memory intelligence layer for ranked, contextual recall."""
from __future__ import annotations

import math
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager

logger = get_logger(__name__)


@dataclass
class RankedMemory:
    score: float
    record: Dict[str, Any]


class MemoryRanker:
    """Rank memories using semantic similarity, recency decay, and goal-type hints."""

    def __init__(self, memory: MemoryManager) -> None:
        self.memory = memory

    def _timestamp_score(self, timestamp_str: str) -> float:
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except Exception:
            return 0.5
        age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()
        return 1 / (1 + math.log1p(max(age_seconds, 0)))

    def _goal_match_score(self, metadata: Dict[str, Any], goal_type: str) -> float:
        tags = metadata.get("tags") or metadata.get("type")
        if not tags:
            return 0.0
        if isinstance(tags, str):
            return 1.0 if goal_type in tags else 0.3
        if isinstance(tags, list):
            return 1.0 if goal_type in tags else 0.3 if tags else 0.0
        return 0.0

    def rank(self, goal: str, goal_type: str, limit: int = 5) -> List[RankedMemory]:
        semantic_hits = self.memory.semantic_search(goal, top_k=limit * 2) if hasattr(self.memory, "semantic_search") else []
        recent_hits = self.memory.recall_recent(limit=limit * 2)
        combined: List[Dict[str, Any]] = semantic_hits + recent_hits
        ranked: List[RankedMemory] = []
        seen_keys: set[str] = set()
        for record in combined:
            namespace = record.get("namespace") or record.get("metadata", {}).get("namespace", "")
            rec_key = f"{namespace}:{record.get('id') or record.get('key') or record.get('value', {}).get('symbolic_key', '')}"
            if rec_key in seen_keys:
                continue
            seen_keys.add(rec_key)
            metadata = record.get("metadata", {})
            similarity = float(record.get("score", 0.5))
            timestamp_raw = record.get("created_at") or record.get("updated_at") or metadata.get("timestamp", "")
            freshness = self._timestamp_score(timestamp_raw) if timestamp_raw else 0.5
            goal_score = self._goal_match_score(metadata, goal_type)
            total = (similarity * 0.5) + (freshness * 0.3) + (goal_score * 0.2)
            ranked.append(RankedMemory(score=total, record=record))
        ranked.sort(key=lambda r: r.score, reverse=True)
        if not ranked:
            logger.info("MemoryRanker: no records found, returning empty ranking")
        report = [{"score": r.score, "namespace": r.record.get("namespace"), "metadata": r.record.get("metadata", {})} for r in ranked[:limit]]
        if report:
            try:
                self.memory.store_text(
                    str(report),
                    namespace="memory_rank_reports",
                    metadata={"goal": goal, "goal_type": goal_type},
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to store memory rank report: %s", exc)
        return ranked[:limit]


class MemoryFilter:
    """Filter out noisy, duplicate, or low-signal memories."""

    def __init__(self, min_length: int = 10) -> None:
        self.min_length = min_length

    def filter(self, ranked: List[RankedMemory]) -> List[RankedMemory]:
        seen_content: set[str] = set()
        filtered: List[RankedMemory] = []
        for item in ranked:
            content = item.record.get("text") or item.record.get("value", {}).get("text") or str(item.record.get("value", ""))
            if not content or len(content) < self.min_length:
                continue
            metadata = item.record.get("metadata", {})
            if metadata.get("namespace", "").startswith("reflection.self-model"):
                continue
            content_key = content.strip()
            if content_key in seen_content:
                continue
            seen_content.add(content_key)
            filtered.append(item)
        return filtered


class MemoryContextBuilder:
    """Construct curated memory context windows for planning and reflection."""

    def __init__(self, memory: MemoryManager, ranker: Optional[MemoryRanker] = None, mem_filter: Optional[MemoryFilter] = None) -> None:
        self.memory = memory
        self.ranker = ranker or MemoryRanker(memory)
        self.filter = mem_filter or MemoryFilter()

    def build_context(self, goal: str, goal_type: str, limit: int = 5) -> Tuple[List[Dict[str, Any]], str]:
        ranked = self.ranker.rank(goal, goal_type, limit=limit)
        curated = self.filter.filter(ranked)
        context_strings: List[str] = []
        for item in curated:
            metadata = item.record.get("metadata", {})
            text = item.record.get("text") or item.record.get("value", {}).get("text") or str(item.record.get("value", ""))
            context_strings.append(f"[{metadata.get('namespace', metadata.get('category', ''))}] {text}")
        context_block = "\n".join(context_strings)
        ranked_payload = []
        for item in ranked:
            metadata = item.record.get("metadata", {})
            ranked_payload.append(
                {
                    "score": item.score,
                    "namespace": item.record.get("namespace", metadata.get("namespace")),
                    "metadata": metadata,
                    "text": item.record.get("text")
                    or item.record.get("value", {}).get("text")
                    or str(item.record.get("value", "")),
                }
            )
        payload = {
            "goal": goal,
            "goal_type": goal_type,
            "count": len(curated),
            "ranked": ranked_payload,
            "context_block": context_block,
        }
        try:
            self.memory.store_fact(
                "memory_contexts",
                key=None,
                value=payload,
                metadata={
                    "goal": goal,
                    "goal_type": goal_type,
                    "count": len(curated),
                    "ranked": len(ranked_payload),
                    "type": "context_window",
                },
            )
            self.memory.store_text(
                json.dumps(payload, ensure_ascii=False),
                namespace="memory_contexts",
                metadata={
                    "goal": goal,
                    "goal_type": goal_type,
                    "count": len(curated),
                    "ranked": len(ranked_payload),
                    "type": "context_window",
                },
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to store memory context: %s", exc)
        return [item.record for item in curated], context_block
