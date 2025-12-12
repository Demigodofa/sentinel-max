import re
from enum import Enum


class Intent(str, Enum):
    CONVERSATION = "conversation"
    TASK = "task"
    AUTONOMY_TRIGGER = "autonomy_trigger"
    # (keep others if present)


AUTONOMY_KEYWORDS = {
    "run autonomously",
    "start autonomy",
    "execute autonomously",
    "autonomy mode",
    "proceed autonomously",
}

TASK_PREFIXES = (
    "build ",
    "create ",
    "implement ",
    "draft ",
    "design ",
    "develop ",
    "write ",
    "compose ",
    "plan ",
    "generate ",
    "run ",
)

WEB_TASK_PATTERNS = (
    r"\b(search the web|web search|google|look up|lookup|find online)\b",
    r"\b(go online|go on the internet|search online|find on the internet|browse online)\b",
    r"\b(online research|internet research)\b",
)

FILE_ACTION_HINTS = ("save", "write", "store", "record")
WEB_REFERENCES = ("online", "internet", "web")


def classify_intent(text: str) -> Intent:
    if not text or not text.strip():
        return Intent.CONVERSATION

    normalized = text.strip()
    lowered = normalized.lower()

    # Hard-detect web search / lookup requests as TASK so it doesn't get "noted".
    # Examples:
    #  - "search the web for X"
    #  - "google X"
    #  - "look up X"
    for pattern in WEB_TASK_PATTERNS:
        if re.search(pattern, lowered):
            return Intent.TASK

    # Detect file-save requests that imply tool usage even when phrased conversationally
    # (e.g., "go online and find X and save it").
    if any(hint in lowered for hint in FILE_ACTION_HINTS) and any(ref in lowered for ref in WEB_REFERENCES):
        return Intent.TASK

    if lowered.startswith("/auto") or any(keyword in lowered for keyword in AUTONOMY_KEYWORDS):
        return Intent.AUTONOMY_TRIGGER

    if lowered.startswith(TASK_PREFIXES):
        return Intent.TASK

    return Intent.CONVERSATION
