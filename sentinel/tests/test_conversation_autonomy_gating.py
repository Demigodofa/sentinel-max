from unittest.mock import MagicMock

import pytest

from sentinel.agent_core.base import ExecutionTrace
from sentinel.conversation.conversation_controller import ConversationController
from sentinel.conversation.dialog_manager import DialogManager
from sentinel.conversation.intent_engine import NormalizedGoal
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.task_graph import TaskGraph, TaskNode
from sentinel.tools.registry import ToolRegistry
from sentinel.world.model import WorldModel


def build_controller(normalized_goal: NormalizedGoal):
    memory = MemoryManager()
    world_model = WorldModel(memory)
    dialog_manager = DialogManager(memory, world_model)

    intent_engine = MagicMock()
    intent_engine.run.return_value = normalized_goal

    nl_to_taskgraph = MagicMock()
    autonomy = MagicMock()
    planner = MagicMock()
    planner.tool_registry = ToolRegistry()

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
        domain="coding",
        parameters={},
        constraints=[],
        preferences=[],
        context={},
        source_intent=None,
        ambiguities=[],
        raw_text="build a script",
    )


def test_greeting_stays_conversational(normalized_goal):
    controller, intent_engine, nl_to_taskgraph, autonomy, multi_agent_engine = build_controller(normalized_goal)

    result = controller.handle_input("hello")

    intent_engine.run.assert_not_called()
    nl_to_taskgraph.translate.assert_not_called()
    autonomy.run_graph.assert_not_called()
    multi_agent_engine.coordinate.assert_not_called()
    assert "I hear you" in result["response"]


def test_task_request_proposes_plan_only(normalized_goal):
    controller, intent_engine, nl_to_taskgraph, autonomy, multi_agent_engine = build_controller(normalized_goal)

    result = controller.handle_input("build a script to rename files")

    intent_engine.run.assert_called_once()
    nl_to_taskgraph.translate.assert_not_called()
    autonomy.run_graph.assert_not_called()
    multi_agent_engine.coordinate.assert_not_called()
    assert controller.pending_goal is normalized_goal
    assert "Execute? (y/n)" in result["response"]


def test_plan_executes_after_user_approval(normalized_goal):
    controller, intent_engine, nl_to_taskgraph, autonomy, multi_agent_engine = build_controller(normalized_goal)

    graph = TaskGraph(nodes=[TaskNode(id="step", description="do work", tool=None)])
    nl_to_taskgraph.translate.return_value = graph
    multi_agent_engine.coordinate.return_value = graph
    autonomy.run_graph.return_value = ExecutionTrace()

    controller.handle_input("build a script to rename files")
    result = controller.handle_input("y")

    nl_to_taskgraph.translate.assert_called_once()
    multi_agent_engine.coordinate.assert_called_once()
    autonomy.run_graph.assert_called_once()
    assert "Tasks executed" in result["response"]
    assert controller.pending_goal is None


def test_autonomy_trigger_executes(normalized_goal):
    controller, intent_engine, nl_to_taskgraph, autonomy, multi_agent_engine = build_controller(normalized_goal)

    graph = TaskGraph(nodes=[TaskNode(id="step", description="do work", tool=None)])
    nl_to_taskgraph.translate.return_value = graph
    multi_agent_engine.coordinate.return_value = graph
    autonomy.run_graph.return_value = ExecutionTrace()

    result = controller.handle_input("/auto build a script to rename files")

    intent_engine.run.assert_called_once()
    nl_to_taskgraph.translate.assert_called_once()
    multi_agent_engine.coordinate.assert_called_once()
    autonomy.run_graph.assert_called_once()
    assert "Tasks executed" in result["response"]


def test_auto_mode_runs_without_prompt(normalized_goal):
    controller, intent_engine, nl_to_taskgraph, autonomy, multi_agent_engine = build_controller(normalized_goal)

    graph = TaskGraph(nodes=[TaskNode(id="step", description="do work", tool=None)])
    nl_to_taskgraph.translate.return_value = graph
    multi_agent_engine.coordinate.return_value = graph
    autonomy.run_graph.return_value = ExecutionTrace()

    controller.handle_input("/auto on")
    result = controller.handle_input("build a script to rename files")

    assert controller.auto_mode_enabled is True
    intent_engine.run.assert_called_once()
    nl_to_taskgraph.translate.assert_called_once()
    multi_agent_engine.coordinate.assert_called_once()
    autonomy.run_graph.assert_called_once()
    assert "Tasks executed" in result["response"]
