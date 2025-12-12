from __future__ import annotations

import os
from pathlib import Path


def get_sandbox_root() -> Path:
    """
    Hard-root for ALL file operations.
    Must be an absolute path.
    """
    raw = os.getenv("SENTINEL_SANDBOX_ROOT", r"F:\\Sandbox")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        # force absolute to avoid surprises
        root = root.resolve()
    return root


def ensure_sandbox_root_exists() -> Path:
    root = get_sandbox_root()
    root.mkdir(parents=True, exist_ok=True)
    return root
