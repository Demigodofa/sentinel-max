"""Configuration loader."""
from __future__ import annotations

import os
from typing import Any, Dict


def load_config() -> Dict[str, Any]:
    return {
        "environment": os.environ.get("SENTINEL_ENV", "development"),
    }
