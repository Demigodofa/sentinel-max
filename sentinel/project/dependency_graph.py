"""Dependency tracking for long-horizon project plans."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Set


class ProjectDependencyGraph:
    """Build and analyze dependencies between planned project steps."""

    def build(self, plan: Dict[str, Any]) -> Dict[str, List[str]]:
        graph: Dict[str, List[str]] = {}
        for step_id, step in plan.items():
            deps = step.get("depends_on") or []
            graph[step_id] = list(dict.fromkeys(deps))
        return graph

    def detect_cycles(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        visited: Set[str] = set()
        stack: Set[str] = set()
        cycles: List[List[str]] = []

        def visit(node: str, path: List[str]) -> None:
            if node in stack:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            stack.add(node)
            for dep in graph.get(node, []):
                visit(dep, path + [dep])
            stack.remove(node)

        for node in graph:
            if node not in visited:
                visit(node, [node])
        return cycles

    def find_unresolved(self, graph: Dict[str, List[str]]) -> Dict[str, List[str]]:
        nodes = set(graph.keys())
        unresolved: Dict[str, List[str]] = {}
        for node, deps in graph.items():
            missing = [dep for dep in deps if dep not in nodes]
            if missing:
                unresolved[node] = missing
        return unresolved

    def topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        indegree: Dict[str, int] = defaultdict(int)
        adjacency: Dict[str, Set[str]] = defaultdict(set)

        for node, deps in graph.items():
            indegree.setdefault(node, 0)
            for dep in deps:
                if dep in graph:
                    indegree[node] += 1
                    adjacency[dep].add(node)

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
