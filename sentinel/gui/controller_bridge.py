"""Bridge GUI events to the Sentinel controller with thread safety."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Iterable, List, Optional

from sentinel.agent_core.base import PlanStep
from sentinel.controller import SentinelController

PlanUpdateCallback = Callable[[List[PlanStep]], None]
LogUpdateCallback = Callable[[List[str]], None]
AgentResponseCallback = Callable[[str], None]


class ControllerBridge:
    """Thread-safe connector between GUI widgets and :class:`SentinelController`."""

    def __init__(
        self,
        controller: SentinelController | None = None,
        *,
        on_plan_update: Optional[PlanUpdateCallback] = None,
        on_log_update: Optional[LogUpdateCallback] = None,
        on_agent_response: Optional[AgentResponseCallback] = None,
    ) -> None:
        self.controller = controller or SentinelController()
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4)
        self.on_plan_update = on_plan_update
        self.on_log_update = on_log_update
        self.on_agent_response = on_agent_response
        self._seen_log_keys: set[str] = set()

    # ------------------------------------------------------------------
    # Public API used by GUI widgets
    # ------------------------------------------------------------------
    def send_user_input(self, text: str) -> None:
        """Process user input on a background thread."""

        if not text:
            return
        self._executor.submit(self._process_input, text)

    def refresh_plan(self) -> None:
        self._executor.submit(self._emit_plan_update)

    def refresh_logs(self) -> None:
        self._executor.submit(self._emit_log_update)

    def refresh_state(self) -> None:
        self.refresh_plan()
        self.refresh_logs()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _process_input(self, text: str) -> None:
        with self._lock:
            response = self.controller.process_input(text)
        if self.on_agent_response:
            self.on_agent_response(response)
        self._emit_plan_update()
        self._emit_log_update()

    def _emit_plan_update(self) -> None:
        if not self.on_plan_update:
            return
        steps = self._collect_plan_steps()
        self.on_plan_update(steps)

    def _emit_log_update(self) -> None:
        if not self.on_log_update:
            return
        logs = self._collect_logs(limit=100)
        self.on_log_update(logs)

    def _collect_plan_steps(self, limit: int = 1) -> List[PlanStep]:
        records = self.controller.memory.recall_recent(limit=limit, namespace="plans")
        if not records:
            return []
        plan_entry = records[0].get("value", {})
        steps_raw: Iterable[dict] = plan_entry.get("steps", []) if isinstance(plan_entry, dict) else []
        steps: List[PlanStep] = []
        for raw in steps_raw:
            try:
                steps.append(PlanStep(**raw))
            except Exception:
                continue
        return steps

    def _collect_logs(self, limit: int = 50) -> List[str]:
        records = self.controller.memory.recall_recent(limit=limit)
        lines: List[str] = []
        for record in reversed(records):
            record_key = record.get("key") or record.get("metadata", {}).get("id")
            if record_key and record_key in self._seen_log_keys:
                continue
            timestamp = record.get("updated_at") or record.get("created_at")
            try:
                ts = datetime.fromisoformat(timestamp).strftime("%H:%M:%S") if timestamp else "--:--:--"
            except Exception:
                ts = "--:--:--"
            namespace = record.get("namespace", "log")
            value = record.get("value")
            content = ""
            if isinstance(value, dict):
                content = value.get("text") or value.get("output") or str(value)
            else:
                content = str(value)
            lines.append(f"[{ts}] ({namespace}) {content}")
            if record_key:
                self._seen_log_keys.add(record_key)
        return lines

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
