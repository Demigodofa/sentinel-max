from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Iterable

from sentinel.planning.task_graph import TaskGraph, TaskNode
from sentinel.gui.theme import load_theme


class GraphPanel(ttk.Frame):
    """Textual task graph visualizer."""

    def __init__(self, master: tk.Misc, theme: dict | None = None) -> None:
        self.theme = theme or load_theme()
        super().__init__(master, padding=self.theme["spacing"]["pad"], style="GraphPanel.TFrame")
        self._configure_styles()
        self._build_widgets()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        colors = self.theme["colors"]
        style.configure(
            "GraphPanel.TFrame",
            background=colors["panel_bg"],
            borderwidth=self.theme["border"]["width"],
            relief=self.theme["border"]["relief"],
        )

    def _build_widgets(self) -> None:
        colors = self.theme["colors"]
        fonts = self.theme["fonts"]
        self.text = tk.Text(
            self,
            wrap="word",
            background=colors["panel_bg"],
            foreground=colors["text"],
            insertbackground=colors["accent"],
            font=fonts["mono"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self.scrollbar.set, state="disabled")
        self.text.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def render_graph(self, graph: TaskGraph | None) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        if not graph:
            self.text.insert(tk.END, "No graph available\n")
        else:
            for node in self._iter_nodes(graph):
                requires = ", ".join(node.requires) if node.requires else "root"
                produces = ", ".join(node.produces) if node.produces else "none"
                line = f"{node.id} -> requires [{requires}] produces [{produces}] tool={node.tool}\n"
                self.text.insert(tk.END, line)
        self.text.see(tk.END)
        self.text.configure(state="disabled")

    def _iter_nodes(self, graph: TaskGraph) -> Iterable[TaskNode]:
        try:
            return list(graph)
        except Exception:
            return []
