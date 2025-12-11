"""Bridge GUI events to the Sentinel controller."""
from __future__ import annotations

from sentinel.controller import SentinelController


class ControllerBridge:
    def __init__(self, controller: SentinelController | None = None) -> None:
        self.controller = controller or SentinelController()

    def send(self, message: str) -> str:
        return self.controller.process_input(message)
