"""Predictive model for tool behaviors and side effects."""
from __future__ import annotations

import math
from typing import Any, Dict

from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class ToolEffectPredictorV2:
    """Richer predictor capturing outputs, side effects, and failure likelihood."""

    def __init__(self, semantic_profiles: Dict[str, Dict] | None = None) -> None:
        self.semantic_profiles: Dict[str, Dict] = semantic_profiles or {}

    def predict(self, tool_name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        profile = self.semantic_profiles.get(tool_name, {})
        output_template = profile.get("outputs", {})
        vfs_writes = list(profile.get("vfs_writes", []))
        side_effects = list(profile.get("side_effects", profile.get("postconditions", [])))
        failure_likelihood = float(profile.get("failure_likelihood", 0.1))

        for key, value in inputs.items():
            if isinstance(value, str) and any(token in key for token in ["path", "file", "artifact", "output"]):
                vfs_writes.append(value)
            if isinstance(value, list):
                for candidate in value:
                    if isinstance(candidate, str) and "/" in candidate:
                        vfs_writes.append(candidate)

        runtime = self._estimate_runtime(inputs, profile)
        predicted_outputs = output_template or {"echo": f"{tool_name} processed {sorted(inputs.keys())}"}
        metadata = {"semantic_confidence": profile.get("confidence", 0.5)}

        warnings = []
        if failure_likelihood >= 0.5:
            warnings.append("High predicted failure risk")
        if profile.get("preconditions"):
            missing = [p for p in profile["preconditions"] if p not in inputs]
            if missing:
                warnings.append(f"Missing preconditions: {', '.join(missing)}")
                failure_likelihood = min(1.0, failure_likelihood + 0.2)

        return {
            "outputs": predicted_outputs,
            "vfs_writes": sorted(set(vfs_writes)),
            "side_effects": sorted(set(side_effects)),
            "failure_likelihood": round(failure_likelihood, 3),
            "runtime": runtime,
            "metadata": metadata,
            "warnings": warnings,
        }

    def update_model(self, semantic_data: Dict[str, Dict]) -> None:
        for tool, data in semantic_data.items():
            existing = self.semantic_profiles.get(tool, {})
            merged = {**existing, **data}
            if "side_effects" in data and "postconditions" not in merged:
                merged["postconditions"] = data["side_effects"]
            self.semantic_profiles[tool] = merged
        logger.info("ToolEffectPredictorV2 updated with semantics for %d tools", len(semantic_data))

    def _estimate_runtime(self, inputs: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
        size = sum(len(str(v)) for v in inputs.values())
        baseline = 0.05 if profile.get("latency_pattern") == "low" else 0.2
        baseline = 0.5 if profile.get("latency_pattern") == "high" else baseline
        runtime = baseline + math.log1p(size) * 0.01
        return {"seconds": round(runtime, 3), "pattern": profile.get("latency_pattern", "medium")}
