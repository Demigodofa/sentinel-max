"""Plan publishing helpers for the plan panel."""
from __future__ import annotations

import time
from typing import Dict, List, Optional
from uuid import uuid4

from sentinel.memory.memory_manager import MemoryManager

_DEFAULT_PUBLISHER: "PlanPublisher | None" = None


class PlanPublisher:
    """Persist plan steps in memory so the Plan panel can render them."""

    def __init__(self, memory: MemoryManager):
        self.memory = memory

    def publish_plan(self, goal: str, steps: List[Dict]) -> str:
        plan_id = str(uuid4())
        normalized = []
        for idx, step in enumerate(steps, start=1):
            normalized.append(
                {
                    "step_id": step.get("step_id", idx),
                    "description": step.get("description", ""),
                    "tool_name": step.get("tool_name"),
                    "params": step.get("params", {}),
                    "status": step.get("status", "queued"),
                    "note": step.get("note"),
                }
            )
        payload = {
            "plan_id": plan_id,
            "goal": goal,
            "version": 1,
            "steps": normalized,
            "timestamp": time.time(),
        }
        self.memory.store_fact("plans", key=plan_id, value=payload, metadata={"goal": goal, "version": 1})
        return plan_id

    def update_step(
        self,
        plan_id: str,
        step_id: int,
        status: str,
        note: Optional[str] = None,
        description: Optional[str] = None,
        tool_name: Optional[str] = None,
        params: Optional[Dict] = None,
    ) -> Dict:
        records = self.memory.query("plans", key=plan_id)
        if records:
            plan = records[0].get("value", {})
        else:
            plan = {"plan_id": plan_id, "goal": "", "version": 0, "steps": []}

        steps = plan.get("steps") or []
        existing = None
        for step in steps:
            if step.get("step_id") == step_id:
                existing = step
                break
        if existing is None:
            existing = {
                "step_id": step_id,
                "description": description or f"Step {step_id}",
                "tool_name": tool_name,
                "params": params or {},
                "status": "queued",
            }
            steps.append(existing)

        if description:
            existing["description"] = description
        if tool_name:
            existing["tool_name"] = tool_name
        if params:
            existing["params"] = params
        existing["status"] = status
        if note:
            existing["note"] = note
        existing["updated_at"] = time.time()

        plan["steps"] = steps
        plan["version"] = int(plan.get("version", 0)) + 1
        self.memory.store_fact("plans", key=plan_id, value=plan, metadata={"goal": plan.get("goal", ""), "version": plan["version"]})
        return plan


def configure_plan_memory(memory: MemoryManager) -> None:
    global _DEFAULT_PUBLISHER
    _DEFAULT_PUBLISHER = PlanPublisher(memory)


def publish_plan(goal: str, steps: List[Dict]) -> str:
    if _DEFAULT_PUBLISHER is None:
        raise RuntimeError("Plan publisher not configured")
    return _DEFAULT_PUBLISHER.publish_plan(goal, steps)


def update_step(plan_id: str, step_id: int, status: str, note: Optional[str] = None) -> Dict:
    if _DEFAULT_PUBLISHER is None:
        raise RuntimeError("Plan publisher not configured")
    return _DEFAULT_PUBLISHER.update_step(plan_id, step_id, status, note=note)
