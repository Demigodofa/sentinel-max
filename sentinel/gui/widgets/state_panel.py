"""Panel for inspecting pipeline state across key namespaces."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, Iterable

from sentinel.gui.theme import load_theme


class StatePanel(ttk.Frame):
    """Compact view of recent plans, execution, reflections, and policy events."""

    def __init__(self, master: tk.Misc, theme: dict | None = None) -> None:
        self.theme = theme or load_theme()
        super().__init__(master, padding=self.theme["spacing"]["pad"], style="StatePanel.TFrame")
        self._configure_styles()
        self._build_widgets()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        colors = self.theme["colors"]
        style.configure(
            "StatePanel.TFrame",
            background=colors["panel_bg"],
            borderwidth=self.theme["border"]["width"],
            relief=self.theme["border"]["relief"],
        )
        style.configure(
            "StatePanel.Treeview",
            background=colors["panel_bg"],
            fieldbackground=colors["panel_bg"],
            foreground=colors["text"],
            rowheight=22,
        )
        style.configure(
            "StatePanel.Treeview.Heading",
            background=colors["panel_bg"],
            foreground=colors["text"],
        )

    def _build_widgets(self) -> None:
        self.tree = ttk.Treeview(
            self,
            columns=("namespace", "summary"),
            show="headings",
            style="StatePanel.Treeview",
        )
        self.tree.heading("namespace", text="Namespace")
        self.tree.heading("summary", text="Correlation :: Summary")
        self.tree.column("namespace", width=120, anchor="w")
        self.tree.column("summary", width=280, anchor="w")

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def update_state(self, state: Dict[str, Iterable[Dict]]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for namespace, records in sorted(state.items()):
            for record in records:
                meta = record.get("metadata", {}) or {}
                correlation_id = meta.get("correlation_id")
                value = record.get("value")
                if correlation_id is None and isinstance(value, dict):
                    correlation_id = value.get("correlation_id") or value.get("metadata", {}).get("correlation_id") if isinstance(value.get("metadata", {}), dict) else None
                summary = self._summarize_value(value)
                display = f"{correlation_id or 'n/a'} :: {summary}" if summary else correlation_id or "n/a"
                self.tree.insert("", tk.END, values=(namespace, display))

    def _summarize_value(self, value) -> str:
        if isinstance(value, dict):
            for key in ("message", "summary", "goal", "event"):
                if value.get(key):
                    return str(value[key])
            return str(value)
        return str(value) if value is not None else ""

