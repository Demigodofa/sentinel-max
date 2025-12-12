import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from sentinel.project.dependency_graph import ProjectDependencyGraph


def test_dependency_graph_validation_and_sorting():
    graph = ProjectDependencyGraph()
    steps = [
        {"id": "a", "depends_on": []},
        {"id": "b", "depends_on": ["a"]},
        {"id": "c", "depends_on": ["b"]},
    ]

    normalized = graph.normalize_steps(steps)
    depths = graph.compute_depths(normalized)

    assert depths == {"a": 0, "b": 1, "c": 2}
    assert graph.detect_cycles(normalized) == []
    assert graph.validate(normalized) == ([], [])
    assert graph.topological_sort(normalized) == ["a", "b", "c"]


def test_dependency_graph_cycle_and_unresolved_detection():
    graph = ProjectDependencyGraph()
    cyclic = {"x": ["y"], "y": ["x"]}

    with pytest.raises(ValueError):
        graph.compute_depths(cyclic)

    cycles, unresolved = graph.validate(cyclic)
    assert any({"x", "y"}.issubset(set(cycle)) for cycle in cycles)
    assert unresolved == []

    unresolved_graph = {"x": ["missing"]}
    assert graph.validate(unresolved_graph)[1] == ["missing"]
