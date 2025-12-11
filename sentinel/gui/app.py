"""Tkinter GUI bootstrap for Sentinel MAX."""
from __future__ import annotations

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover - optional dependency
    tk = None  # type: ignore
    ttk = None  # type: ignore

from sentinel.gui.controller_bridge import ControllerBridge
from sentinel.gui.theme import load_theme
from sentinel.gui.widgets.input_panel import InputPanel
from sentinel.gui.widgets.log_panel import LogPanel
from sentinel.gui.widgets.plan_panel import PlanPanel


class SentinelApp:
    """Main Tkinter application shell."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.theme = load_theme()
        self.root.title("Sentinel MAX")
        self.root.configure(background=self.theme["colors"]["bg"])
        self._build_layout()
        self.bridge = ControllerBridge(
            on_plan_update=lambda steps: self.root.after(0, lambda: self.plan_panel.update_plan(steps)),
            on_log_update=lambda logs: self.root.after(0, lambda: self.log_panel.append_logs(logs)),
            on_agent_response=lambda text: self.root.after(0, lambda: self._append_agent_response(text)),
        )
        self.bridge.refresh_state()

    def _build_layout(self) -> None:
        colors = self.theme["colors"]
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(1, weight=0)

        self.plan_panel = PlanPanel(self.root, theme=self.theme)
        self.plan_panel.grid(row=0, column=0, sticky="nsew", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad"])

        self.log_panel = LogPanel(self.root, theme=self.theme)
        self.log_panel.grid(row=0, column=1, sticky="nsew", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad"])

        separator = ttk.Separator(self.root, orient="horizontal")
        separator.grid(row=1, column=0, columnspan=2, sticky="ew")

        self.input_panel = InputPanel(self.root, on_send=self._handle_send, theme=self.theme)
        self.input_panel.grid(row=2, column=0, columnspan=2, sticky="ew", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad"])

        self.root.configure(background=colors["bg"])

    def _handle_send(self, text: str) -> None:
        self.bridge.send_user_input(text)

    def _append_agent_response(self, text: str) -> None:
        self.log_panel.append_logs([f"Agent: {text}"])

    def shutdown(self) -> None:
        if hasattr(self, "bridge"):
            self.bridge.shutdown()


def run_gui_app() -> None:
    """Launch the Tkinter GUI application."""

    if tk is None:
        print("Tkinter is not available in this environment.")
        return

    root = tk.Tk()
    app = SentinelApp(root)

    def _on_close() -> None:
        app.shutdown()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()
