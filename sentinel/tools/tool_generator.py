"""Generate simple tools dynamically."""
from __future__ import annotations

from typing import Callable


def generate_echo_tool(prefix: str = "") -> Callable[[str], str]:
    def tool(message: str) -> str:
        return f"{prefix}{message}"

    return tool
