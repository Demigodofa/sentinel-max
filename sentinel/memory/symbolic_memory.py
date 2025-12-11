"""Symbolic memory for structured facts."""
from __future__ import annotations

from typing import Dict, List, Any


class SymbolicMemory:
    def __init__(self) -> None:
        self.facts: List[Dict[str, Any]] = []

    def add_fact(self, fact: Dict[str, Any]) -> None:
        self.facts.append(fact)

    def find(self, key: str, value: Any) -> List[Dict[str, Any]]:
        return [fact for fact in self.facts if fact.get(key) == value]

    def export_state(self) -> Dict[str, Any]:
        return {"facts": list(self.facts)}
