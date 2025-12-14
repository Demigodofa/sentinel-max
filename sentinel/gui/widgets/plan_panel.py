"""Plan panel widget for displaying plan steps."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Iterable

from sentinel.agent_core.base import PlanStep
from sentinel.planning.task_graph import TaskNode
from sentinel.gui.theme import load_theme


class PlanPanel(ttk.Frame):
    """Scrollable panel showing the current plan."""

    def __init__(self, master: tk.Misc, theme: dict | None = None) -> None:
        self.theme = theme or load_theme()
        super().__init__(master, padding=self.theme["spacing"]["pad"], style="PlanPanel.TFrame")
        self._wraplength = 300
        self._wrappable_labels: list[ttk.Label] = []
        self._configure_styles()
        self._build_widgets()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        colors = self.theme["colors"]
        style.configure(
            "PlanPanel.TFrame",
            background=colors["panel_bg"],
            borderwidth=self.theme["border"]["width"],
            relief=self.theme["border"]["relief"],
        )
        style.configure(
            "PlanStep.TFrame",
            background=colors["panel_bg"],
        )
        style.configure(
            "PlanStepTitle.TLabel",
            background=colors["panel_bg"],
            foreground=colors["text"],
            font=(self.theme.get("fonts", {}).get("heading") or self.theme.get("fonts", {}).get("body") or ("Segoe UI", 11, "bold")),
        )
        style.configure(
            "PlanStepBody.TLabel",
            background=colors["panel_bg"],
            foreground=colors.get("muted_text", colors.get("muted", "#888888")),
            font=self.theme["fonts"]["body"],
            wraplength=self._wraplength,
            justify="left",
        )

    def _build_widgets(self) -> None:
        colors = self.theme["colors"]
        self.configure(style="PlanPanel.TFrame")
        self.canvas = tk.Canvas(self, background=colors["panel_bg"], highlightthickness=0, width=320)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style="PlanPanel.TFrame")

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self._inner_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind("<Configure>", self._handle_canvas_configure)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inner.columnconfigure(0, weight=1)

    def update_plan(self, steps: Iterable[PlanStep | TaskNode] | None) -> None:
        """Render plan steps or task nodes in the panel."""

        self._wrappable_labels.clear()
        for child in self.inner.winfo_children():
            child.destroy()

        if not steps:
            empty = ttk.Label(
                self.inner,
                text="No plan available",
                style="PlanStepBody.TLabel",
            )
            self._register_wrappable(empty)
            empty.pack(anchor="w", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad_small"])
            return

        for step in steps:
            frame = ttk.Frame(self.inner, style="PlanStep.TFrame")
            step_id = getattr(step, "step_id", None) or getattr(step, "id", "?")
            title = ttk.Label(
                frame,
                text=f"Step {step_id}: {step.description}",
                style="PlanStepTitle.TLabel",
            )
            self._register_wrappable(title)
            title.pack(anchor="w")

            details = []
            tool_name = getattr(step, "tool_name", None) or getattr(step, "tool", None)
            params = getattr(step, "params", None) or getattr(step, "args", None)
            expected_output = getattr(step, "expected_output", None)
            if tool_name:
                details.append(f"Tool: {tool_name}")
            if expected_output:
                details.append(f"Expected: {expected_output}")
            if params:
                details.append(f"Params: {params}")
            if details:
                body = ttk.Label(
                    frame,
                    text="\n".join(details),
                    style="PlanStepBody.TLabel",
                )
                self._register_wrappable(body)
                body.pack(anchor="w", pady=(self.theme["spacing"]["pad_small"], 0))

            frame.pack(
                anchor="w",
                fill="x",
                padx=self.theme["spacing"]["pad"],
                pady=(self.theme["spacing"]["pad_small"], self.theme["spacing"]["pad"]),
            )

        self._update_wraplength(self._wraplength)

    def _handle_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._inner_window, width=event.width)
        self._update_wraplength(max(200, event.width - 40))

    def _register_wrappable(self, label: ttk.Label) -> None:
        label.configure(wraplength=self._wraplength, justify="left", anchor="w")
        self._wrappable_labels.append(label)

    def _update_wraplength(self, wraplength: int) -> None:
        if wraplength == self._wraplength:
            return
        self._wraplength = wraplength
        for label in self._wrappable_labels:
            label.configure(wraplength=self._wraplength, justify="left", anchor="w")
