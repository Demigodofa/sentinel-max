"""Guard against accidentally committing merge conflict markers in critical files."""

from __future__ import annotations

from pathlib import Path

import pytest


TARGET_FILES = [
    Path("sentinel/dialog/dialog_manager.py"),
    Path("sentinel/policy/policy_engine.py"),
    Path("sentinel/project/dependency_graph.py"),
    Path("sentinel/project/project_memory.py"),
    Path("sentinel/sentinel_spec.md"),
]


@pytest.mark.parametrize("target", TARGET_FILES)
def test_no_merge_markers(target: Path) -> None:
    """Ensure merge conflict markers are not present in critical files."""

    content = target.read_text(encoding="utf-8")
    for marker in ("<<<<<<<", "=======", ">>>>>>>"):
        assert marker not in content, f"Merge marker '{marker}' found in {target}"
