"""Approval gating for real execution."""
from __future__ import annotations

from typing import Optional

from sentinel.dialog_manager import DialogManager


class ApprovalGate:
    """Manage user approval prompts for real executions."""

    def __init__(self, dialog_manager: DialogManager | None = None) -> None:
        self.dialog_manager = dialog_manager
        self.pending_request: Optional[str] = None
        self.approved: bool = False

    def request_approval(self, description: str) -> None:
        """Request approval for the described action."""

        self.pending_request = description
        if not self.approved:
            self.approved = False
        if self.dialog_manager:
            self.dialog_manager.prompt_execution_approval(description)

    def approve(self) -> None:
        """Mark the current request as approved."""

        self.approved = True
        self.pending_request = None

    def deny(self) -> None:
        """Deny the current request and clear it."""

        self.approved = False
        self.pending_request = None

    def is_approved(self) -> bool:
        """Return whether the most recent request has been approved."""

        return self.approved
