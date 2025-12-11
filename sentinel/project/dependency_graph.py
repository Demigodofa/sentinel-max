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

        def dfs(node: str, path: List[str]):
            if node in stack:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:])
                return
            if node in visited:
                return
            visited.add(node)
            stack.add(node)
            for dep in graph.get(node, []):
                dfs(dep, path + [dep])
            stack.remove(node)

        for n in graph:
            dfs(n, [n])
        return cycles

    def find_unresolved(self, graph: Dict[str, List[str]]) -> List[str]:
        unresolved = []
        all_nodes = set(graph.keys())
        for node, deps in graph.items():
            for d in deps:
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
            for dep in graph.get(node, []):
                dfs(dep)
            order.append(node)

        for n in graph:
            dfs(n)

        return order
