"""Tkinter GUI bootstrap for Sentinel MAX."""
from __future__ import annotations

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover - optional dependency
    tk = None  # type: ignore
    ttk = None  # type: ignore

from sentinel.gui.theme import load_theme
from sentinel.gui.widgets.chat_panel import ChatPanel
from sentinel.gui.widgets.control_panel import ControlPanel
from sentinel.gui.widgets.graph_panel import GraphPanel
from sentinel.gui.widgets.input_panel import InputPanel
from sentinel.gui.widgets.insight_panel import InsightPanel
from sentinel.gui.widgets.log_panel import LogPanel
from sentinel.gui.widgets.plan_panel import PlanPanel
from sentinel.interface.gui_bridge import GUIBridge


class SentinelApp:
    """Main Tkinter application shell."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.theme = load_theme()
        self.root.title("Sentinel MAX")
        self.root.configure(background=self.theme["colors"]["bg"])
        self._build_layout()
        self.bridge = GUIBridge(
            on_chat=lambda user, agent: self.root.after(0, lambda: self.chat_panel.append_exchange(user, agent)),
            on_plan=lambda steps: self.root.after(0, lambda: self.plan_panel.update_plan(steps)),
            on_graph=lambda graph: self.root.after(0, lambda: self.graph_panel.render_graph(graph)),
            on_logs=lambda logs: self.root.after(0, lambda: self.log_panel.append_logs(logs)),
            on_insights=lambda data: self.root.after(0, lambda: self.insight_panel.update_insights(data)),
        )
        self.bridge.show_plan()
        self.bridge.show_logs()

    def _build_layout(self) -> None:
        colors = self.theme["colors"]
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        self.chat_panel = ChatPanel(self.root, theme=self.theme)
        self.chat_panel.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad"])

        self.plan_panel = PlanPanel(self.root, theme=self.theme)
        self.plan_panel.grid(row=1, column=0, sticky="nsew", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad"])

        self.graph_panel = GraphPanel(self.root, theme=self.theme)
        self.graph_panel.grid(row=1, column=1, sticky="nsew", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad"])

        self.log_panel = LogPanel(self.root, theme=self.theme)
        self.log_panel.grid(row=2, column=0, sticky="nsew", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad"])

        self.insight_panel = InsightPanel(self.root, theme=self.theme)
        self.insight_panel.grid(row=2, column=1, sticky="nsew", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad"])

        separator = ttk.Separator(self.root, orient="horizontal")
        separator.grid(row=3, column=0, columnspan=2, sticky="ew")

        self.input_panel = InputPanel(self.root, on_send=self._handle_send, theme=self.theme)
        self.input_panel.grid(row=4, column=0, columnspan=2, sticky="ew", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad"])

        self.control_panel = ControlPanel(
            self.root,
            on_simulation=lambda: self._handle_simulation(),
            on_execute=lambda: self._handle_execute(),
            on_show_plan=lambda: self.bridge.show_plan(),
            on_show_graph=lambda: self.bridge.show_graph(),
            on_show_logs=lambda: self.bridge.show_logs(),
            on_rollback=lambda: self.bridge.rollback_to_previous_version(),
            theme=self.theme,
        )
        self.control_panel.grid(row=5, column=0, columnspan=2, sticky="ew", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad"])

        self.root.configure(background=colors["bg"])

    def _handle_send(self, text: str) -> None:
        self.bridge.send_user_input(text)

    def _handle_simulation(self) -> None:
        pending = self.input_panel.current_text()
        if pending:
            self.bridge.run_simulation_only(pending)

    def _handle_execute(self) -> None:
        pending = self.input_panel.current_text()
        if pending:
            self.bridge.execute_in_sandbox(pending)

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
