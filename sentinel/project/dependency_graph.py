"""Dependency tracking for long-horizon project plans."""
from __future__ import annotations


from typing import Dict, List, Any, Set, Tuple
=======
from collections import defaultdict, deque
from typing import Any, Dict, List, Set


class ProjectDependencyGraph:
    """Build and analyze dependencies between planned project steps."""

    def build(self, plan: Dict[str, Any]) -> Dict[str, List[str]]:

        """Build a normalized dependency graph from a plan dictionary."""
        graph: Dict[str, List[str]] = {}
        for step_id, step in plan.items():
            dependencies = step.get("depends_on", [])
            if isinstance(dependencies, dict):
                dependencies = dependencies.get("depends_on", [])
            graph[step_id] = list(dependencies)
=======
        graph: Dict[str, List[str]] = {}
        for step_id, step in plan.items():
            deps = step.get("depends_on") or []
            graph[step_id] = list(dict.fromkeys(deps))
        return graph

    def normalize_steps(self, steps: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Normalize a list of step dictionaries into a dependency graph."""
        graph: Dict[str, List[str]] = {}
        for step in steps:
            step_id = step.get("id")
            if not step_id:
                raise ValueError("Every step must include an 'id'")
            deps = step.get("depends_on", [])
            if isinstance(deps, dict):
                deps = deps.get("depends_on", [])
            if not isinstance(deps, list):
                raise ValueError(f"depends_on for {step_id} must be a list")
            graph[step_id] = deps
        return graph

    def compute_depths(self, graph: Dict[str, List[str]]) -> Dict[str, int]:
        """
        Compute dependency depths for each node.
        Depth of a root node is 0; a node depending on a root is 1, etc.
        """
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
            if not deps:
                depth = 0
            else:
                depth = 1 + max(dfs(dep) for dep in deps)
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

        def _dependencies(node: str) -> List[str]:
            deps = graph.get(node, [])
            if isinstance(deps, dict):
                return deps.get("depends_on", [])
            return deps

        def _dependencies(node: str) -> List[str]:
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
            for dep in _dependencies(node):
                dfs(dep, path + [dep])
            stack.remove(node)

        for node in graph:
            if node not in visited:
                visit(node, [node])
        return cycles

    def find_unresolved(self, graph: Dict[str, List[str]]) -> Dict[str, List[str]]:
        nodes = set(graph.keys())
        unresolved: Dict[str, List[str]] = {}
        for node, deps in graph.items():
            dependencies = deps.get("depends_on", deps) if isinstance(deps, dict) else deps
            for d in dependencies:
                if d not in all_nodes:
                    unresolved.append(d)
        return unresolved

    def validate(self, graph: Dict[str, List[str]]) -> Tuple[List[List[str]], List[str]]:
        """Return detected cycles and unresolved references for the graph."""
        cycles = self.detect_cycles(graph)
        unresolved = self.find_unresolved(graph)
        return cycles, unresolved

    def topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        indegree: Dict[str, int] = defaultdict(int)
        adjacency: Dict[str, Set[str]] = defaultdict(set)

        def dfs(node: str):
            if node in visited:
                return
            visited.add(node)
            dependencies = graph.get(node, [])
            if isinstance(dependencies, dict):
                dependencies = dependencies.get("depends_on", [])
            for dep in dependencies:
                dfs(dep)
            order.append(node)

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
