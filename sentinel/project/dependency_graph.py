"""Dependency tracking for long-horizon project plans."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Set, Tuple


class ProjectDependencyGraph:
    """Build and analyze dependencies between planned project steps."""

    def build(self, plan: Dict[str, Any]) -> Dict[str, List[str]]:
        """Build a normalized dependency graph from a plan dictionary."""
        graph: Dict[str, List[str]] = {}
        for step_id, step in plan.items():
            dependencies = step.get("depends_on", [])
            if isinstance(dependencies, dict):
                dependencies = dependencies.get("depends_on", [])
            graph[step_id] = list(dict.fromkeys(dependencies))
        return graph

    def normalize_steps(self, steps: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Normalize a list of step dictionaries into a dependency graph."""
        graph: Dict[str, List[str]] = {}
        for step in steps:
            step_id = step.get("id")
            if not step_id:
                raise ValueError("Every step must include an 'id'")
            if step_id in graph:
                raise ValueError(f"Duplicate step id detected: {step_id}")
            deps = step.get("depends_on", [])
            if isinstance(deps, dict):
                deps = deps.get("depends_on", [])
            if not isinstance(deps, list):
                raise ValueError(f"depends_on for {step_id} must be a list")
            graph[step_id] = list(dict.fromkeys(deps))
        return graph

    def compute_depths(self, graph: Dict[str, List[str]]) -> Dict[str, int]:
        """Compute dependency depths for each node."""
        depths: Dict[str, int] = {}
        visiting: Set[str] = set()

        def dfs(node: str) -> int:
            if node in depths:
                return depths[node]
            if node in visiting:
                raise ValueError(f"Cycle detected while computing depths: {node}")
            visiting.add(node)
            deps = graph.get(node, [])
            if isinstance(deps, dict):
                deps = deps.get("depends_on", [])
            depth = 0 if not deps else 1 + max(dfs(dep) for dep in deps)
            visiting.remove(node)
            depths[node] = depth
            return depth

        for node in graph:
            dfs(node)
        return depths

    def detect_cycles(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        visited: Set[str] = set()
        stack: Set[str] = set()
        cycles: List[List[str]] = []

        def dependencies(node: str) -> List[str]:
            deps = graph.get(node, [])
            if isinstance(deps, dict):
                return deps.get("depends_on", [])
            return deps

        def dfs(node: str, path: List[str]):
            if node in stack:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            stack.add(node)
            for dep in dependencies(node):
                dfs(dep, path + [dep])
            stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node, [node])
        return cycles

    def find_unresolved(self, graph: Dict[str, List[str]]) -> List[str]:
        nodes = set(graph.keys())
        unresolved: List[str] = []
        for deps in graph.values():
            dependencies = deps.get("depends_on", deps) if isinstance(deps, dict) else deps
            for dep in dependencies:
                if dep not in nodes and dep not in unresolved:
                    unresolved.append(dep)
        return unresolved

    def validate(self, graph: Dict[str, List[str]]) -> Tuple[List[List[str]], List[str]]:
        """Return detected cycles and unresolved references for the graph."""
        cycles = self.detect_cycles(graph)
        unresolved = self.find_unresolved(graph)
        return cycles, unresolved

    def topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        indegree: Dict[str, int] = defaultdict(int)
        adjacency: Dict[str, Set[str]] = defaultdict(set)

        for node, deps in graph.items():
            dependencies = deps.get("depends_on", deps) if isinstance(deps, dict) else deps
            for dep in dependencies:
                indegree[node] += 1
                adjacency[dep].add(node)
            if node not in indegree:
                indegree[node] = indegree[node]

        queue: deque[str] = deque(sorted([n for n, deg in indegree.items() if deg == 0]))
        ordered: List[str] = []

        while queue:
            current = queue.popleft()
            ordered.append(current)
            for neighbor in sorted(adjacency.get(current, set())):
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)

        remaining = [n for n, deg in indegree.items() if deg > 0 and n not in ordered]
        ordered.extend(sorted(remaining))
        return ordered
