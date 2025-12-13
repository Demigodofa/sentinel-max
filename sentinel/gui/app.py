"""Tkinter GUI bootstrap for Sentinel MAX."""
from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from sentinel.controller import SentinelController
from sentinel.gui.clipboard import install as install_clipboard
from sentinel.gui.controller_bridge import ControllerBridge
from sentinel.gui.theme import load_theme
from sentinel.gui.widgets.chat_log import ChatLog
from sentinel.gui.widgets.input_panel import InputPanel
from sentinel.gui.widgets.plan_panel import PlanPanel
from sentinel.gui.widgets.log_panel import LogPanel
from sentinel.gui.widgets.state_panel import StatePanel


def run_gui_app() -> None:
    theme = load_theme()
    root = tk.Tk()
    root.title("Sentinel MAX")

    # On Windows, force a reliable theme to avoid invisible entry text when ttk styles misbehave.
    style = ttk.Style(root)
    if sys.platform.startswith("win"):
        try:
            style.theme_use("clam")
        except Exception:
            pass

    root.configure(bg=theme["colors"]["app_bg"])
    root.minsize(760, 520)

    install_clipboard(root)

    SentinelApp(root, theme=theme, controller=SentinelController())
    root.mainloop()


class SentinelApp:
    def __init__(
        self,
        root: tk.Tk,
        *,
        theme: dict | None = None,
        controller: SentinelController | None = None,
        bridge_cls: type[ControllerBridge] = ControllerBridge,
        build_layout: bool = True,
    ):
        self.root = root
        self.theme = theme or load_theme()
        self.controller = controller or SentinelController()
        self.bridge = bridge_cls(
            controller=self.controller,
            on_plan_update=lambda steps: self._on_plan_update(steps),
            on_log_update=lambda logs: self._on_log_update(logs),
            on_agent_response=lambda text: self._on_agent_response(text),
            on_state_update=lambda state: self._on_state_update(state),
        )
        self.plan_panel: PlanPanel | None = None
        self.log_panel: LogPanel | None = None
        self.state_panel: StatePanel | None = None
        if build_layout:
            self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._shutdown)

    def _build_layout(self) -> None:
        c = self.theme["colors"]

        container = ttk.Frame(self.root, padding=self.theme["spacing"]["pad_small"])
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        main_area = ttk.Frame(container)
        main_area.grid(row=0, column=0, sticky="nsew")

        self.chat = ChatLog(main_area, theme=self.theme)
        self.chat.grid(row=0, column=0, sticky="nsew", padx=(0, self.theme["spacing"]["pad_small"]))

        side_panel = ttk.Frame(main_area)
        side_panel.grid(row=0, column=1, sticky="nsew")
        side_panel.grid_columnconfigure(0, weight=1)
        side_panel.grid_rowconfigure(0, weight=1)
        side_panel.grid_rowconfigure(1, weight=1)
        side_panel.grid_rowconfigure(2, weight=1)

        self.plan_panel = PlanPanel(side_panel, theme=self.theme)
        self.plan_panel.grid(row=0, column=0, sticky="nsew")

        self.state_panel = StatePanel(side_panel, theme=self.theme)
        self.state_panel.grid(row=1, column=0, sticky="nsew", pady=(self.theme["spacing"]["pad_small"], 0))

        self.log_panel = LogPanel(side_panel, theme=self.theme)
        self.log_panel.grid(row=2, column=0, sticky="nsew", pady=(self.theme["spacing"]["pad_small"], 0))

        main_area.columnconfigure(0, weight=2)
        main_area.columnconfigure(1, weight=1)
        main_area.rowconfigure(0, weight=1)

        self.input_panel = InputPanel(container, on_send=self._handle_send, theme=self.theme)
        self.input_panel.grid(row=1, column=0, sticky="ew", pady=(self.theme["spacing"]["pad_small"], 0))

        self.chat.append("meta", "Sentinel MAX GUI ready. Type a message below.")

    def _handle_send(self, text: str) -> None:
        # Show user message immediately (copyable transcript)
        self.chat.append("user", text)
        self.bridge.send_user_input(text)

    def _on_agent_response(self, message: str) -> None:
        self.root.after(0, lambda: self.chat.append("agent", str(message)))

    def _on_plan_update(self, steps) -> None:
        if not self.plan_panel:
            return
        self.root.after(0, lambda: self.plan_panel.update_plan(steps))

    def _on_log_update(self, logs) -> None:
        if not self.log_panel:
            return
        self.root.after(0, lambda: self.log_panel.append_logs(logs))

    def _on_state_update(self, state) -> None:
        if not self.state_panel:
            return
        self.root.after(0, lambda: self.state_panel.update_state(state))

    def _shutdown(self) -> None:
        try:
            self.bridge.shutdown()
        finally:
            self.root.destroy()
