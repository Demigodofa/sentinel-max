from sentinel.tools.microservice_builder import MicroserviceBuilder


def test_microservice_builder_writes_files_and_lists(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTINEL_PROJECT_STORAGE", str(tmp_path))
    builder = MicroserviceBuilder()

    result = builder.execute(description="/ping - pong", service_name="svc", port=9001)

    service_dir = tmp_path / "svc"
    code_path = service_dir / "app.py"
    req_path = service_dir / "requirements.txt"

    assert code_path.exists()
    assert req_path.exists()
    assert "uvicorn" in req_path.read_text()
    assert str(code_path) == result["code_path"]
    assert str(req_path) == result["requirements_path"]
    assert "uvicorn" in result["run_command"]
    assert str(service_dir) in result["run_command"]

    services = builder.execute(action="list")
    assert any(s["service_name"] == "svc" for s in services.get("services", []))

    stopped = builder.execute(action="stop", service_name="svc")
    assert stopped["status"] == "stopped"

    logs = builder.execute(action="logs", service_name="svc", limit=10)
    assert logs["logs"]
