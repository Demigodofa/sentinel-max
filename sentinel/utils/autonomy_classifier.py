"""
Moderate-sensitivity autonomy activation classifier.
"""
from __future__ import annotations

import re

TASK_PATTERNS = [
    r"\bfix\b",
    r"\bimprove\b",
    r"\boptimize\b",
    r"\brewrite\b",
    r"\brefactor\b",
    r"\bbuild\b",
    r"\bcreate\b",
    r"\bmake\b",
    r"\bdesign\b",
    r"\bgenerate\b",
    r"\bscript\b",
    r"\btool\b",
    r"\bproject\b",
    r"\bschema\b",
    r"\bcompare\b",
    r"\bimplement\b",
    r"\bdevelop\b",
]


def should_trigger_autonomy(text: str) -> bool:
    normalized = text.lower().strip()

    # Conversations not tasks
    if normalized in {"hi", "hello", "hey", "yo", "sup", "what's up"}:
        return False

    # Very short = always chat
    if len(normalized.split()) <= 2:
        return False

    # Detect task-like intent
    return any(re.search(pat, normalized) for pat in TASK_PATTERNS)
