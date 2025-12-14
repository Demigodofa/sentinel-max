from types import SimpleNamespace
from unittest.mock import MagicMock

from sentinel.conversation.conversation_controller import ConversationController
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_schema import ToolSchema
from sentinel.agent_core.base import Tool


class StubTool(Tool):
    def __init__(self, name: str) -> None:
        super().__init__(name, "stub", deterministic=True)
        self.schema = ToolSchema(
            name=name,
            version="1.0.0",
            description="stub",
            input_schema={},
            output_schema={},
            permissions=["compute"],
            deterministic=True,
        )

    def execute(self, **_: object) -> str:  # pragma: no cover - not invoked in this test
        return "stub"


def test_dead_wood_uses_recent_history(tmp_path) -> None:
    registry = ToolRegistry()
    registry.register(StubTool("fs_list"))
    registry.register(StubTool("web_search"))

    planner = SimpleNamespace(tool_registry=registry, policy_engine=MagicMock())
    controller = ConversationController(
        dialog_manager=MagicMock(),
        intent_engine=MagicMock(),
        nl_to_taskgraph=MagicMock(),
        autonomy=MagicMock(),
        planner=planner,
        memory=MemoryManager(storage_dir=tmp_path),
        world_model=MagicMock(),
        simulation_sandbox=MagicMock(),
        multi_agent_engine=MagicMock(),
    )

    controller.memory.store_fact("execution", key="recent", value={"tool": "fs_list"})

    unused, usage, lookback = controller._dead_wood_report(lookback=10)

    assert "fs_list" not in unused
    assert "web_search" in unused
    assert usage["fs_list"] == 1
    assert usage["web_search"] == 0
    assert lookback == 10
