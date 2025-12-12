from sentinel.gui.app import SentinelApp
from sentinel.gui.theme import load_theme


class FakeBridge:
    def __init__(self, controller=None, **callbacks):
        self.controller = controller
        self.callbacks = callbacks
        self.sent = []

    def send_user_input(self, text: str) -> None:
        self.sent.append(text)
        if self.callbacks.get("on_agent_response"):
            self.callbacks["on_agent_response"]("bridge reply")

    def shutdown(self) -> None:
        self.sent.append("shutdown")


class FakeRoot:
    def __init__(self) -> None:
        self.after_calls = []
        self.protocol_value = None
        self.destroyed = False

    def after(self, delay: int, func, *args):
        self.after_calls.append(delay)
        func(*args)

    def protocol(self, _, func):
        self.protocol_value = func

    def destroy(self):
        self.destroyed = True


class FakeChat:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def append(self, who: str, text: str) -> None:
        self.messages.append((who, text))


class FakePlan:
    def __init__(self) -> None:
        self.updated = None

    def update_plan(self, steps):
        self.updated = steps


class FakeLog:
    def __init__(self) -> None:
        self.lines = None

    def append_logs(self, lines):
        self.lines = lines


def test_gui_uses_controller_bridge():
    root = FakeRoot()
    app = SentinelApp(
        root,
        theme=load_theme(),
        controller="controller",
        bridge_cls=FakeBridge,
        build_layout=False,
    )
    app.chat = FakeChat()
    app.plan_panel = FakePlan()
    app.log_panel = FakeLog()

    app._on_plan_update(["step"])
    app._on_log_update(["log"])
    app._handle_send("hello bridge")

    assert app.bridge.sent == ["hello bridge"]
    assert ("agent", "bridge reply") in app.chat.messages
    assert app.plan_panel.updated == ["step"]
    assert app.log_panel.lines == ["log"]
