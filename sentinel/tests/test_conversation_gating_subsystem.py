from unittest.mock import MagicMock

import pytest
from unittest.mock import MagicMock

from sentinel.agent_core.base import ExecutionTrace, Tool
from sentinel.conversation.conversation_controller import ConversationController
from sentinel.conversation.dialog_manager import DialogManager
from sentinel.conversation.message_dto import MessageDTO
from sentinel.conversation.intent_engine import NormalizedGoal
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import TaskGraph, TaskNode
from sentinel.tools.registry import ToolRegistry
from sentinel.tools.tool_schema import ToolSchema
from sentinel.world.model import WorldModel


class DummyTool(Tool):
    schema = ToolSchema(
        name="dummy_tool",
        version="1.0.0",
        description="Dummy tool for testing",
        input_schema={},
        output_schema={"result": "string"},
        permissions=["test"],
    )

    def __init__(self) -> None:
        super().__init__(name="dummy_tool", description="Dummy tool")

    def execute(self, **kwargs):  # pragma: no cover - simulation only
        return {"received": kwargs}


def build_controller(normalized_goal: NormalizedGoal, tool_registry: ToolRegistry | None = None):
    memory = MemoryManager()
    world_model = WorldModel(memory)
    dialog_manager = DialogManager(memory, world_model)

    intent_engine = MagicMock()
    intent_engine.run.return_value = normalized_goal

    nl_to_taskgraph = MagicMock()
    autonomy = MagicMock()
    planner = MagicMock()
    planner.tool_registry = tool_registry or ToolRegistry()

    multi_agent_engine = MagicMock()

    controller = ConversationController(
        dialog_manager=dialog_manager,
        intent_engine=intent_engine,
        nl_to_taskgraph=nl_to_taskgraph,
        autonomy=autonomy,
        planner=planner,
        memory=memory,
        world_model=world_model,
        simulation_sandbox=None,
        multi_agent_engine=multi_agent_engine,
    )

    return controller, intent_engine, nl_to_taskgraph, autonomy, multi_agent_engine


@pytest.fixture
def normalized_goal():
    return NormalizedGoal(
        type="general_goal",
        domain="research",
        parameters={},
        constraints=[],
        preferences=[],
        context={},
        source_intent=None,
        ambiguities=[],
        raw_text="search the web",
    )


def test_envelope_logged_to_memory(normalized_goal):
    controller, *_ = build_controller(normalized_goal)

    controller.handle_input(
        MessageDTO(text="hello", mode="test", context_refs=["ctx-1"])
    )

    stored = controller.memory.query("goals")
    assert stored
    assert stored[0]["value"]["text"] == "hello"
    assert stored[0]["metadata"]["mode"] == "test"
    assert stored[0]["metadata"]["context_refs"] == ["ctx-1"]


def test_tools_command_returns_registered_tools(normalized_goal):
    registry = ToolRegistry()
    registry.register(DummyTool())
    controller, *_ = build_controller(normalized_goal, tool_registry=registry)

    result = controller.handle_input(MessageDTO(text="/tools", mode="test"))

    assert "- dummy_tool" in result["response"]


def test_task_request_prompts_for_execution(normalized_goal):
    controller, intent_engine, nl_to_taskgraph, autonomy, multi_agent_engine = build_controller(normalized_goal)

    result = controller.handle_input(MessageDTO(text="search the web for ai news", mode="test"))

    intent_engine.run.assert_called_once()
    nl_to_taskgraph.translate.assert_not_called()
    autonomy.run_graph.assert_not_called()
    multi_agent_engine.coordinate.assert_not_called()
    assert controller.pending_plan is not None
    assert "Execute? (y/n)" in result["response"]


def test_pending_plan_executes_on_yes(normalized_goal):
    controller, intent_engine, nl_to_taskgraph, autonomy, multi_agent_engine = build_controller(normalized_goal)

    graph = TaskGraph(nodes=[TaskNode(id="step", description="do work", tool=None)])
    nl_to_taskgraph.translate.return_value = graph
    multi_agent_engine.coordinate.return_value = graph
    autonomy.run_graph.return_value = ExecutionTrace()

    controller.handle_input(MessageDTO(text="search the web for ai news", mode="test"))
    result = controller.handle_input(MessageDTO(text="y", mode="test"))

    nl_to_taskgraph.translate.assert_called_once()
    multi_agent_engine.coordinate.assert_called_once()
    autonomy.run_graph.assert_called_once()
    assert controller.pending_plan is None
    assert "Tasks executed" in result["response"]
