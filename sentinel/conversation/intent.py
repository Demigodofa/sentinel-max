from enum import Enum, auto


class Intent(Enum):
    CONVERSATION = auto()
    TASK = auto()
    AUTONOMY_TRIGGER = auto()


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
    normalized = text.strip()
    lowered = normalized.lower()

    if lowered.startswith("/auto") or any(keyword in lowered for keyword in AUTONOMY_KEYWORDS):
        return Intent.AUTONOMY_TRIGGER

    if lowered.startswith(TASK_PREFIXES):
        return Intent.TASK

    return Intent.CONVERSATION
