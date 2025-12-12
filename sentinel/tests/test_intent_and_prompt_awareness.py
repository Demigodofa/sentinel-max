from sentinel.conversation.intent import Intent, classify_intent
from sentinel.llm.client import DEFAULT_SYSTEM_PROMPT


def test_online_find_and_save_detected_as_task():
    text = "go online and find the latest ai paper and save it"

    assert classify_intent(text) == Intent.TASK


def test_default_system_prompt_mentions_tools():
    assert "web_search" in DEFAULT_SYSTEM_PROMPT
    assert "internet_extract" in DEFAULT_SYSTEM_PROMPT
    assert "fs_write" in DEFAULT_SYSTEM_PROMPT
