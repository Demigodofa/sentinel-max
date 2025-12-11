# sentinel/project/dependency_graph.py

from typing import Dict, List, Any, Set


class ProjectDependencyGraph:
    """
    Builds and validates dependency graphs for long-horizon plans.
    Detects:
        - cycles
        - unresolved dependencies
        - invalid references
    Supports:
        - topological ordering
        - multi-phase sequencing
    """

    def build(self, plan: Dict[str, Any]) -> Dict[str, List[str]]:
        graph = {}
        for step_id, step in plan.items():
            graph[step_id] = step.get("depends_on", [])
        return graph

    def detect_cycles(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        visited: Set[str] = set()
        stack: Set[str] = set()
        cycles = []

        def _dependencies(node: str) -> List[str]:
            deps = graph.get(node, [])
            if isinstance(deps, dict):
                return deps.get("depends_on", [])
            return deps

        def dfs(node: str, path: List[str]):
            if node in stack:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:])
                return
            if node in visited:
                return
            visited.add(node)
            stack.add(node)
            for dep in _dependencies(node):
                dfs(dep, path + [dep])
            stack.remove(node)

        for n in graph:
            dfs(n, [n])
        return cycles

    def find_unresolved(self, graph: Dict[str, List[str]]) -> List[str]:
        unresolved = []
        all_nodes = set(graph.keys())
        for node, deps in graph.items():
            dependencies = deps.get("depends_on", deps) if isinstance(deps, dict) else deps
            for d in dependencies:
                if d not in all_nodes:
                    unresolved.append(d)
        return unresolved

    def topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        visited: Set[str] = set()
        order: List[str] = []

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

        for n in graph:
            dfs(n)

        return order
