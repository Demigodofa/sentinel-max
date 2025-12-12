from enum import Enum, auto


class Intent(Enum):
    CONVERSATION = auto()
    INFORMATION = auto()
    TASK_REQUEST = auto()
    AUTONOMY_TRIGGER = auto()


AUTONOMY_KEYWORDS = {
    "/auto",
    "run autonomously",
    "start autonomy",
    "execute autonomously",
    "go ahead",
    "do it",
}


def classify_intent(text: str) -> Intent:
    t = text.lower().strip()

    if any(k in t for k in AUTONOMY_KEYWORDS):
        return Intent.AUTONOMY_TRIGGER

    if t.startswith(("/", "run ", "build ", "create ", "implement ")):
        return Intent.TASK_REQUEST

    if "?" in t or len(t.split()) < 6:
        return Intent.CONVERSATION

    return Intent.INFORMATION
