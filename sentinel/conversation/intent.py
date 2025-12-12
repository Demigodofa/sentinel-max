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
    if re.search(r"\b(search the web|web search|google|look up|lookup|find online)\b", lowered):
        return Intent.TASK

    if lowered.startswith("/auto") or any(keyword in lowered for keyword in AUTONOMY_KEYWORDS):
        return Intent.AUTONOMY_TRIGGER

    if lowered.startswith(TASK_PREFIXES):
        return Intent.TASK

    return Intent.CONVERSATION
