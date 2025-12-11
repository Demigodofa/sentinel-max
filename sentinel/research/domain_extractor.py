"""Domain knowledge extraction utilities."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List

from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class DomainKnowledgeExtractor:
    """Extract structured domain knowledge from raw text documents."""

    def extract(self, docs: List[Dict]) -> Dict:
        """Return structured concepts, entities, processes, and relationships."""

        concepts: set[str] = set()
        entities: set[str] = set()
        processes: set[str] = set()
        relationships: Dict[str, List[str]] = defaultdict(list)
        rules: List[str] = []
        constraints: List[str] = []
        workflows: List[List[str]] = []
        failure_modes: List[str] = []

        for doc in docs:
            text = str(doc.get("content", ""))
            concepts.update(self._extract_keywords(text))
            entities.update(self._extract_entities(text))
            processes.update(self._extract_processes(text))
            relationships.update(self._extract_relationships(text))
            rules.extend(self._extract_rules(text))
            constraints.extend(self._extract_constraints(text))
            workflows.extend(self._extract_workflows(text))
            failure_modes.extend(self._extract_failures(text))

        return {
            "concepts": sorted(concepts),
            "entities": sorted(entities),
            "processes": sorted(processes),
            "relationships": {k: sorted(set(v)) for k, v in relationships.items()},
            "rules": sorted(set(rules)),
            "constraints": sorted(set(constraints)),
            "workflows": workflows,
            "failure_modes": sorted(set(failure_modes)),
        }

    def _extract_keywords(self, text: str) -> List[str]:
        tokens = re.findall(r"[A-Za-z]{4,}", text)
        common = {"with", "from", "this", "that", "have", "which", "using"}
        return [t.lower() for t in tokens if t.lower() not in common]

    def _extract_entities(self, text: str) -> List[str]:
        matches = re.findall(r"([A-Z][a-zA-Z]+\b)", text)
        return [m for m in matches if len(m) > 2]

    def _extract_processes(self, text: str) -> List[str]:
        verbs = re.findall(r"\b(compile|deploy|analyze|extract|simulate|train|update|validate)\w*\b", text, re.IGNORECASE)
        return [v.lower() for v in verbs]

    def _extract_relationships(self, text: str) -> Dict[str, List[str]]:
        relations: Dict[str, List[str]] = defaultdict(list)
        pattern = re.compile(r"(\w+)\s+(depends on|requires|produces|uses)\s+(\w+)", re.IGNORECASE)
        for subject, relation, obj in pattern.findall(text):
            relations[subject.lower()].append(f"{relation.lower()}:{obj.lower()}")
        return relations

    def _extract_rules(self, text: str) -> List[str]:
        return [line.strip() for line in text.splitlines() if line.strip().lower().startswith("must")]

    def _extract_constraints(self, text: str) -> List[str]:
        keywords = ["never", "avoid", "limit", "only"]
        constraints = []
        for line in text.splitlines():
            lower = line.lower()
            if any(k in lower for k in keywords):
                constraints.append(line.strip())
        return constraints

    def _extract_workflows(self, text: str) -> List[List[str]]:
        workflows: List[List[str]] = []
        if "->" in text:
            for chain in text.split("->"):
                steps = [step.strip() for step in chain.split(";") if step.strip()]
                if steps:
                    workflows.append(steps)
        return workflows

    def _extract_failures(self, text: str) -> List[str]:
        failure_keywords = ["fail", "error", "exception", "timeout", "missing"]
        return [sentence.strip() for sentence in text.split(".") if any(k in sentence.lower() for k in failure_keywords)]
