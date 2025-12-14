from sentinel.controller import SentinelController


class _DummyRegistry:
    def __init__(self) -> None:
        self.calls = []

    def has_tool(self, name: str) -> bool:
        return name == "echo"

    def call(self, name: str, **kwargs):
        self.calls.append(kwargs)
        return kwargs

    def list_tools(self):  # pragma: no cover - compatibility path
        return {"echo": object()}


class _DummySandbox:
    def execute(self, func, tool_name: str, **args):
        return func(tool_name, **args)


def test_tool_command_runs_multiple_lines():
    controller = object.__new__(SentinelController)
    controller.tool_registry = _DummyRegistry()
    controller.sandbox = _DummySandbox()

    message = '/tool echo {"a": 1}\n/tool echo {"b": 2}'
    response = controller._handle_cli_command(message)

    assert response.splitlines() == ["{'a': 1}", "{'b': 2}"]
