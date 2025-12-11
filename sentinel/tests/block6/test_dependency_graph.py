from sentinel.project.dependency_graph import ProjectDependencyGraph


def test_cycle_detection():
    graph_builder = ProjectDependencyGraph()
    graph = {
        "A": {"depends_on": ["B"]},
        "B": {"depends_on": ["A"]},
    }
    cycles = graph_builder.detect_cycles(graph)
    assert cycles != []
