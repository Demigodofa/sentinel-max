from sentinel.dialog.dialog_manager import DialogManager


def test_dialog_reports_formatting():
    dialog = DialogManager()
    overview = dialog.show_project_overview(
        {
            "name": "demo",
            "description": "test project",
            "goals": [{"id": "g1", "text": "first", "status": "completed"}],
        }
    )
    issues = dialog.show_dependency_issues({"cycles": [], "unresolved": []})

    assert "📦 PROJECT" in overview
    assert "✔ No dependency issues." == issues
