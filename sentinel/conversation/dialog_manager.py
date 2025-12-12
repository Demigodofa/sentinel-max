"""Dialog manager that maintains conversational state and preferences."""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional

from sentinel.conversation.intent_engine import NormalizedGoal
from sentinel.llm.client import ChatMessage, LLMClient, DEFAULT_SYSTEM_PROMPT

from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.world.model import WorldModel

logger = get_logger(__name__)


class DialogManager:
    """Stateful dialog manager with memory-backed context."""

    def __init__(self, memory: MemoryManager, world_model: WorldModel, persona: str = "Professional + Concise") -> None:
        self.memory = memory
        self.world_model = world_model
        self.persona = persona
        self._llm = LLMClient()
        self.last_intent: Optional[str] = None
        self.active_goals: Deque[str] = deque(maxlen=6)
        self.partial_tasks: Deque[str] = deque(maxlen=6)
        self.pending_questions: Deque[str] = deque(maxlen=6)
        self.multi_turn_context: Deque[Dict[str, str]] = deque(maxlen=10)
        self.memory.store_fact("dialog_prefs", key="persona", value=persona, metadata={"source": "dialog_manager"})

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------
    def get_session_context(self) -> Dict[str, object]:
        recent_turns = list(self.multi_turn_context)
        preferences = [self.persona]
        context = {"recent_turns": recent_turns, "preferences": preferences, "active_goals": list(self.active_goals)}
        logger.debug("DialogManager session context: %s", context)
        return context

    def build_context(self, user_message: str, normalized_goal: Optional[object] = None) -> Dict[str, object]:
        domain = self.world_model.get_domain(user_message)
        capabilities = self.world_model.list_capabilities(domain.name)
        dependencies = self.world_model.predict_dependencies(user_message)
        context = {
            "domain": domain.name,
            "capabilities": capabilities,
            "dependencies": {k: sorted(list(v)) for k, v in dependencies.get("requires", {}).items()},
            "preferences": [self.persona],
        }
        if normalized_goal:
            context["goal"] = getattr(normalized_goal, "as_goal_statement", lambda: str(normalized_goal))()
        self.memory.store_fact("dialog_context", key=None, value=context, metadata={"source": "dialog_manager"})
        return context

    # ------------------------------------------------------------------
    # Turn handling
    # ------------------------------------------------------------------
    def record_turn(
        self,
        user_message: str,
        response: str,
        *,
        context: Optional[Dict[str, object]] = None,
        normalized_goal: Optional[object] = None,
        task_graph: Optional[object] = None,
        questions: Optional[List[str]] = None,
    ) -> None:
        payload = {
            "user_message": user_message,
            "response": response,
            "context": context or self.build_context(user_message, normalized_goal),
            "questions": questions or list(self.pending_questions),
            "task_graph": getattr(task_graph, "metadata", {}) if task_graph else None,
        }
        self.memory.store_fact("dialog_turns", key=None, value=payload, metadata={"source": "dialog_manager"})
        self._update_buffers(user_message, response)

    def _update_buffers(self, user_message: str, response: str) -> None:
        self.multi_turn_context.append({"user": user_message, "agent": response})
        if len(self.multi_turn_context) > self.multi_turn_context.maxlen:
            self.multi_turn_context.popleft()

    # ------------------------------------------------------------------
    # Goal + pronoun resolution
    # ------------------------------------------------------------------
    def remember_goal(self, normalized_goal: object) -> None:
        goal_text = getattr(normalized_goal, "as_goal_statement", lambda: str(normalized_goal))()
        self.active_goals.append(goal_text)
        self.memory.store_text(goal_text, namespace="goals", metadata={"type": "normalized"})

    def resolve_pronoun(self, token: str) -> Optional[str]:
        if not self.active_goals:
            return None
        last_goal = self.active_goals[-1]
        if token.lower() in {"it", "that", "this", "previous"}:
            return last_goal
        return None

    # ------------------------------------------------------------------
    # Professional response handling
    # ------------------------------------------------------------------
    def format_agent_response(self, base_text: str, clarifications: Optional[List[str]] = None) -> str:
        statements = [base_text.strip()]
        if clarifications:
            statements.append("Clarifications needed: " + "; ".join(clarifications))
            self.pending_questions.extend(clarifications)
        return " ".join(statements)

    def craft_frontstage_message(self, normalized_goal: NormalizedGoal, clarifications: Optional[List[str]] = None) -> str:
        goal_statement = normalized_goal.as_goal_statement()
        domain = normalized_goal.domain.replace("_", " ") if normalized_goal.domain else "general"
        preference_view = ", ".join(normalized_goal.preferences) if normalized_goal.preferences else self.persona
        header = f"I hear you're aiming for: {goal_statement}."
        readiness = (
            "I can brief the specialists and orchestrate the work once you give the go-ahead. "
            "Say 'yes' or use `/auto` to run the proposed plan when you're ready."
        )
        tone = f"I'll keep it {preference_view.lower()} while we plan within the {domain} space."
        return self.format_agent_response(" ".join([header, readiness, tone]), clarifications=clarifications)

    def flush_questions(self) -> List[str]:
        pending = list(self.pending_questions)
        self.pending_questions.clear()
        return pending

    def register_questions(self, questions: List[str]) -> None:
        for question in questions:
            if question not in self.pending_questions:
                self.pending_questions.append(question)

    def track_partial_task(self, description: str) -> None:
        self.partial_tasks.append(description)
        self.memory.store_fact(
            "dialog_partials", key=None, value={"description": description}, metadata={"source": "dialog_manager"}
        )

    # ------------------------------------------------------------------
    # Safe fallbacks
    # ------------------------------------------------------------------
    def respond_conversationally(self, text: str) -> str:
        reply = self._llm.chat(
            [ChatMessage("system", DEFAULT_SYSTEM_PROMPT), ChatMessage("user", text)],
            max_tokens=400,
        )
        if reply and reply.strip():
            return self.format_agent_response(reply.strip())
        return "I hear you. What would you like to work on?"

    def acknowledge_information(self, text: str) -> str:
        return "Got it — I've noted that."

    def propose_plan(self, goal) -> str:
        reply = self._llm.chat(
            [
                ChatMessage("system", DEFAULT_SYSTEM_PROMPT),
                ChatMessage(
                    "user",
                    "Write a short execution plan (3-6 steps) for this task. "
                    "Assume tools may exist for web_search, internet_extract, code_analyzer. "
                    "Be concise.\n\nTASK:\n" + str(goal),
                ),
            ],
            max_tokens=300,
        )
        if reply and reply.strip():
            return self.format_agent_response(reply.strip())
        return self.format_agent_response(
            "I can plan this:\n" f"{goal}\n\n" "Execute? (y/n) — or say `/auto` to run automatically."
        )
