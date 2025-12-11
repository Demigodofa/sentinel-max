"""In-memory simulation sandbox for predicting tool and task behavior."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sentinel.logging.logger import get_logger
from sentinel.planning.task_graph import TaskGraph, TaskNode
from sentinel.tools.registry import ToolRegistry
from sentinel.research.effect_predictor import ToolEffectPredictorV2

logger = get_logger(__name__)


class VirtualFileSystem:
    """Lightweight in-memory file overlay used during simulations."""

    def __init__(self) -> None:
        self.files: Dict[str, str] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}

    def write(self, path: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Store file contents without touching disk."""

        self.files[path] = content
        merged = dict(self.metadata.get(path, {}))
        merged.update(metadata or {})
        merged.setdefault("last_action", "write")
        self.metadata[path] = merged

    def read(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(f"Virtual path not found: {path}")
        return self.files[path]

    def exists(self, path: str) -> bool:
        return path in self.files

    def list(self) -> List[str]:
        return list(self.files.keys())


class ToolEffectPredictor:
    """Deprecated shim for V1 predictor (kept for backward compatibility)."""

    def predict(self, tool: Any, args: Dict[str, Any], world_model: Any | None) -> Dict[str, Any]:
        v2 = ToolEffectPredictorV2()
        schema = getattr(tool, "schema", None)
        if schema:
            v2.update_model({tool.name: {"outputs": schema.output_schema, "preconditions": []}})
        return v2.predict(tool.name, args)


class BenchmarkFacade:
    """Synthetic performance estimator that avoids real execution."""

    def estimate_performance(self, tool: Any, args: Dict[str, Any]) -> Dict[str, Any]:
        input_size = sum(len(str(v)) for v in args.values())
        complexity = "O(n log n)" if input_size > 50 else "O(n)"
        relative_speed = max(1, min(10, 10 - int(input_size / 20)))
        notes = f"Estimated complexity {complexity} with relative speed {relative_speed} for args {list(args.keys())}"
        return {
            "complexity": complexity,
            "relative_speed": relative_speed,
            "notes": notes,
        }


@dataclass
class SimulationResult:
    success: bool
    predicted_outputs: Dict[str, Any]
    predicted_vfs_changes: Dict[str, str]
    benchmark: Dict[str, Any]
    warnings: List[str] = field(default_factory=list)


class SimulationSandbox:
    """Predictive sandbox with a virtual filesystem overlay."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        virtual_fs: Optional[VirtualFileSystem] = None,
        predictor: Optional[ToolEffectPredictorV2] = None,
        benchmark: Optional[BenchmarkFacade] = None,
        semantic_profiles: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.vfs = virtual_fs or VirtualFileSystem()
        self.predictor = predictor or ToolEffectPredictorV2(semantic_profiles)
        self.benchmark_facade = benchmark or BenchmarkFacade()
        self.semantic_profiles = semantic_profiles or {}

    def simulate_tool_call(self, tool_name: str, args: Dict[str, Any], world_model: Any | None) -> SimulationResult:
        if not self.tool_registry.has_tool(tool_name):
            warnings = [f"Tool '{tool_name}' is not registered"]
            return SimulationResult(
                success=False,
                predicted_outputs={},
                predicted_vfs_changes={},
                benchmark={},
                warnings=warnings,
            )

        tool = self.tool_registry.get(tool_name)
        predictions = self.predictor.predict(tool_name, args)
        schema = getattr(tool, "schema", None)
        missing_required: List[str] = []
        if schema:
            missing_required = [
                key for key, meta in schema.input_schema.items() if meta.get("required") and key not in args
            ]
            if missing_required:
                predictions.setdefault("warnings", []).append(
                    f"Missing required parameters: {', '.join(missing_required)}"
                )
        vfs_changes: Dict[str, str] = {}
        for path in predictions.get("vfs_writes", []):
            summary = f"Predicted write by {tool_name} using args {sorted(args.keys())}"
            self.vfs.write(path, summary, metadata={"tool": tool_name, "type": "predicted"})
            vfs_changes[path] = summary
        for side_effect in predictions.get("side_effects", []):
            vfs_changes.setdefault(f"side_effect://{tool_name}/{side_effect}", side_effect)

        benchmark = self.benchmark_facade.estimate_performance(tool, args)
        failure_risk = predictions.get("failure_likelihood", 0.0)
        success = failure_risk < 0.7 and not predictions.get("warnings")
        return SimulationResult(
            success=success,
            predicted_outputs=predictions.get("outputs", {}),
            predicted_vfs_changes=vfs_changes,
            benchmark={**benchmark, "failure_likelihood": failure_risk, "runtime": predictions.get("runtime")},
            warnings=predictions.get("warnings", []),
        )

    def simulate_taskgraph(self, taskgraph: TaskGraph, world_model: Any | None) -> Dict[str, SimulationResult]:
        results: Dict[str, SimulationResult] = {}
        produced: Dict[str, Any] = {}
        produced_by = {
            artifact: node.id for node in taskgraph for artifact in node.produces
        }
        indegree = {
            node.id: len([req for req in node.requires if req in produced_by])
            for node in taskgraph
        }
        ready = [node.id for node in taskgraph if indegree[node.id] == 0]

        while ready:
            node_id = ready.pop(0)
            node = taskgraph.get(node_id)
            args = self._resolve_args(node, produced)
            simulation = self.simulate_tool_call(node.tool, args, world_model) if node.tool else self._noop(node, args)
            results[node.id] = simulation
            self._store_outputs(node, simulation, produced)
            for neighbor in taskgraph:
                if any(req in node.produces for req in neighbor.requires):
                    indegree[neighbor.id] -= 1
                    if indegree[neighbor.id] == 0 and neighbor.id not in ready:
                        ready.append(neighbor.id)

        return results

    def _resolve_args(self, node: TaskNode, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        args = dict(node.args)
        for requirement in node.requires:
            if requirement in artifacts and requirement not in args:
                args[requirement] = artifacts[requirement]
        return args

    def _store_outputs(self, node: TaskNode, result: SimulationResult, artifacts: Dict[str, Any]) -> None:
        if not node.produces:
            return
        for produced in node.produces:
            if produced in result.predicted_outputs:
                artifacts[produced] = result.predicted_outputs[produced]
            else:
                artifacts[produced] = result.predicted_outputs or result.benchmark

    def _noop(self, node: TaskNode, args: Dict[str, Any]) -> SimulationResult:
        description = "Pass-through node" if not node.tool else f"Non-executable node {node.tool}"
        return SimulationResult(
            success=True,
            predicted_outputs={produced: args.get(produced, description) for produced in node.produces},
            predicted_vfs_changes={},
            benchmark={"complexity": "O(1)", "relative_speed": 10, "notes": "No-op node", "failure_likelihood": 0.0},
            warnings=[],
        )

    def set_semantic_profiles(self, semantic_profiles: Dict[str, Dict[str, Any]]) -> None:
        """Update predictor with semantic profiles from research pipelines."""

        self.semantic_profiles = semantic_profiles
        self.predictor.update_model(semantic_profiles)
