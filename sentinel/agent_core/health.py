# sentinel/agent_core/health.py
# Adaptive Health + Performance Engine for Sentinel MAX

from __future__ import annotations

import time
import threading
from typing import Any, Dict, List, Optional
from statistics import mean

from sentinel.logging.logger import get_logger

log = get_logger(__name__)


class PerformanceTracker:
    """
    Tracks performance signals:
      - step durations
      - tool success rate
      - failure rate
      - improvement after reflection
      - browser agent responsiveness
      - plan/goal convergence
    """

    def __init__(self):
        self.step_times: List[float] = []
        self.tool_successes = 0
        self.tool_failures = 0
        self.reflection_improvements = 0
        self.browser_failures = 0
        self.stalls = 0

    # ---------------------------------------------------------

    def record_step_time(self, duration: float):
        self.step_times.append(duration)
        if len(self.step_times) > 200:
            self.step_times = self.step_times[-200:]

    def record_tool_success(self):
        self.tool_successes += 1

    def record_tool_failure(self):
        self.tool_failures += 1

    def record_browser_failure(self):
        self.browser_failures += 1

    def record_stall(self):
        self.stalls += 1

    def record_reflection_improvement(self):
        self.reflection_improvements += 1

    # ---------------------------------------------------------

    def score(self) -> float:
        """
        Produce a 0–100 performance score.
        Weighted blend of different signals.
        """

        if not self.step_times:
            return 50.0

        avg_time = mean(self.step_times)
        successes = self.tool_successes
        failures = self.tool_failures
        stalls = self.stalls

        # Base: faster steps = higher score
        time_score = max(10, min(100, 120 - avg_time * 10))

        # Success/failure ratio
        if successes + failures == 0:
            tool_score = 60
        else:
            ratio = successes / max(1, (successes + failures))
            tool_score = ratio * 100

        stall_penalty = max(0, 20 - stalls * 5)

        final = (time_score * 0.5) + (tool_score * 0.4) + (stall_penalty * 0.1)

        return max(0, min(100, final))

    def export(self) -> Dict[str, Any]:
        return {
            "avg_step_time": mean(self.step_times) if self.step_times else None,
            "tool_successes": self.tool_successes,
            "tool_failures": self.tool_failures,
            "browser_failures": self.browser_failures,
            "stalls": self.stalls,
            "performance_score": self.score(),
        }


class HallucinationDetector:
    """
    Detects hallucinations at the AGENT level:
      - nonexistent tools
      - invalid selectors
      - contradictory memory writes
      - plan drift between steps
    """

    def __init__(self, registry):
        self.registry = registry
        self.prev_plan = None
        self.prev_action = None

    def validate_tool(self, tool_name: str) -> bool:
        return tool_name in self.registry.tools

    def detect_plan_drift(self, plan) -> bool:
        if self.prev_plan is None:
            self.prev_plan = plan
            return False

        if plan == self.prev_plan:
            return True  # repeated plan = stuck

        self.prev_plan = plan
        return False

    def detect_selector_hallucination(self, selector: str) -> bool:
        if selector is None:
            return False
        if not isinstance(selector, str):
            return True
        # Long-term: integrate DOM introspection feedback
        return False

    def detect(self, step: Dict[str, Any]) -> List[str]:
        errors = []

        tool = step.get("tool")
        selector = step.get("selector")

        if tool and not self.validate_tool(tool):
            errors.append(f"Invalid tool: {tool}")

        if self.detect_selector_hallucination(selector):
            errors.append(f"Invalid selector: {selector}")

        return errors


class LoopGuard:
    """
    Protects against infinite loops, repeated actions,
    lack of progress, and runaway step times.
    """

    def __init__(self):
        self.previous_actions: List[str] = []
        self.max_history = 10
        self.max_step_time = 8.0  # seconds
        self.max_repeats = 4

    # ---------------------------------------------------------

    def check_step_time(self, duration: float) -> bool:
        return duration > self.max_step_time

    def check_repetition(self, action_repr: str) -> bool:
        self.previous_actions.append(action_repr)
        if len(self.previous_actions) > self.max_history:
            self.previous_actions = self.previous_actions[-self.max_history:]

        recent = self.previous_actions[-self.max_repeats:]
        return len(recent) >= self.max_repeats and all(a == action_repr for a in recent)

    # ---------------------------------------------------------

    def export(self) -> Dict[str, Any]:
        return {
            "recent_actions": self.previous_actions[-5:],
            "max_step_time": self.max_step_time,
            "max_repeats": self.max_repeats,
        }


class HealthMonitor:
    """
    Central health system for Sentinel MAX.
    Integrated into the autonomy loop.

    Provides:
      - performance scoring
      - hallucination detection
      - loop guard
      - recovery suggestions
      - health state export
    """

    def __init__(self, registry):
        self.registry = registry
        self.performance = PerformanceTracker()
        self.hallu = HallucinationDetector(registry)
        self.loop_guard = LoopGuard()

    # ---------------------------------------------------------

    def evaluate_step(self, step: Dict[str, Any], duration: float) -> Dict[str, Any]:
        """Evaluate a completed step and produce health signals."""

        self.performance.record_step_time(duration)

        # Tool results
        if step.get("error"):
            self.performance.record_tool_failure()
        else:
            self.performance.record_tool_success()

        # Hallucination detection
        hallucinations = self.hallu.detect(step)

        # Loop danger checks
        repeated = self.loop_guard.check_repetition(str(step))
        slow = self.loop_guard.check_step_time(duration)

        health = {
            "hallucinations": hallucinations,
            "repeated_action": repeated,
            "slow_step": slow,
            "score": self.performance.score(),
        }

        return health

    # ---------------------------------------------------------

    def needs_recovery(self, health: Dict[str, Any]) -> bool:
        """Adaptive mode: If score is low OR hallucination OR loop detected → recover."""

        if health["score"] < 40:
            return True
        if health["hallucinations"]:
            return True
        if health["repeated_action"]:
            return True
        if health["slow_step"]:
            return True
        return False

    # ---------------------------------------------------------

    def recovery_strategy(self, health: Dict[str, Any]) -> str:
        """Return the recommended recovery action."""

        if health["hallucinations"]:
            return "inject_reflection"
        if health["repeated_action"]:
            return "replan"
        if health["slow_step"]:
            return "retry_with_backoff"
        if health["score"] < 40:
            return "inject_reflection"

        return "continue"

    # ---------------------------------------------------------

    def export_state(self) -> Dict[str, Any]:
        return {
            "performance": self.performance.export(),
            "loop_guard": self.loop_guard.export(),
        }


__all__ = [
    "HealthMonitor",
    "PerformanceTracker",
    "LoopGuard",
    "HallucinationDetector",
]
