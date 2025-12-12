from sentinel.project.long_horizon_engine import LongHorizonProjectEngine
from sentinel.project.long_horizon_engine import LongHorizonProjectEngine
from sentinel.project.project_memory import ProjectMemory


def test_long_horizon_reports_progress(tmp_path):
    memory = ProjectMemory(storage_path=tmp_path)
    engine = LongHorizonProjectEngine(memory=memory)
    project = engine.create_project("demo", "desc", goals=[{"text": "g1", "status": "completed"}])

    progress = engine.progress_report(project["project_id"])

    assert "100%" in progress


def test_dependency_issue_reporting(tmp_path):
    memory = ProjectMemory(storage_path=tmp_path)
    engine = LongHorizonProjectEngine(memory=memory)
    project = engine.create_project("demo2", "desc", goals=[{"text": "g2"}])
    memory.record_dependencies(project["project_id"], {"s2": ["missing"]})

    report = engine.dependency_issues(project["project_id"])
    assert "Unresolved" in report
