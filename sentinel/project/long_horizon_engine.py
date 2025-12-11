"""Enterprise-grade long-horizon project orchestrator."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from sentinel.dialog.dialog_manager import DialogManager
from sentinel.policy.policy_engine import PolicyEngine, PolicyViolation
from sentinel.project.dependency_graph import ProjectDependencyGraph
from sentinel.project.project_memory import ProjectMemory


class LongHorizonProjectEngine:
    """
    Coordinates long-running projects with durable storage, dependency validation,
    policy enforcement, and human-readable reporting.
    """

    def __init__(
        self,
        *,
        memory: ProjectMemory | None = None,
        policy: PolicyEngine | None = None,
        dialog: DialogManager | None = None,
        dependency_graph: ProjectDependencyGraph | None = None,
    ) -> None:
        self.memory = memory or ProjectMemory()
        self.policy = policy or PolicyEngine()
        self.dialog = dialog or DialogManager()
        self.dependency_graph = dependency_graph or ProjectDependencyGraph()

    # ------------------------------------------------------------------
    # Project lifecycle
    # ------------------------------------------------------------------
    def create_project(self, name: str, description: str, goals: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        project = self.memory.create(name=name, description=description)
        goals = goals or []
        if goals:
            self._persist_goals(project["project_id"], goals)
        self.policy.check_project_limits({"goals": list(goals)})
        return project

    def _persist_goals(self, project_id: str, goals: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = []
        for goal in goals:
            goal_id = goal.get("id") or str(uuid.uuid4())
            normalized.append({
                "id": goal_id,
                "text": goal.get("text", ""),
                "status": goal.get("status", "pending"),
                "metadata": goal.get("metadata", {}),
            })
        data = self.memory.upsert_goals(project_id, normalized)
        self.policy.check_project_limits({"goals": list(data.get("goals", {}).values())})
        return data

    def add_goals(self, project_id: str, goals: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._persist_goals(project_id, goals)

    # ------------------------------------------------------------------
    # Planning lifecycle
    # ------------------------------------------------------------------
    def register_plan(self, project_id: str, steps: List[Dict[str, Any]], plan_id: Optional[str] = None) -> Dict[str, Any]:
        if not steps:
            raise ValueError("Plan steps are required")

        graph = self.dependency_graph.normalize_steps(steps)
        cycles, unresolved = self.dependency_graph.validate(graph)
        if cycles:
            raise PolicyViolation(f"Plan contains dependency cycles: {cycles}")
        if unresolved:
            raise PolicyViolation(f"Plan has unresolved dependencies: {unresolved}")

        depths = self.dependency_graph.compute_depths(graph)
        plan_payload = {
            "plan_id": plan_id or str(uuid.uuid4()),
            "steps": steps,
            "dependencies": graph,
            "metadata": {
                "max_depth": max(depths.values()) if depths else 0,
                "created_at": time.time(),
            },
        }
        self.policy.validate_project_plan(plan_payload)

        self.memory.record_plan(project_id, plan_payload["plan_id"], plan_payload)
        self.memory.record_dependencies(project_id, graph)
        self.memory.append_log(project_id, {"event": "plan_registered", "plan_id": plan_payload["plan_id"]})
        return plan_payload

    # ------------------------------------------------------------------
    # Execution and governance
    # ------------------------------------------------------------------
    def record_step_result(self, project_id: str, step_id: str, status: str, output: Optional[str] = None) -> Dict[str, Any]:
        data = self.memory.load(project_id)
        entry = {
            "event": "step_completed",
            "step_id": step_id,
            "status": status,
            "output": output,
        }
        self.memory.append_log(project_id, entry)
        if step_id in data.get("goals", {}):
            self.memory.set_goal_status(project_id, step_id, status)
        return self.memory.snapshot(project_id)

    def enforce_autonomy(self, project_id: str, state: Dict[str, Any]) -> None:
        self.policy.enforce_autonomy_constraints(project_id, state)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def overview(self, project_id: str) -> str:
        data = self.memory.snapshot(project_id)
        goals = list(data.get("goals", {}).values())
        return self.dialog.show_project_overview({
            "name": data.get("name"),
            "description": data.get("description"),
            "goals": goals,
        })

    def progress_report(self, project_id: str) -> str:
        data = self.memory.snapshot(project_id)
        goals = list(data.get("goals", {}).values())
        completed = [g for g in goals if g.get("status") == "completed"]
        progress = {
            "pct": int((len(completed) / len(goals)) * 100) if goals else 0,
            "completed_goals": len(completed),
            "total_goals": len(goals),
        }
        return self.dialog.show_project_progress(progress)

    def full_report(self, project_id: str) -> str:
        data = self.memory.snapshot(project_id)
        goals = list(data.get("goals", {}).values())
        progress = {
            "pct": int(
                (len([g for g in goals if g.get("status") == "completed"]) / len(goals)) * 100
            ) if goals else 0,
            "completed_goals": len([g for g in goals if g.get("status") == "completed"]),
            "total_goals": len(goals),
        }
        issues = dict(zip(["cycles", "unresolved"], self.dependency_graph.validate(data.get("dependencies", {}))))
        return self.dialog.show_full_report(
            {
                "name": data.get("name"),
                "description": data.get("description"),
                "goals": goals,
            },
            progress,
            issues,
        )

    def dependency_issues(self, project_id: str) -> str:
        graph = self.memory.snapshot(project_id).get("dependencies", {})
        cycles, unresolved = self.dependency_graph.validate(graph)
        return self.dialog.show_dependency_issues({"cycles": cycles, "unresolved": unresolved})

    def milestone_notification(self, title: str, description: str) -> str:
        return self.dialog.notify_milestone({"title": title, "description": description})

    def health_report(self) -> str:
        health = {
            "storage": self.memory.health_check(),
            "policy": {
                "max_goals": self.policy.max_goals,
                "max_dependency_depth": self.policy.max_dependency_depth,
                "max_project_duration_days": self.policy.max_project_duration_days,
                "max_refinement_rounds": self.policy.max_refinement_rounds,
            },
        }
        return self.dialog.show_health(health)

