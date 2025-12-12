import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from sentinel.project.project_memory import ProjectMemory


def test_project_memory_atomic_and_validation(tmp_path):
    memory = ProjectMemory(tmp_path)
    project = memory.create("demo", "desc")

    project_id = project["project_id"]
    memory.append_log(project_id, {"event": "test"})
    memory.append_reflection(project_id, {"note": "check"})
    memory.upsert_goals(project_id, [{"id": "g1", "text": "goal"}])
    memory.record_plan(project_id, "p1", {"steps": []})
    memory.record_dependencies(project_id, {"g1": []})
    memory.set_goal_status(project_id, "g1", "completed")

    snapshot = memory.snapshot(project_id)
    assert snapshot["goals"]["g1"]["status"] == "completed"
    assert snapshot["plans"]["p1"]["steps"] == []
    assert snapshot["dependencies"] == {"g1": []}
    assert snapshot["logs"] and snapshot["reflections"]

    corrupt_path = memory._project_path(project_id)
    corrupt_path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        memory.load(project_id)
