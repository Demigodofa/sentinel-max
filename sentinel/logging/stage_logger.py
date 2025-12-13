"""Structured pipeline logging with correlation IDs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager

logger = get_logger(__name__)


@dataclass
class PipelineStageLogger:
    """Write structured stage events tied together by a correlation ID."""

    memory: MemoryManager
    correlation_id: str

    def log_ingest(self, message: str, **details: Any) -> None:
        self._log("ingest", message, details)

    def log_plan(self, message: str, **details: Any) -> None:
        self._log("plan", message, details)

    def log_policy(self, message: str, **details: Any) -> None:
        self._log("policy", message, details)

    def log_execute(self, message: str, **details: Any) -> None:
        self._log("execute", message, details)

    def log_reflect(self, message: str, **details: Any) -> None:
        self._log("reflect", message, details)

    def _log(self, stage: str, message: str, details: Dict[str, Any] | None = None) -> None:
        payload = {
            "stage": stage,
            "correlation_id": self.correlation_id,
            "message": message,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.memory.store_fact(
                "pipeline_events",
                key=None,
                value=payload,
                metadata={"stage": stage, "correlation_id": self.correlation_id},
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to persist pipeline event for %s: %s", stage, exc)

