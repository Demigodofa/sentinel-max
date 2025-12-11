"""Long-horizon project engine for Sentinel MAX."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List

from sentinel.project.project_memory import ProjectMemory
from sentinel.project.dependency_graph import ProjectDependencyGraph
from sentinel.agent_core.planner import SentinelPlanner
from sentinel.agent_core.worker import SentinelWorker
from sentinel.agent_core.reflection import ReflectionEngine
from sentinel.agent_core.autonomy import AutonomyLoop
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import TaskGraph, TaskNode


@dataclass
class PlanStep:
    """Normalized representation of a planned action."""

    action: Any
    depends_on: List[str]


class LongHorizonProjectEngine:
    """
    Manages multi-day, multi-phase long-horizon projects.
    Tracks goals, dependencies, plans, reflections, execution progress,
    and interacts with the Planner, Worker, Memory, and AutonomyLoop.
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        planner: SentinelPlanner,
        worker: SentinelWorker,
        reflection_engine: ReflectionEngine,
        autonomy_loop: AutonomyLoop,
        storage_path: str = "projects",
    ) -> None:
        self.memory = memory_manager
        self.planner = planner
        self.worker = worker
        self.reflection = reflection_engine
        self.autonomy = autonomy_loop

        self.project_memory = ProjectMemory(storage_path)
        self.dep_graph = ProjectDependencyGraph()

    # ------------------------------------------------------------
    # PROJECT CREATION & LOADING
    # ------------------------------------------------------------

    def create_project(self, name: str, description: str) -> Dict[str, Any]:
        """Create a new long-horizon project with metadata."""
        data = self.project_memory.create(name, description)
        return data

    def load_project(self, project_id: str) -> Dict[str, Any]:
        """Load project data."""
        return self.project_memory.load(project_id)

    def save_project(self, project_id: str, project_data: Dict[str, Any]) -> None:
        """Persist project updates."""
        self.project_memory.save(project_id, project_data)

    # ------------------------------------------------------------
    # GOAL MANAGEMENT
    # ------------------------------------------------------------

    def add_goal(self, project_id: str, goal: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new long-horizon goal and attach metadata."""
        project = self.load_project(project_id)

        goal_id = str(uuid.uuid4())
        project.setdefault("goals", {})[goal_id] = {
            "goal_id": goal_id,
            "goal": goal,
            "metadata": metadata,
            "status": "pending",
            "created_at": time.time(),
            "updated_at": time.time(),
        }

        self.save_project(project_id, project)
        return project["goals"][goal_id]

    def update_goal_status(self, project_id: str, goal_id: str, status: str) -> None:
        """Update the status of a long-horizon goal."""
        project = self.load_project(project_id)
        if goal_id not in project.get("goals", {}):
            raise ValueError(f"Unknown goal: {goal_id}")

        project["goals"][goal_id]["status"] = status
        project["goals"][goal_id]["updated_at"] = time.time()

        self.save_project(project_id, project)

    # ------------------------------------------------------------
    # LONG-HORIZON PLANNING
    # ------------------------------------------------------------

    def build_long_horizon_plan(self, project_id: str) -> Dict[str, Any]:
        """
        Create a multi-phase plan across all active goals.
        Planner is invoked using goal text + metadata.
        """
        project = self.load_project(project_id)
        goals = project.get("goals", {})

        plan: Dict[str, Any] = {}
        phase = 1

        for goal_id, goal_data in goals.items():
            if goal_data.get("status") not in ("pending", "in_progress"):
                continue

            goal_text = goal_data["goal"]
            plan_steps = self._normalize_plan_steps(self.planner.plan(goal_text))

            for step in plan_steps:
                step_id = str(uuid.uuid4())
                plan[step_id] = {
                    "step_id": step_id,
                    "goal_id": goal_id,
                    "project_id": project_id,
                    "phase": phase,
                    "action": step.action,
                    "depends_on": step.depends_on or [],
                    "status": "pending",
                }

            phase += 1

        project["plans"] = plan
        self.save_project(project_id, project)

        return plan

    def _normalize_plan_steps(self, raw_steps: Any) -> List[PlanStep]:
        if isinstance(raw_steps, TaskGraph):
            return self._from_taskgraph(raw_steps)

        normalized: List[PlanStep] = []
        for item in raw_steps or []:
            if isinstance(item, PlanStep):
                normalized.append(item)
                continue
            depends = []
            action: Any = None
            if isinstance(item, dict):
                action = item.get("action") or item.get("description") or item.get("goal")
                depends = item.get("depends_on") or item.get("requires") or []
            else:
                action = getattr(item, "action", None) or getattr(item, "description", None) or str(item)
                depends = getattr(item, "depends_on", None) or getattr(item, "requires", None) or []
            normalized.append(PlanStep(action=action, depends_on=list(depends)))
        return normalized

    def _from_taskgraph(self, graph: TaskGraph) -> List[PlanStep]:
        produces_to_node: Dict[str, str] = {}
        for node in graph:
            if isinstance(node, TaskNode):
                for artifact in node.produces:
                    produces_to_node[artifact] = node.id
        steps: List[PlanStep] = []
        for node in graph:
            if not isinstance(node, TaskNode):
                continue
            dependencies = [produces_to_node[r] for r in node.requires if r in produces_to_node]
            action = node.description or node.tool or node.id
            steps.append(PlanStep(action=action, depends_on=dependencies))
        return steps

    # ------------------------------------------------------------
    # DEPENDENCY ANALYSIS
    # ------------------------------------------------------------

    def track_dependencies(self, project_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Produce full dependency graph, detect cycles/unresolved links,
        and store results.
        """
        graph = self.dep_graph.build(plan)
        cycles = self.dep_graph.detect_cycles(graph)
        unresolved = self.dep_graph.find_unresolved(graph)
        ordering = self.dep_graph.topological_sort(graph)

        result = {
            "graph": graph,
            "cycles": cycles,
            "unresolved": unresolved,
            "order": ordering,
        }

        project = self.load_project(project_id)
        project["dependencies"] = result
        self.save_project(project_id, project)

        return result

    # ------------------------------------------------------------
    # PROGRESS TRACKING
    # ------------------------------------------------------------

    def evaluate_progress(self, project_id: str) -> Dict[str, Any]:
        """Compute progress based on completed plan steps and goal status."""
        project = self.load_project(project_id)

        plan = project.get("plans", {})
        total = len(plan)
        completed = len([s for s in plan.values() if s.get("status") == "completed"])

        goal_status = {gid: g.get("status") for gid, g in project.get("goals", {}).items()}

        progress = {
            "completed_steps": completed,
            "total_steps": total,
            "pct": (completed / total * 100.0) if total > 0 else 0.0,
            "goals": goal_status,
            "timestamp": time.time(),
        }

        self.project_memory.append_log(project_id, {"type": "progress", "details": progress})

        return progress

    # ------------------------------------------------------------
    # PROJECT REFINEMENT
    # ------------------------------------------------------------

    def refine_project_plan(self, project_id: str, issues: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger re-planning when problems arise:
            - dependency cycles
            - unresolved items
            - reflection issues
        """
        self.load_project(project_id)

        new_plan = self.build_long_horizon_plan(project_id)

        deps = self.track_dependencies(project_id, new_plan)

        self.project_memory.append_reflection(
            project_id,
            {"type": "refine_plan", "issues": issues, "new_plan_size": len(new_plan)},
        )

        return {"plan": new_plan, "dependencies": deps}

    # ------------------------------------------------------------
    # AUTONOMY LOOP INTEGRATION
    # ------------------------------------------------------------

    def run_project_cycle(self, project_id: str) -> Dict[str, Any]:
        """
        Execute a single long-horizon cycle:
            - load project
            - determine active goals + steps
            - execute ordered steps
            - reflect + refine
            - write memory + logs
        """
        project = self.load_project(project_id)
        plan = project.get("plans")

        if not plan:
            plan = self.build_long_horizon_plan(project_id)
            self.track_dependencies(project_id, plan)
            project = self.load_project(project_id)

        deps = project.get("dependencies", {})
        order = deps.get("order", [])

        for step_id in order:
            step = plan.get(step_id)
            if not step or step.get("status") != "pending":
                continue

            result = self._execute_step(step)

            step["status"] = "completed" if getattr(result, "success", False) else "failed"
            step["result"] = getattr(result, "output", None)
            step["updated_at"] = time.time()

        project["plans"] = plan
        self.save_project(project_id, project)

        progress = self.evaluate_progress(project_id)

        reflection = self._reflect_project(project, plan, progress)
        self.project_memory.append_reflection(project_id, reflection)

        refined = None
        if reflection.get("requires_refinement"):
            refined = self.refine_project_plan(project_id, reflection)

        return {"progress": progress, "reflection": reflection, "refinement": refined}

    def _execute_step(self, step: Dict[str, Any]) -> Any:
        if hasattr(self.worker, "execute"):
            return self.worker.execute(step.get("action"))
        if hasattr(self.worker, "run"):
            return self.worker.run(step.get("action"))
        raise AttributeError("Worker must implement 'execute' or 'run'")

    def _reflect_project(self, project_data: Dict[str, Any], plan: Dict[str, Any], progress: Dict[str, Any]) -> Dict[str, Any]:
        if hasattr(self.reflection, "reflect_project"):
            return self.reflection.reflect_project(project_data=project_data, plan=plan, progress=progress)
        if hasattr(self.reflection, "reflect"):
            return self.reflection.reflect(progress, reflection_type="long-horizon", goal=None)
        return {"summary": "No reflection available", "requires_refinement": False}
