import sentinel.main as entry
from sentinel.gui.app import GUIStartupError


def test_run_gui_falls_back_to_cli(monkeypatch, capsys):
    calls = {"cli": 0}

    def fake_run_gui_app():
        raise GUIStartupError("no display")

    def fake_run_cli():
        calls["cli"] += 1
        return 0

    monkeypatch.setattr(entry, "run_gui_app", fake_run_gui_app)
    monkeypatch.setattr(entry, "run_cli", fake_run_cli)

    rc = entry.run_gui()

    assert rc == 0
    assert calls["cli"] == 1
    out = capsys.readouterr().out
    assert "Falling back to CLI" in out
