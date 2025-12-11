"""Configuration for tool autonomy behaviors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class ToolAutonomyPolicy:
    autonomy_mode: Literal["ask", "review", "autonomous"]
    require_benchmark_improvement: bool = True
    require_simulation_success: bool = True
    require_policy_approval: bool = True
