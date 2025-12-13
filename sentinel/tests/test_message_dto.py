import pytest

from sentinel.conversation.message_dto import MessageDTO


def test_message_dto_round_trip_payload():
    dto = MessageDTO(
        text="hello",
        mode="gui",
        autonomy=True,
        tool_call={"name": "echo", "args": {"text": "hi"}},
        context_refs=["session-1", "memory-2"],
    )

    payload = dto.to_payload()

    assert payload["text"] == "hello"
    assert payload["mode"] == "gui"
    assert payload["autonomy"] is True
    assert payload["tool_call"] == {"name": "echo", "args": {"text": "hi"}}
    assert payload["context_refs"] == ["session-1", "memory-2"]


def test_coerce_from_mapping_applies_defaults():
    dto = MessageDTO.coerce({"text": "ping"})

    assert dto.mode == "cli"
    assert dto.text == "ping"
    assert dto.context_refs == []


def test_invalid_entries_raise_value_error():
    with pytest.raises(ValueError):
        MessageDTO(text="", mode="cli")
    with pytest.raises(ValueError):
        MessageDTO(text="hi", mode="unsupported")
    with pytest.raises(ValueError):
        MessageDTO(text="hi", mode="cli", context_refs=["", 3])
    with pytest.raises(ValueError):
        MessageDTO.validate_payload({"mode": "cli"})
