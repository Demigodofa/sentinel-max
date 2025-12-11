from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from sentinel.gui.theme import load_theme


class ControlPanel(ttk.Frame):
    """Action buttons for simulation, sandbox execution, and inspection."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_simulation: Callable[[], None],
        on_execute: Callable[[], None],
        on_show_plan: Callable[[], None],
        on_show_graph: Callable[[], None],
        on_show_logs: Callable[[], None],
        on_rollback: Callable[[], None],
        theme: dict | None = None,
    ) -> None:
        self.theme = theme or load_theme()
        super().__init__(master, padding=self.theme["spacing"]["pad"], style="ControlPanel.TFrame")
        self._configure_styles()
        self._build_buttons(on_simulation, on_execute, on_show_plan, on_show_graph, on_show_logs, on_rollback)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        colors = self.theme["colors"]
        style.configure(
            "ControlPanel.TFrame",
            background=colors["panel_bg"],
            borderwidth=self.theme["border"]["width"],
            relief=self.theme["border"]["relief"],
        )
        style.configure(
            "ControlPanel.TButton",
            background=colors["accent"],
            foreground=colors["panel_bg"],
            padding=self.theme["spacing"]["pad_small"],
        )

    def _build_buttons(
        self,
        on_simulation: Callable[[], None],
        on_execute: Callable[[], None],
        on_show_plan: Callable[[], None],
        on_show_graph: Callable[[], None],
        on_show_logs: Callable[[], None],
        on_rollback: Callable[[], None],
    ) -> None:
        labels = [
            ("Run Simulation Only", on_simulation),
            ("Execute in Sandbox", on_execute),
            ("Show Plan", on_show_plan),
            ("Show Graph", on_show_graph),
            ("Show Logs", on_show_logs),
            ("Rollback to Previous Version", on_rollback),
        ]
        for idx, (label, callback) in enumerate(labels):
            btn = ttk.Button(self, text=label, command=callback, style="ControlPanel.TButton")
            btn.grid(row=0, column=idx, padx=self.theme["spacing"]["pad_small"], pady=self.theme["spacing"]["pad_small"], sticky="ew")
        for idx in range(len(labels)):
            self.columnconfigure(idx, weight=1)
