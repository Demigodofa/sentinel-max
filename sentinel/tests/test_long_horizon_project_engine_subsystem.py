import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from sentinel.project.long_horizon_engine import LongHorizonProjectEngine
from sentinel.project.project_memory import ProjectMemory


def test_long_horizon_engine_lifecycle(tmp_path):
    memory = ProjectMemory(tmp_path)
    engine = LongHorizonProjectEngine(memory=memory)

    project = engine.create_project("name", "desc", goals=[{"id": "g1", "text": "do"}])
    plan = engine.register_plan(
        project["project_id"],
        [
            {"id": "s1", "depends_on": []},
            {"id": "s2", "depends_on": ["s1"]},
        ],
    )

    snapshot = engine.record_step_result(project["project_id"], "g1", "completed")
    assert snapshot["goals"]["g1"]["status"] == "completed"
    assert plan["metadata"]["max_depth"] == 1

    report = engine.progress_report(project["project_id"])
    assert "PROGRESS" in report
