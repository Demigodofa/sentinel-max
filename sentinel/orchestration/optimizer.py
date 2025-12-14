"""Optimizer that applies learnings after orchestration runs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.registry import ToolRegistry

logger = get_logger(__name__)


class Optimizer:
    """Persist alias mappings and intent rules for future runs."""

    def __init__(self, tool_registry: ToolRegistry, memory: MemoryManager):
        self.tool_registry = tool_registry
        self.memory = memory
        self.alias_file = self.memory.base_dir / "tool_aliases.json"
        self.intent_rules_file = self.memory.base_dir / "intent_rules.json"

    def optimize(
        self,
        *,
        tool_events: Optional[Iterable[Dict]] = None,
        reflections: Optional[Dict] = None,
        corrections: Optional[List[Dict]] = None,
    ) -> Dict[str, int | str]:
        alias_rules = self._collect_alias_rules(tool_events)
        intent_rules = self._collect_intent_rules(corrections)
        alias_count = self._persist_alias_rules(alias_rules)
        intent_count = self._persist_intent_rules(intent_rules)
        message = (
            f"Optimizer applied: saved {alias_count} new alias rules; "
            f"stored {intent_count} intent rule{'s' if intent_count != 1 else ''}"
        )
        logger.info(message)
        self.memory.store_fact(
            "optimizer_runs",
            key=None,
            value={"alias_rules": alias_rules, "intent_rules": intent_rules, "message": message},
        )
        return {"alias_rules": alias_count, "intent_rules": intent_count, "message": message}

    def _collect_alias_rules(self, tool_events: Optional[Iterable[Dict]]) -> Dict[str, Dict[str, str | None]]:
        rules: Dict[str, Dict[str, str | None]] = {}
        events = list(tool_events or self.memory.query("tool_events"))
        for event in events:
            payload = event.get("value", event) if isinstance(event, dict) else {}
            if payload.get("event") != "tool_repair":
                continue
            tool = payload.get("tool")
            alias = payload.get("dropped_arg")
            if not tool or not alias:
                continue
            rules.setdefault(tool, {})[alias] = None
        return rules

    def _collect_intent_rules(self, corrections: Optional[List[Dict]]) -> List[Dict]:
        collected: List[Dict] = []
        if corrections:
            collected.extend(corrections)
        existing = self.memory.recall_recent(namespace="intent_rules", limit=20)
        for record in existing:
            value = record.get("value") or {}
            if isinstance(value, dict):
                collected.append(value)
        return collected

    def _persist_alias_rules(self, rules: Dict[str, Dict[str, str | None]]) -> int:
        if not rules:
            return 0
        path = Path(self.alias_file)
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        else:
            existing = {}

        changed = 0
        for tool, aliases in rules.items():
            current = existing.setdefault(tool, {})
            for alias, target in aliases.items():
                if alias in current:
                    continue
                current[alias] = target
                changed += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        try:
            self.tool_registry.configure_alias_persistence(self.memory.base_dir)
        except Exception:  # pragma: no cover - defensive
            logger.debug("Alias persistence already configured")
        return changed

    def _persist_intent_rules(self, rules: List[Dict]) -> int:
        if not rules:
            return 0
        stored = 0
        for rule in rules:
            self.memory.store_fact("intent_rules", key=None, value=rule)
            stored += 1
        if rules:
            payload = self.intent_rules_file
            payload.parent.mkdir(parents=True, exist_ok=True)
            try:
                payload.write_text(json.dumps(rules, indent=2), encoding="utf-8")
            except Exception:  # pragma: no cover - defensive
                logger.warning("Failed to persist intent rules to disk")
        return stored
