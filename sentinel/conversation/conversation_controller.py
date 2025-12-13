"""Unified conversational pipeline orchestrator."""
from __future__ import annotations

import json
import re
import time
from typing import Dict, Optional, TYPE_CHECKING, Iterable, Tuple

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
        # Autonomy guardrails (user-friendly defaults)
        self.auto_budget_turns: Optional[int] = 0
        self.auto_deadline_epoch: float = 0.0

    def handle_input(self, text: str) -> Dict[str, object]:
        logger.info("Conversation pipeline received: %s", text)
        session_context = self.dialog_manager.get_session_context()
        raw = text.strip()
        normalized_text = raw.lower()

        if self.auto_mode_enabled and self._auto_expired():
            self._disable_auto_mode()

        # ------------------------------------------------------------
        # 1) Slash commands ALWAYS win (do not send to intent engine)
        # ------------------------------------------------------------
        if normalized_text.startswith("/"):
            cmd_result = self._handle_slash_command(raw, session_context)
            if cmd_result is not None:
                return cmd_result

        if normalized_text.startswith("/tool"):
            return self._handle_direct_tool_call(text, session_context)

        if self.pending_plan and self._is_execution_confirmation(normalized_text):
            turns, ttl = self._parse_auto_budget(normalized_text)
            if turns is not None or ttl is not None:
                self._arm_auto_mode(turns=turns, ttl_seconds=ttl or 3600)
            return self._execute_pending_plan(text, session_context)

        if self.pending_plan and self._is_cancel(normalized_text):
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

        if self.pending_goal and self._is_execution_confirmation(normalized_text):
            turns, ttl = self._parse_auto_budget(normalized_text)
            if turns is not None or ttl is not None:
                self._arm_auto_mode(turns=turns, ttl_seconds=ttl or 3600)
            goal_to_execute = self.pending_goal
            self.pending_goal = None
            return self._execute_with_goal(text, goal_to_execute, session_context)

        if self.pending_goal and self._is_cancel(normalized_text):
            self.pending_goal = None
            response = self.dialog_manager.format_agent_response(
                "Okay — cancelled. Tell me what to change."
            )
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
            if self.auto_mode_enabled and not self._auto_expired():
                self._consume_auto_budget()
                return self._execute_pending_plan(text, session_context)
            response = self.dialog_manager.propose_plan(self.pending_goal_text)
            response = (
                f"{response}\n\n"
                "Reply **y** (or /run) to run, **n** to revise, or use **/auto** to run immediately."
            )
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
                response = (
                    f"{response}\n\n"
                    "Reply **y** (or /run) to run, **n** to revise, or use **/auto** to run immediately."
                )
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
            if self.auto_mode_enabled and not self._auto_expired():
                self.pending_goal = None
                self._consume_auto_budget()
                return self._execute_with_goal(text, tentative_goal, session_context)
            self.pending_goal = tentative_goal
            response = self.dialog_manager.propose_plan(tentative_goal.as_goal_statement())
            response = (
                f"{response}\n\n"
                "Reply **y** (or /run) to run, **n** to revise, or use **/auto** to run immediately."
            )
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

        # Autonomy trigger should only "execute" if there is a pending plan,
        # otherwise treat it as normal conversation to avoid random auto-runs.
        if intent == Intent.AUTONOMY_TRIGGER:
            if self.pending_goal:
                goal_to_execute = self.pending_goal
                self.pending_goal = None
                return self._execute_with_goal(text, goal_to_execute, session_context)
            if self.pending_plan:
                return self._execute_pending_plan(text, session_context)
            response = self.dialog_manager.respond_conversationally(text)
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
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

    def _auto_expired(self) -> bool:
        if not self.auto_mode_enabled:
            return True
        if self.auto_budget_turns is not None and self.auto_budget_turns <= 0:
            return True
        if self.auto_deadline_epoch and time.time() > self.auto_deadline_epoch:
            return True
        return False

    def _consume_auto_budget(self) -> None:
        if self.auto_budget_turns is not None:
            self.auto_budget_turns -= 1
        if self._auto_expired():
            self._disable_auto_mode()

    def _arm_auto_mode(self, turns: Optional[int] = 10, ttl_seconds: Optional[int] = 3600) -> None:
        self.auto_mode_enabled = True
        self.auto_budget_turns = turns
        self.auto_deadline_epoch = time.time() + ttl_seconds if ttl_seconds else 0.0

    def _disable_auto_mode(self) -> None:
        self.auto_mode_enabled = False
        self.auto_budget_turns = 0
        self.auto_deadline_epoch = 0.0

    def _handle_slash_command(
        self, raw: str, session_context: Dict[str, object]
    ) -> Optional[Dict[str, object]]:
        """
        Slash commands are UI/ops controls (not "tasks").
        Supported:
          /help
          /tools
          /auto            -> executes pending plan if present
          /auto on|off
          /auto <free text> -> one-shot: treat remainder as a task and execute immediately
          /cancel          -> drops pending plan
        """
        text = raw.strip()
        lower = text.lower()

        if lower in {"/help", "/?"}:
            msg = (
                "Commands:\n"
                "  /help               show this help\n"
                "  /tools              list registered tools\n"
                "  /auto               execute the last proposed plan\n"
                "  /auto on|off        toggle auto-execution mode\n"
                "  /auto <turns>       enable bounded autonomy for N turns (default 1h timer)\n"
                "  /auto <duration>    enable bounded autonomy for a duration (e.g., 30m, 1h)\n"

                "  /auto until done    run autonomously without turn/time limits (manual stop)\n"

                "  /auto <task>        one-shot: plan+execute <task>\n"
                "  /run                execute the last proposed plan\n"
            )
            response = self.dialog_manager.format_agent_response(msg)
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if lower == "/cancel":
            self.pending_goal = None
            self.pending_plan = None
            self.pending_goal_text = None
            response = self.dialog_manager.format_agent_response(
                "Cancelled. Tell me what you want to do next."
            )
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if lower == "/tools":
            reg = getattr(self.planner, "tool_registry", None)

            def _iter_tools() -> Iterable[object]:
                if reg is None:
                    return []
                if hasattr(reg, "list_tools"):
                    try:
                        tools = reg.list_tools()
                    except Exception:
                        tools = []
                    if isinstance(tools, dict):
                        return tools.values()
                    return tools
                tools_dict = getattr(reg, "_tools", None) or getattr(reg, "tools", None)
                if isinstance(tools_dict, dict):
                    return tools_dict.values()
                return []

            lines = []
            for tool in _iter_tools():
                name = getattr(tool, "name", "<unnamed>")
                desc = getattr(tool, "description", "")
                lines.append(f"- {name}: {desc}".rstrip(": "))

            response = self.dialog_manager.format_agent_response(
                "Available tools:\n" + ("\n".join(lines) if lines else "(none)")
            )
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if lower in {"/auto on", "/auto enable"}:
            self._arm_auto_mode()
            response = self.dialog_manager.format_agent_response(
                "Auto mode enabled (10 actions, 1 hour). I'll execute approved plans without prompting."
            )
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if lower in {"/auto off", "/auto disable"}:
            self._disable_auto_mode()
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

        # /auto <task text>  (one-shot execute or bounded autonomy)
        if lower.startswith("/auto "):
            remainder = text[len("/auto ") :].strip()
            turns, ttl = self._parse_auto_budget(remainder)

            if turns is None and ttl is None and remainder.lower() in {
                "until done",
                "until complete",
                "until finished",
                "no limit",
                "forever",
            }:
                self._arm_auto_mode(turns=None, ttl_seconds=None)
                response = self.dialog_manager.format_agent_response(
                    "Auto mode enabled until manually stopped. I'll keep running plans without timing out."
                )
                self.dialog_manager.record_turn(text, response, context=session_context)
                return {
                    "response": response,
                    "normalized_goal": None,
                    "task_graph": None,
                    "trace": None,
                    "dialog_context": session_context,
                }

            if turns is not None or ttl is not None:
                ttl_seconds = ttl or 3600
                self._arm_auto_mode(turns=turns, ttl_seconds=ttl_seconds)
                budget_label = f"{turns} turns" if turns is not None else "time-bound"
                deadline_label = f"{ttl_seconds} seconds"
                response = self.dialog_manager.format_agent_response(
                    f"Auto mode enabled ({budget_label}; stops after {deadline_label})."
                )
                self.dialog_manager.record_turn(text, response, context=session_context)
                return {
                    "response": response,
                    "normalized_goal": None,
                    "task_graph": None,
                    "trace": None,
                    "dialog_context": session_context,
                }
            if remainder and remainder not in {"on", "enable", "off", "disable"}:
                normalized_goal = self.intent_engine.run(remainder)
                self.pending_goal = None
                self.pending_plan = None
                self.pending_goal_text = None
                self._disable_auto_mode()
                return self._execute_with_goal(remainder, normalized_goal, session_context)

        if lower == "/auto":
            if self.pending_goal is not None:
                goal_to_execute = self.pending_goal
                self.pending_goal = None
                return self._execute_with_goal(text, goal_to_execute, session_context)
            if self.pending_plan:
                return self._execute_pending_plan(text, session_context)
            response = self.dialog_manager.format_agent_response(
                "No pending plan to run. Ask for a task first, or use `/auto <task>`."
            )
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        if lower in {"/run", "/execute"}:
            if self.pending_plan:
                return self._execute_pending_plan(text, session_context)
            if self.pending_goal is not None:
                goal_to_execute = self.pending_goal
                self.pending_goal = None
                return self._execute_with_goal(text, goal_to_execute, session_context)
            response = self.dialog_manager.format_agent_response("No pending plan to run.")
            self.dialog_manager.record_turn(text, response, context=session_context)
            return {
                "response": response,
                "normalized_goal": None,
                "task_graph": None,
                "trace": None,
                "dialog_context": session_context,
            }

        return None

    def _is_execution_confirmation(self, normalized_text: str) -> bool:
        direct = {
            "y",
            "yes",
            "run",
            "execute",
            "start",
            "go",
            "do it",
        }
        if normalized_text in direct:
            return True
        substrings = [
            "run it",
            "run the plan",
            "execute the plan",
            "continue",
            "keep going",
            "go ahead",
            "please proceed",
            "keep running",
            "run this",
        ]
        return any(trigger in normalized_text for trigger in substrings)

    def _is_cancel(self, normalized_text: str) -> bool:
        return normalized_text in {"n", "no", "cancel", "stop"}

    def _parse_auto_budget(self, text: str) -> Tuple[Optional[int], Optional[int]]:
        lowered = text.lower().strip()
        if not lowered:
            return (None, None)

        if lowered in {"until done", "until complete", "until finished", "no limit", "forever"}:
            return (None, None)

        match_hours = re.search(r"(\d+)\s*(h|hr|hrs|hour|hours)", lowered)
        if match_hours:
            return (None, int(match_hours.group(1)) * 3600)
        match_minutes = re.search(r"(\d+)\s*(m|min|mins|minute|minutes)", lowered)
        if match_minutes:
            return (None, int(match_minutes.group(1)) * 60)
        match_seconds = re.search(r"(\d+)\s*(s|sec|secs|second|seconds)", lowered)
        if match_seconds:
            return (None, int(match_seconds.group(1)))
        if lowered.isdigit():
            return (int(lowered), 3600)
        return (None, None)

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
        response = self._final_response(trace, normalized_goal, enriched_graph)
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

        # --- REAL execution (not simulation) ---
        try:
            # Prefer running through the real Sandbox if available
            sandbox = getattr(getattr(self.autonomy, "worker", None), "sandbox", None)

            if sandbox is not None:
                output = sandbox.execute(self.planner.tool_registry.call, name, **parsed_args)
            else:
                # Fallback (less safe): direct registry call
                output = self.planner.tool_registry.call(name, **parsed_args)

            response_text = f"Tool '{name}' executed successfully:\n{output}"
        except Exception as exc:
            response_text = f"Tool '{name}' failed: {exc}"
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
        # Also publish a simplified plan for the GUI plan panel
        steps = []
        for node in task_graph:
            steps.append(
                {
                    "id": getattr(node, "id", ""),
                    "title": getattr(node, "title", "")
                    or getattr(node, "action", "")
                    or getattr(node, "tool", ""),
                    "depends_on": getattr(node, "depends_on", []) or [],
                }
            )

        self.memory.store_fact(
            "plans",
            key=None,
            value={"goal": goal_text, "steps": steps},
            metadata={"domain": normalized_goal.domain},
        )
        trace = self.autonomy.run_graph(task_graph, goal_text)
        return trace

    def _final_response(
        self, trace: ExecutionTrace, normalized_goal: NormalizedGoal, task_graph
    ) -> str:
        if trace.failed_nodes:
            issues = "; ".join(res.error or "unknown failure" for res in trace.failed_nodes)
            base = f"Tasks executed with failures: {issues}."
        else:
            base = "Tasks executed successfully with constraints validated."

        suggestions: list[str] = []
        metadata = getattr(task_graph, "metadata", {}) if task_graph else {}
        if isinstance(metadata, dict):
            critic = metadata.get("critic_suggestions") or []
            if critic:
                suggestions.extend([f"Critic: {item}" for item in critic])
            optimizations = metadata.get("optimizations") or []
            if optimizations:
                suggestions.extend([f"Optimizer: {item}" for item in optimizations])
            tool_gap = metadata.get("tool_gap")
            if tool_gap:
                suggestions.append(f"Tool gap detected: {tool_gap}. I can auto-generate an agent/tool to cover it.")
            generated_tool = metadata.get("generated_tool") if isinstance(metadata.get("generated_tool"), dict) else None
            if generated_tool:
                suggestions.append(
                    f"Proposed new agent/tool '{generated_tool.get('name', 'candidate')}' to self-augment the registry."
                )
        if suggestions:
            self.memory.store_fact(
                "autonomy_suggestions",
                key=None,
                value={"goal": normalized_goal.as_goal_statement(), "suggestions": suggestions},
                metadata={"source": "conversation_controller"},
            )
            base = f"{base} Suggestions: {'; '.join(suggestions)}."
        if normalized_goal.preferences:
            base = f"{base} Persona: {', '.join(normalized_goal.preferences)}."
        return self.dialog_manager.format_agent_response(base)
