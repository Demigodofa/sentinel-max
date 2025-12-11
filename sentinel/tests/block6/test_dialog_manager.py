from sentinel.dialog.dialog_manager import DialogManager


def test_show_project_overview():
    dialog_manager = DialogManager()
    output = dialog_manager.show_project_overview({
        "name": "Test",
        "description": "Demo project",
        "goals": [{"id": "g1", "text": "Do X"}],
    })
    assert "Test" in output
    assert "Do X" in output
