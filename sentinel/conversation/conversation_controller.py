"""Unified conversational pipeline orchestrator."""
from __future__ import annotations

import json
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
        multi_agent_engine: Optional[MultiAgentEngine] = None,
    ) -> None:
        self.dialog_manager = dialog_manager
        self.intent_engine = intent_engine
        self.nl_to_taskgraph = nl_to_taskgraph
        self.autonomy = autonomy
        self.planner = planner
        self.memory = memory
        self.world_model = world_model
        self.simulation_sandbox = simulation_sandbox or SimulationSandbox(self.planner.tool_registry)
        self.multi_agent_engine = multi_agent_engine or MultiAgentEngine(
            planner=self.planner,
            registry=self.planner.tool_registry,
            sandbox=self.simulation_sandbox,
            memory=self.memory,
            policy_engine=self.planner.policy_engine,
            world_model=self.world_model,
            dialog_manager=self.dialog_manager,
        )
        self.auto_mode_enabled: bool = False
        self.pending_goal: Optional[NormalizedGoal] = None
        self.pending_plan: Optional[dict] = None
        self.pending_goal_text: Optional[str] = None

    def handle_input(self, text: str) -> Dict[str, object]:
        logger.info("Conversation pipeline received: %s", text)
        session_context = self.dialog_manager.get_session_context()
        normalized_text = text.strip().lower()

        if normalized_text in {"/auto on", "/auto enable"}:
            self.auto_mode_enabled = True
            response = self.dialog_manager.format_agent_response(
                "Auto mode enabled. I'll execute approved plans without prompting."
            )
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if normalized_text in {"/auto off", "/auto disable"}:
            self.auto_mode_enabled = False
            self.pending_goal = None
            self.pending_plan = None
            self.pending_goal_text = None
            response = self.dialog_manager.format_agent_response(
                "Auto mode disabled. I'll ask before executing plans."
            )
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if normalized_text == "/tools":
            tool_names = sorted(self.planner.tool_registry.list_tools())
            if not tool_names:
                tool_list = "No tools registered."
            else:
                tool_list = "\n".join(f"- {name}" for name in tool_names)
            response = self.dialog_manager.format_agent_response(tool_list)
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if normalized_text.startswith("/tool"):
            return self._handle_direct_tool_call(text, session_context)

        if normalized_text == "/auto" and self.pending_plan:
            return self._execute_pending_plan(text, session_context)

        if self.pending_plan and normalized_text in {"y", "yes", "run", "execute"}:
            return self._execute_pending_plan(text, session_context)

        if self.pending_plan and normalized_text in {"n", "no", "cancel"}:
            self.pending_plan = None
            self.pending_goal = None
            self.pending_goal_text = None
            response = self.dialog_manager.format_agent_response("Okay, canceled the pending plan.")
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if self._looks_like_task(normalized_text):
            normalized_goal = self.intent_engine.run(text)
            self.pending_goal = normalized_goal
            self.pending_goal_text = normalized_goal.as_goal_statement()
            self.pending_plan = {"normalized_goal": normalized_goal}
            if self.auto_mode_enabled:
                return self._execute_pending_plan(text, session_context)
            response = self.dialog_manager.propose_plan(self.pending_goal_text)
            self.dialog_manager.record_turn(
                text,
                response,
                context=session_context,
                normalized_goal=normalized_goal,
            )
            return {
                "response": response,
                "normalized_goal": normalized_goal,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

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

        if intent == Intent.TASK:
            tentative_goal = self.intent_engine.run(text)
            clarifications = tentative_goal.ambiguities
            if clarifications:
                self.dialog_manager.register_questions(clarifications)
                self.pending_goal = tentative_goal
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
            if self.auto_mode_enabled:
                self.pending_goal = None
                return self._execute_with_goal(text, tentative_goal, session_context)
            self.pending_goal = tentative_goal
            response = self.dialog_manager.propose_plan(tentative_goal.as_goal_statement())
            self.dialog_manager.record_turn(
                text,
                response,
                context=session_context,
                normalized_goal=tentative_goal,
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
            self.pending_goal = None
            return self._execute_with_goal(text, normalized_goal, session_context)

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
    def _execute_with_goal(
        self, user_input: str, normalized_goal: NormalizedGoal, session_context: Dict[str, object]
    ) -> Dict[str, object]:
        self.dialog_manager.remember_goal(normalized_goal)
        clarifications = normalized_goal.ambiguities
        if clarifications:
            self.dialog_manager.register_questions(clarifications)
            response = self.dialog_manager.format_agent_response(
                "I need a precise target before executing.", clarifications=clarifications
            )
            self.dialog_manager.record_turn(
                user_input,
                response,
                context=session_context,
                normalized_goal=normalized_goal,
                questions=clarifications,
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
            user_input,
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

    def _execute_pending_plan(self, user_input: str, session_context: Dict[str, object]) -> Dict[str, object]:
        plan = self.pending_plan or {}
        normalized_goal = plan.get("normalized_goal") or self.pending_goal
        self.pending_plan = None
        self.pending_goal = None
        self.pending_goal_text = None
        if not normalized_goal:
            response = self.dialog_manager.format_agent_response("No pending plan to execute.")
            self.dialog_manager.record_turn(user_input, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }
        return self._execute_with_goal(user_input, normalized_goal, session_context)

    def _handle_direct_tool_call(self, text: str, session_context: Dict[str, object]) -> Dict[str, object]:
        parts = text.strip().split(" ", 2)
        if len(parts) < 3:
            response = self.dialog_manager.format_agent_response("Usage: /tool <name> <json_args>")
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        name, raw_args = parts[1], parts[2]
        try:
            parsed_args = json.loads(raw_args)
            if not isinstance(parsed_args, dict):
                raise ValueError("Tool arguments must be a JSON object")
        except Exception as exc:  # pragma: no cover - defensive parsing
            response = self.dialog_manager.format_agent_response(f"Invalid tool arguments: {exc}")
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if not self.planner.tool_registry.has_tool(name):
            response = self.dialog_manager.format_agent_response(f"Tool '{name}' is not registered.")
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        simulation = self.simulation_sandbox.simulate_tool_call(name, parsed_args, self.world_model)
        if simulation.success:
            outputs = simulation.predicted_outputs or simulation.benchmark
            response_text = f"Tool '{name}' executed successfully: {outputs}"
        else:
            warnings = simulation.warnings or ["Unknown error"]
            response_text = f"Tool '{name}' failed: {'; '.join(warnings)}"
        response = self.dialog_manager.format_agent_response(response_text)
        self.dialog_manager.record_turn(text, response, context=session_context)
        return {
            "response": response,
            "normalized_goal": None,
            "task_graph": None,
            "trace": None,
            "dialog_context": session_context,
        }

    def _looks_like_task(self, normalized_text: str) -> bool:
        task_verbs = ("search", "browse", "create", "build", "write", "fix", "debug", "run")
        return normalized_text.startswith(task_verbs) or "web" in normalized_text or "internet" in normalized_text

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
