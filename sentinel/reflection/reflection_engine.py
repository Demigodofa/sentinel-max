"""Reflection engine with multi-dimensional reasoning."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sentinel.logging.logger import get_logger
from sentinel.memory.intelligence import MemoryContextBuilder
from sentinel.memory.memory_manager import MemoryManager
from sentinel.policy.policy_engine import PolicyEngine

logger = get_logger(__name__)


class ReflectionEngine:
    """Generate actionable reflections that can drive replanning."""

    def __init__(
        self,
        memory: MemoryManager,
        policy_engine: PolicyEngine,
        memory_context_builder: Optional[MemoryContextBuilder] = None,
    ) -> None:
        self.memory = memory
        self.policy_engine = policy_engine
        self.memory_context_builder = memory_context_builder or MemoryContextBuilder(memory)

    def reflect(
        self,
        trace: Any,
        reflection_type: str = "operational",
        goal: str | None = None,
        correlation_id: str | None = None,
    ) -> Dict[str, Any]:
        issues = self._detect_issues(trace)
        simulation_insights = self._simulation_insights(trace)
        if simulation_insights.get("warnings"):
            issues.append("simulation_warnings")
        if simulation_insights.get("predicted_failures"):
            issues.append("simulation_failures")
        policy_outcomes = self._policy_outcomes(trace)
        if policy_outcomes.get("blocked"):
            issues.append("policy_blocked")
        suggestions = self._suggest_improvements(trace, issues, simulation_insights)
        if policy_outcomes.get("suggested_fixes"):
            suggestions.extend(policy_outcomes["suggested_fixes"])
        plan_adjustment = self._plan_adjustment(trace, issues)
        summary = self._summarize(trace, issues, suggestions, policy_outcomes)
        context = self._memory_context(goal) if goal else ""
        reflection = {
            "summary": summary,
            "issues_detected": issues,
            "improvement_suggestions": suggestions,
            "root_cause": issues[0] if issues else "none",
            "plan_adjustment": plan_adjustment,
            "context": context,
            "reflection_type": reflection_type,
            "confidence": self._confidence(trace, issues),
            "simulation": simulation_insights,
            "correlation_id": correlation_id,
        }
        self._persist(reflection, reflection_type, correlation_id=correlation_id)
        decision = self.policy_engine.advise(issues)
        if not decision.allowed:
            reflection["policy_advice"] = decision.to_dict()
        return reflection

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _detect_issues(self, trace: Any) -> List[str]:
        issues: List[str] = []
        failed = getattr(trace, "failed_nodes", []) or []
        if failed:
            issues.append("execution_failures")
        if not getattr(trace, "results", []):
            issues.append("no_results")
        return issues

    def _suggest_improvements(self, trace: Any, issues: List[str], simulation: Dict[str, Any]) -> List[str]:
        suggestions: List[str] = []
        if "execution_failures" in issues:
            suggestions.append("Retry failed tasks with adjusted inputs")
        if "no_results" in issues:
            suggestions.append("Expand search scope or enrich inputs")
        if simulation.get("warnings"):
            suggestions.append("Resolve simulation warnings before live execution")
        if simulation.get("predicted_failures"):
            suggestions.append("Reorder or adjust tasks flagged by simulation")
        if simulation.get("slow_paths"):
            suggestions.append("Optimize predicted slow tasks using benchmark notes")
        if not suggestions:
            suggestions.append("Continue current strategy")
        return suggestions

    def _plan_adjustment(self, trace: Any, issues: List[str]) -> Dict[str, Any]:
        if not issues:
            return {"action": "none"}
        return {"action": "replan", "focus": issues}

    def _summarize(
        self,
        trace: Any,
        issues: List[str],
        suggestions: List[str],
        policy_outcomes: Dict[str, Any],
    ) -> str:
        blocked = policy_outcomes.get("blocked") or []
        rewrites = policy_outcomes.get("rewrites") or []
        policy_bits = []
        if blocked:
            policy_bits.append(f"blocked={len(blocked)}")
        if rewrites:
            policy_bits.append(f"rewrites={len(rewrites)}")
        policy_summary = f" policy={' '.join(policy_bits)}" if policy_bits else ""
        return (
            f"Trace results={len(getattr(trace, 'results', []))}, issues={issues}, suggestions={suggestions}"\
            f"{policy_summary}"
        )

    def _confidence(self, trace: Any, issues: List[str]) -> float:
        base = 0.8
        if issues:
            base -= 0.2 * len(issues)
        return max(base, 0.1)

    def _simulation_insights(self, trace: Any) -> Dict[str, Any]:
        warnings: List[str] = []
        predicted_failures: List[str] = []
        slow_paths: List[str] = []
        for result in getattr(trace, "results", []) or []:
            simulation = getattr(result, "simulation", None)
            if not simulation:
                continue
            warnings.extend(simulation.warnings)
            if not simulation.success:
                predicted_failures.append(result.node.id)
            if simulation.benchmark.get("relative_speed", 10) < 5:
                slow_paths.append(result.node.id)
        return {
            "warnings": warnings,
            "predicted_failures": predicted_failures,
            "slow_paths": slow_paths,
        }

    def _policy_outcomes(self, trace: Any) -> Dict[str, Any]:
        blocked: List[Dict[str, Any]] = []
        rewrites: List[Dict[str, Any]] = []
        suggested_fixes: List[str] = []
        for result in getattr(trace, "results", []) or []:
            policy = getattr(result, "policy", None)
            if not policy:
                continue
            if policy.rewrites:
                rewrites.append({"task": result.node.id, "rewrites": policy.rewrites})
            if not policy.allowed:
                blocked.append({"task": result.node.id, "reasons": policy.reasons})
                if policy.reasons:
                    suggested_fixes.append(
                        f"Adjust task {result.node.id} to satisfy policy: {', '.join(policy.reasons)}"
                    )
        return {
            "blocked": blocked,
            "rewrites": rewrites,
            "suggested_fixes": suggested_fixes,
        }

    def _memory_context(self, goal: str) -> str:
        _, context_block = self.memory_context_builder.build_context(goal, "reflection", limit=3)
        return context_block

    def _persist(self, reflection: Dict[str, Any], reflection_type: str, correlation_id: str | None = None) -> None:
        try:
            metadata = {"summary": reflection.get("summary", ""), "confidence": reflection.get("confidence"), "type": reflection_type}
            namespace = f"reflection.{reflection_type}"
            self.memory.store_fact(namespace, key=None, value=reflection, metadata=metadata)
            self.memory.store_text(
                str(reflection),
                namespace=f"reflection.{reflection_type}",
                metadata={
                    "summary": reflection.get("summary", ""),
                    "confidence": reflection.get("confidence"),
                    "correlation_id": correlation_id,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to persist reflection: %s", exc)
