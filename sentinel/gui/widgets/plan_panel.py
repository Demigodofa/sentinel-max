"""Plan panel widget for displaying plan steps."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Iterable, Any

from sentinel.agent_core.base import PlanStep
from sentinel.planning.task_graph import TaskNode
from sentinel.gui.theme import load_theme


class PlanPanel(ttk.Frame):
    """Scrollable panel showing the current plan."""

    def __init__(self, master: tk.Misc, theme: dict | None = None) -> None:
        self.theme = theme or load_theme()
        super().__init__(master, padding=self.theme["spacing"]["pad"], style="PlanPanel.TFrame")
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
            wraplength=260,
            justify="left",
        )

    def _build_widgets(self) -> None:
        colors = self.theme["colors"]
        self.configure(style="PlanPanel.TFrame")

        # Header (goal + version) sits above the scrollable list.
        header = ttk.Frame(self, style="PlanPanel.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(0, weight=1)

        self._goal_var = tk.StringVar(value="Plan")
        self._goal_label = ttk.Label(
            header,
            textvariable=self._goal_var,
            style="PlanStepTitle.TLabel",
        )
        self._goal_label.grid(row=0, column=0, sticky="w")

        self._version_var = tk.StringVar(value="")
        self._version_label = ttk.Label(
            header,
            textvariable=self._version_var,
            style="PlanStepBody.TLabel",
        )
        self._version_label.grid(row=1, column=0, sticky="w")

        self.canvas = tk.Canvas(self, background=colors["panel_bg"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style="PlanPanel.TFrame")

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(window, width=e.width)
        )

        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.scrollbar.grid(row=1, column=1, sticky="ns")

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

    def update_plan(self, payload: Any) -> None:
        """Render the current plan.

        The GUI bridge may send either:
        - an Iterable[PlanStep|TaskNode]
        - a dict payload: {"goal": str|None, "version": int|None, "steps": [...]}.
        """

        goal = None
        version = None
        steps = payload
        if isinstance(payload, dict):
            goal = payload.get("goal")
            version = payload.get("version")
            steps = payload.get("steps")

        if goal:
            self._goal_var.set(f"Goal: {goal}")
        else:
            self._goal_var.set("Plan")
        self._version_var.set(f"Version: {version}" if version else "")

        for child in self.inner.winfo_children():
            child.destroy()

        if not steps:
            empty = ttk.Label(
                self.inner,
                text="No plan available",
                style="PlanStepBody.TLabel",
            )
            empty.pack(anchor="w", padx=self.theme["spacing"]["pad"], pady=self.theme["spacing"]["pad_small"])
            return

        for step in steps:
            frame = ttk.Frame(self.inner, style="PlanStep.TFrame")
            step_id = getattr(step, "step_id", None) or getattr(step, "id", "?")

            status = ""
            meta = getattr(step, "metadata", None) or {}
            if isinstance(meta, dict):
                if meta.get("status") == "done":
                    status = "Γ£à "
                elif meta.get("status") == "failed":
                    status = "Γ¥î "
                elif meta.get("status"):
                    status = "ΓÅ│ "

            title = ttk.Label(
                frame,
                text=f"{status}Step {step_id}: {step.description}",
                style="PlanStepTitle.TLabel",
            )
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
                body.pack(anchor="w", pady=(self.theme["spacing"]["pad_small"], 0))

            frame.pack(
                anchor="w",
                fill="x",
                padx=self.theme["spacing"]["pad"],
                pady=(self.theme["spacing"]["pad_small"], self.theme["spacing"]["pad"]),
            )
