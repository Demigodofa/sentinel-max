import logging
from queue import Queue

import pytest

# Selenium is required for module import; skip the suite entirely when missing to
# keep environments without browser drivers green.
pytest.importorskip("selenium", reason="selenium not installed; browser relay disabled")

from sentinel.watchers.browser_command_relay import ChatGPTBrowserRelay, BrowserRelayConfig


class _DummyElement:
    def __init__(self, text: str) -> None:
        self.text = text


class _DummyDriver:
    def __init__(self, elements):
        self.elements = elements
        self.visited_url = None

    def get(self, url: str) -> None:  # pragma: no cover - simple setter
        self.visited_url = url

    def find_elements(self, *_args, **_kwargs):
        return self.elements

    def find_element(self, *_args, **_kwargs):  # pragma: no cover - simple stub
        return True

    def quit(self):  # pragma: no cover - nothing to clean up
        return None


def test_run_logs_driver_creation_failure(caplog):
    queue: Queue[str] = Queue()
    relay = ChatGPTBrowserRelay(
        queue,
        driver_factory=lambda: (_ for _ in ()).throw(RuntimeError("missing driver")),
        logger=logging.getLogger("relay_test"),
    )

    with caplog.at_level(logging.ERROR):
        relay.run()

    assert "Failed to create Chrome driver" in caplog.text
    assert queue.empty()


def test_run_exits_when_chatgpt_tab_unreachable(caplog):
    queue: Queue[str] = Queue()

    class _BrokenDriver(_DummyDriver):
        def get(self, _url: str) -> None:  # pragma: no cover - deliberate failure
            raise RuntimeError("navigation failed")

    relay = ChatGPTBrowserRelay(
        queue,
        driver_factory=lambda: _BrokenDriver([]),
        logger=logging.getLogger("relay_test_unreachable"),
    )

    with caplog.at_level(logging.ERROR):
        relay.run()

    assert "Navigation to chatgpt_url failed" in caplog.text
    assert queue.empty()


def test_poll_once_extracts_new_commands():
    queue: Queue[str] = Queue()
    relay = ChatGPTBrowserRelay(queue, config=BrowserRelayConfig())

    relay._driver = _DummyDriver(
        [_DummyElement("noise"), _DummyElement("<START>cmd 1<STOP> other"), _DummyElement("<START>cmd 1<STOP>")]
    )

    relay._poll_once()

    # Only one unique command should be forwarded despite duplicate markers
    assert queue.get(timeout=1) == "cmd 1"
    assert queue.empty()


def test_forward_command_strips_and_forwards(caplog):
    queue: Queue[str] = Queue()
    relay = ChatGPTBrowserRelay(queue, config=BrowserRelayConfig())

    with caplog.at_level(logging.INFO):
        relay._forward_command("   cmd 2   ")

    assert queue.get(timeout=1) == "cmd 2"
    assert "Forwarding ChatGPT command into GUI: cmd 2" in caplog.text
