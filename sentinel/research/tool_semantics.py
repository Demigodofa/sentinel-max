"""Tool semantics extraction utilities."""
from __future__ import annotations

from typing import Dict, List

from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class ToolSemanticsExtractor:
    """Infer tool behaviors and IO semantics from research documents."""

    def extract_semantics(self, docs: List[Dict]) -> Dict[str, Dict]:
        semantics: Dict[str, Dict] = {}
        for doc in docs:
            content = str(doc.get("content", "")).lower()
            tool_name = doc.get("metadata", {}).get("tool") or self._guess_tool(content)
            if not tool_name:
                continue
            entry = semantics.setdefault(
                tool_name,
                {
                    "inputs": set(),
                    "outputs": set(),
                    "preconditions": set(),
                    "postconditions": set(),
                    "failure_signatures": set(),
                    "latency_pattern": "medium",
                    "side_effects": set(),
                },
            )
            entry["inputs"].update(self._scan(content, ["input", "parameter", "arg", "requires"]))
            entry["outputs"].update(self._scan(content, ["output", "returns", "produces", "artifact"]))
            entry["preconditions"].update(self._scan(content, ["must", "requires", "needs"]))
            entry["postconditions"].update(self._scan(content, ["creates", "writes", "updates"]))
            entry["failure_signatures"].update(self._scan(content, ["error", "fail", "exception"]))
            if "slow" in content or "latency" in content:
                entry["latency_pattern"] = "high"
            if "fast" in content or "cached" in content:
                entry["latency_pattern"] = "low"
            for keyword in ["write", "file", "side effect", "mutate"]:
                if keyword in content:
                    entry["side_effects"].add(keyword)
        normalized: Dict[str, Dict] = {}
        for tool, data in semantics.items():
            normalized[tool] = {
                "inputs": sorted(data["inputs"]),
                "outputs": sorted(data["outputs"]),
                "preconditions": sorted(data["preconditions"]),
                "postconditions": sorted(data["postconditions"]),
                "failure_signatures": sorted(data["failure_signatures"]),
                "latency_pattern": data["latency_pattern"],
                "side_effects": sorted(data["side_effects"]),
            }
        return normalized

    def merge_with_existing(self, tool_registry, semantics: Dict[str, Dict]) -> Dict[str, Dict]:
        merged: Dict[str, Dict] = {}
        for name, data in semantics.items():
            schema = tool_registry.get_schema(name) if tool_registry and tool_registry.has_tool(name) else None
            baseline = {
                "inputs": list(schema.input_schema) if schema else [],
                "outputs": list(schema.output_schema) if schema else [],
                "preconditions": [],
                "postconditions": [],
                "failure_signatures": [],
                "latency_pattern": "medium",
                "side_effects": [],
            }
            merged[name] = {
                "inputs": sorted(set(baseline["inputs"]) | set(data.get("inputs", []))),
                "outputs": sorted(set(baseline["outputs"]) | set(data.get("outputs", []))),
                "preconditions": sorted(set(data.get("preconditions", []))),
                "postconditions": sorted(set(data.get("postconditions", []))),
                "failure_signatures": sorted(set(data.get("failure_signatures", []))),
                "latency_pattern": data.get("latency_pattern", baseline["latency_pattern"]),
                "side_effects": sorted(set(data.get("side_effects", []))),
            }
        return merged

    def _scan(self, content: str, keywords: List[str]) -> List[str]:
        hits = []
        for token in content.split():
            for keyword in keywords:
                if keyword in token:
                    hits.append(token.strip(",.;"))
        return hits

    def _guess_tool(self, content: str) -> str | None:
        candidates = ["web_search", "internet_extract", "code_analyzer", "microservice_builder"]
        for name in candidates:
            if name.replace("_", " ") in content:
                return name
        return None
