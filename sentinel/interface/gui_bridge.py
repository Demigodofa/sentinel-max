"""GUI integration layer that routes events through the conversational pipeline."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional

from sentinel.controller import SentinelController
from sentinel.agent_core.base import PlanStep
from sentinel.planning.task_graph import TaskGraph, TaskNode

ChatCallback = Callable[[str, str], None]
PlanCallback = Callable[[List[PlanStep | TaskNode]], None]
GraphCallback = Callable[[object], None]
LogCallback = Callable[[List[str]], None]
InsightCallback = Callable[[Dict[str, object]], None]


class GUIBridge:
    """Thread-safe GUI bridge that exposes conversation-aware actions."""

    def __init__(
        self,
        controller: Optional[SentinelController] = None,
        *,
        on_chat: Optional[ChatCallback] = None,
        on_plan: Optional[PlanCallback] = None,
        on_graph: Optional[GraphCallback] = None,
        on_logs: Optional[LogCallback] = None,
        on_insights: Optional[InsightCallback] = None,
    ) -> None:
        self.controller = controller or SentinelController()
        self.on_chat = on_chat
        self.on_plan = on_plan
        self.on_graph = on_graph
        self.on_logs = on_logs
        self.on_insights = on_insights
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4)

    # ------------------------------------------------------------------
    # Public API used by GUI widgets
    # ------------------------------------------------------------------
    def send_user_input(self, text: str) -> None:
        if not text:
            return
        self._executor.submit(self._process_conversation, text)

    def run_simulation_only(self, text: str) -> None:
        if not text:
            return
        self._executor.submit(self._simulate_only, text)

    def execute_in_sandbox(self, text: str) -> None:
        self.send_user_input(text)

    def show_plan(self) -> None:
        self._executor.submit(self._emit_plan_update)

    def show_graph(self) -> None:
        self._executor.submit(self._emit_graph_update)

    def show_logs(self) -> None:
        self._executor.submit(self._emit_log_update)

    def rollback_to_previous_version(self) -> None:
        self._executor.submit(self._rollback_plan)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _process_conversation(self, text: str) -> None:
        with self._lock:
            result = self.controller.process_conversation(text)
        response = result.get("response", "")
        if self.on_chat:
            self.on_chat(text, response)
        self._emit_plan_update()
        self._emit_graph_update(result.get("task_graph"))
        self._emit_log_update()
        self._emit_insights()

    def _simulate_only(self, text: str) -> None:
        conversation = self.controller.conversation_controller
        normalized_goal = conversation.intent_engine.run(text)
        task_graph = conversation.nl_to_taskgraph.translate(normalized_goal)
        simulations = self.controller.simulation_sandbox.simulate_taskgraph(task_graph, conversation.world_model)
        self.controller.memory.store_fact(
            "simulations",
            key=f"simulation_only_{normalized_goal.type}",
            value={node: result.__dict__ for node, result in simulations.items()},
            metadata={"mode": "simulation_only"},
        )
        if self.on_graph:
            self.on_graph(task_graph)
        if self.on_insights:
            self.on_insights(
                {
                    "world_model": conversation.world_model.dependencies,
                    "simulation": {node: result.__dict__ for node, result in simulations.items()},
                    "benchmarks": {},
                    "multi_agent_logs": self._collect_multi_agent_logs(),
                }
            )

    def _emit_plan_update(self) -> None:
        if not self.on_plan:
            return
        records = self.controller.memory.recall_recent(limit=1, namespace="plans")
        steps: List[PlanStep | TaskNode] = []
        if records:
            payload = records[0].get("value", {})
            raw_nodes = payload.get("nodes") or payload.get("steps") or []
            for raw in raw_nodes:
                try:
                    if "tool" in raw:
                        steps.append(TaskNode(**raw))
                    else:
                        steps.append(PlanStep(**raw))
                except Exception:
                    continue
        self.on_plan(steps)

    def _emit_graph_update(self, graph: object | None = None) -> None:
        if not self.on_graph:
            return
        if graph is None:
            recent = self.controller.memory.latest("task_graphs")
            if recent:
                payload = recent.get("value", {})
                nodes = payload.get("nodes", [])
                try:
                    graph = TaskGraph(TaskNode(**node) for node in nodes)
                except Exception:
                    graph = None
        self.on_graph(graph)

    def _emit_log_update(self) -> None:
        if not self.on_logs:
            return
        lines = self._collect_logs(limit=120)
        self.on_logs(lines)

    def _emit_insights(self) -> None:
        if not self.on_insights:
            return
        insights = {
            "world_model": self._collect_world_model_state(),
            "simulation": self._collect_simulation_results(),
            "benchmarks": self._collect_benchmark_summary(),
            "multi_agent_logs": self._collect_multi_agent_logs(),
        }
        self.on_insights(insights)

    def _collect_logs(self, limit: int = 120) -> List[str]:
        records = self.controller.memory.recall_recent(limit=limit)
        lines: List[str] = []
        for record in reversed(records):
            namespace = record.get("namespace", "log")
            value = record.get("value")
            if isinstance(value, dict):
                content = value.get("text") or value.get("output") or str(value)
            else:
                content = str(value)
            lines.append(f"({namespace}) {content}")
        return lines

    def _collect_world_model_state(self) -> Dict[str, object]:
        return self.controller.world_model.dependencies

    def _collect_simulation_results(self) -> Dict[str, object]:
        records = self.controller.memory.recall_recent(limit=5, namespace="simulations")
        if not records:
            return {}
        latest = records[0].get("value", {})
        return latest if isinstance(latest, dict) else {"results": latest}

    def _collect_benchmark_summary(self) -> Dict[str, object]:
        records = self.controller.memory.recall_recent(limit=3, namespace="execution")
        summary: Dict[str, object] = {}
        for record in records:
            value = record.get("value")
            if isinstance(value, dict) and value.get("benchmark"):
                summary[record.get("key") or str(record.get("created_at"))] = value.get("benchmark")
        return summary

    def _collect_multi_agent_logs(self) -> List[str]:
        records = self.controller.memory.recall_recent(limit=5, namespace="plan_feedback")
        logs: List[str] = []
        for record in records:
            logs.append(str(record.get("value")))
        return logs

    def _rollback_plan(self) -> None:
        records = self.controller.memory.recall_recent(limit=2, namespace="task_graphs")
        if len(records) < 2 or not self.on_logs:
            return
        previous = records[1]
        self.controller.memory.store_fact("task_graphs", key=None, value=previous.get("value"), metadata={"action": "rollback"})
        self.on_logs(["Rolled back to previous task graph version."])

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
