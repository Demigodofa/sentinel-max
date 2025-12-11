from sentinel.policy.policy_engine import PolicyViolation
from sentinel.project.long_horizon_engine import LongHorizonProjectEngine
from sentinel.project.project_memory import ProjectMemory


def test_engine_registers_plan_and_tracks_progress(tmp_path):
    memory = ProjectMemory(storage_path=tmp_path)
    engine = LongHorizonProjectEngine(memory=memory)
    project = engine.create_project(
        name="Demo",
        description="Test project",
        goals=[{"id": "g1", "text": "Do work"}],
    )

    engine.register_plan(project["project_id"], [
        {"id": "g1", "action": "do work", "depends_on": []}
    ])

    engine.record_step_result(project["project_id"], "g1", "completed")
    report = engine.progress_report(project["project_id"])

    assert "100%" in report


def test_engine_rejects_cycles(tmp_path):
    memory = ProjectMemory(storage_path=tmp_path)
    engine = LongHorizonProjectEngine(memory=memory)
    project = engine.create_project(name="Cycle", description="Cycle test")

    steps = [
        {"id": "A", "action": "step A", "depends_on": ["B"]},
        {"id": "B", "action": "step B", "depends_on": ["A"]},
    ]

    try:
        engine.register_plan(project["project_id"], steps)
        assert False, "Plan with cycles should be blocked"
    except PolicyViolation:
        assert True
