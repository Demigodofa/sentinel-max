from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from typing import Dict

from sentinel.gui.theme import load_theme


class InsightPanel(ttk.Frame):
    """Display world model, simulation, and benchmark summaries."""

    def __init__(self, master: tk.Misc, theme: dict | None = None) -> None:
        self.theme = theme or load_theme()
        super().__init__(master, padding=self.theme["spacing"]["pad"], style="InsightPanel.TFrame")
        self._configure_styles()
        self._build_widgets()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        colors = self.theme["colors"]
        style.configure(
            "InsightPanel.TFrame",
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
            font=fonts["body"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self.scrollbar.set, state="disabled")
        self.text.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def update_insights(self, insights: Dict[str, object]) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        for key in ["world_model", "simulation", "benchmarks", "multi_agent_logs"]:
            if key not in insights:
                continue
            self.text.insert(tk.END, f"{key.replace('_', ' ').title()}\n")
            self.text.insert(tk.END, json.dumps(insights[key], indent=2, default=str) + "\n\n")
        self.text.see(tk.END)
        self.text.configure(state="disabled")
