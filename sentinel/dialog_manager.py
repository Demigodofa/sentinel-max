"""Compatibility wrapper for the conversation dialog manager."""
from typing import Dict, Optional

from sentinel.memory.memory_manager import MemoryManager
from sentinel.world.model import WorldModel


class DialogManager:
    """Lightweight dialog manager that records turns and world context."""

    def __init__(self, memory: MemoryManager, world_model: WorldModel) -> None:
        self.memory = memory
        self.world_model = world_model

    def build_context(self, user_message: str) -> Dict[str, object]:
        domain = self.world_model.get_domain(user_message)
        resources = self.world_model.predict_required_resources(user_message)
        dependencies = self.world_model.predict_dependencies(user_message)
        capabilities = self.world_model.list_capabilities(domain.name)
        context = {
            "domain": domain.name,
            "capabilities": capabilities,
            "resources": [resource.name for resource in resources],
            "dependencies": {k: sorted(list(v)) for k, v in dependencies.get("requires", {}).items()},
        }
        self.memory.store_fact("dialog_context", key=None, value=context, metadata={"source": "dialog_manager"})
        return context

    def record_turn(self, user_message: str, response: str, context: Optional[Dict[str, object]] = None) -> None:
        payload = {
            "user_message": user_message,
            "response": response,
            "context": context or self.build_context(user_message),
        }
        self.memory.store_fact("dialog_turns", key=None, value=payload, metadata={"source": "dialog_manager"})

    # ------------------------------------------------------------------
    def prompt_execution_approval(self, description: str):
        payload = {"type": "execution_approval", "description": description}
        self.memory.store_fact("approvals", key=None, value=payload, metadata={"source": "dialog_manager"})
        return {
            "prompt": f"Approval requested: {description}",
            "tone": "concise",
        }

    def notify_execution_status(self, status: dict):
        message = {
            "type": "execution_status",
            "status": status,
            "summary": "Execution update",
        }
        self.memory.store_fact("execution_notifications", key=None, value=message, metadata={"source": "dialog_manager"})
        return message

    def show_research_summary(self, summary: dict):
        payload = {"type": "research_summary", "summary": summary}
        self.memory.store_fact("research.domain", key=None, value=payload, metadata={"source": "dialog_manager"})
        return payload

    def show_tool_semantics(self, semantics: dict):
        payload = {"type": "tool_semantics", "semantics": semantics}
        self.memory.store_fact("research.tools", key=None, value=payload, metadata={"source": "dialog_manager"})
        return payload
