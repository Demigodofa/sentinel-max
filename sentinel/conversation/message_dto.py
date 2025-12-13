"""Schema-validated message envelope shared across interfaces."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional


@dataclass
class MessageDTO:
    """Normalized message envelope passed into the conversation stack."""

    text: str
    mode: str = "cli"
    autonomy: Optional[bool] = None
    tool_call: Optional[Dict[str, Any]] = None
    context_refs: list[str] = field(default_factory=list)

    ALLOWED_MODES = {"cli", "gui", "api", "test"}

    def __post_init__(self) -> None:
        self._validate_text()
        self._validate_mode()
        self._validate_autonomy()
        self._validate_tool_call()
        self._normalize_context_refs()

    def _validate_text(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("MessageDTO.text must be a non-empty string")

    def _validate_mode(self) -> None:
        if not isinstance(self.mode, str):
            raise ValueError("MessageDTO.mode must be a string")
        if self.mode not in self.ALLOWED_MODES:
            raise ValueError(f"Unsupported message mode '{self.mode}'")

    def _validate_autonomy(self) -> None:
        if self.autonomy is not None and not isinstance(self.autonomy, bool):
            raise ValueError("MessageDTO.autonomy must be a boolean when provided")

    def _validate_tool_call(self) -> None:
        if self.tool_call is None:
            return
        if not isinstance(self.tool_call, dict):
            raise ValueError("MessageDTO.tool_call must be a dictionary when provided")

    def _normalize_context_refs(self) -> None:
        refs: Iterable[Any] = self.context_refs or []
        normalized: list[str] = []
        for ref in refs:
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError("MessageDTO.context_refs entries must be non-empty strings")
            normalized.append(ref)
        self.context_refs = normalized

    def to_payload(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "mode": self.mode,
            "autonomy": self.autonomy,
            "tool_call": self.tool_call,
            "context_refs": list(self.context_refs),
        }

    @classmethod
    def coerce(cls, candidate: "MessageDTO | Mapping[str, Any] | str", default_mode: str = "cli") -> "MessageDTO":
        if isinstance(candidate, cls):
            return candidate
        if isinstance(candidate, Mapping):
            merged = {"mode": default_mode, **candidate}
            return cls(**merged)  # type: ignore[arg-type]
        if isinstance(candidate, str):
            return cls(text=candidate, mode=default_mode)
        raise TypeError("MessageDTO must be built from a MessageDTO, mapping, or string")

    @classmethod
    def validate_payload(cls, payload: Mapping[str, Any]) -> None:
        required_fields = {"text"}
        missing = required_fields - set(payload)
        if missing:
            raise ValueError(f"Missing required message fields: {sorted(missing)}")
        cls(**payload)  # noqa: B901 - validation only
