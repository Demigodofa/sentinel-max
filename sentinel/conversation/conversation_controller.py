"""Unified conversational pipeline orchestrator."""
from __future__ import annotations

from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sentinel.agent_core.autonomy import AutonomyLoop
from sentinel.agent_core.base import ExecutionTrace
from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.planning.adaptive_planner import AdaptivePlanner
from sentinel.simulation.sandbox import SimulationSandbox
from sentinel.world.model import WorldModel
from sentinel.conversation.dialog_manager import DialogManager
from sentinel.conversation.intent import Intent, classify_intent
from sentinel.conversation.intent_engine import IntentEngine, NormalizedGoal
from sentinel.conversation.nl_to_taskgraph import NLToTaskGraph
from sentinel.agents.multi_agent_engine import MultiAgentEngine

logger = get_logger(__name__)


class ConversationController:
    """Run the full conversational stack from text to execution."""

    def __init__(
        self,
        dialog_manager: DialogManager,
        intent_engine: IntentEngine,
        nl_to_taskgraph: NLToTaskGraph,
        autonomy: "AutonomyLoop",
        planner: AdaptivePlanner,
        memory: MemoryManager,
        world_model: WorldModel,
        simulation_sandbox: Optional[SimulationSandbox] = None,
    ) -> None:
        self.dialog_manager = dialog_manager
        self.intent_engine = intent_engine
        self.nl_to_taskgraph = nl_to_taskgraph
        self.autonomy = autonomy
        self.planner = planner
        self.memory = memory
        self.world_model = world_model
        self.simulation_sandbox = simulation_sandbox or SimulationSandbox(self.planner.tool_registry)
        self.multi_agent_engine = MultiAgentEngine(
            planner=self.planner,
            registry=self.planner.tool_registry,
            sandbox=self.simulation_sandbox,
            memory=self.memory,
            policy_engine=self.planner.policy_engine,
            world_model=self.world_model,
            dialog_manager=self.dialog_manager,
        )

    def handle_input(self, text: str) -> Dict[str, object]:
        logger.info("Conversation pipeline received: %s", text)
        session_context = self.dialog_manager.get_session_context()

        intent = classify_intent(text)

        if intent == Intent.CONVERSATION:
            response = self.dialog_manager.respond_conversationally(text)
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if intent == Intent.INFORMATION:
            self.memory.store_fact("user_info", key=None, value=text, metadata={"source": "user"})
            response = self.dialog_manager.acknowledge_information(text)
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if intent == Intent.TASK_REQUEST:
            tentative_goal = self.intent_engine.run(text)
            clarifications = tentative_goal.ambiguities
            if clarifications:
                self.dialog_manager.register_questions(clarifications)
            response = self.dialog_manager.propose_plan(tentative_goal.as_goal_statement())
            self.dialog_manager.record_turn(
                text,
                response,
                context=session_context,
                normalized_goal=tentative_goal,
                questions=clarifications,
            )
            return {
                "response": response,
                "normalized_goal": tentative_goal,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if intent == Intent.AUTONOMY_TRIGGER:
            normalized_goal = self.intent_engine.run(text)
            self.dialog_manager.remember_goal(normalized_goal)
            clarifications = normalized_goal.ambiguities
            if clarifications:
                self.dialog_manager.register_questions(clarifications)
                response = self.dialog_manager.format_agent_response(
                    "I need a precise target before executing.", clarifications=clarifications
                )
                self.dialog_manager.record_turn(
                    text, response, context=session_context, normalized_goal=normalized_goal, questions=clarifications
                )
                return {
                    "response": response,
                    "normalized_goal": normalized_goal,
                    "task_graph": None,
                    "trace": None,
                    "dialog_context": session_context,
                }

            task_graph = self.nl_to_taskgraph.translate(normalized_goal)
            enriched_graph = self.multi_agent_engine.coordinate(task_graph)
            trace = self._execute_graph(normalized_goal, enriched_graph)
            response = self._final_response(trace, normalized_goal)
            self.dialog_manager.record_turn(
                text,
                response,
                context=session_context,
                normalized_goal=normalized_goal,
                task_graph=enriched_graph,
                questions=self.dialog_manager.flush_questions(),
            )
            return {
                "response": response,
                "normalized_goal": normalized_goal,
                "task_graph": enriched_graph,
                "trace": trace,
                "dialog_context": session_context,
            }

        response = self.dialog_manager.respond_conversationally(text)
        self.dialog_manager.record_turn(text, response, context=session_context)
        return {
            "response": response,
            "normalized_goal": None,
            "task_graph": None,
            "trace": None,
            "dialog_context": session_context,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _execute_graph(self, normalized_goal: NormalizedGoal, task_graph) -> ExecutionTrace:
        goal_text = normalized_goal.as_goal_statement()
        self.memory.store_fact(
            "task_graphs",
            key=None,
            value={
                "goal": goal_text,
                "metadata": task_graph.metadata,
                "nodes": [node.__dict__ for node in task_graph],
            },
            metadata={"domain": normalized_goal.domain},
        )
        trace = self.autonomy.run_graph(task_graph, goal_text)
        return trace

    def _final_response(self, trace: ExecutionTrace, normalized_goal: NormalizedGoal) -> str:
        if trace.failed_nodes:
            issues = "; ".join(res.error or "unknown failure" for res in trace.failed_nodes)
            base = f"Tasks executed with failures: {issues}."
        else:
            base = "Tasks executed successfully with constraints validated."
        if normalized_goal.preferences:
            base = f"{base} Persona: {', '.join(normalized_goal.preferences)}."
        return self.dialog_manager.format_agent_response(base)
