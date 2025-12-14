"""Regression tests for GUI layout constraints."""

from __future__ import annotations

import tkinter as tk

import pytest

from sentinel.gui.app import SentinelApp


def _build_app() -> tuple[tk.Tk, SentinelApp]:
    root = tk.Tk()
    root.withdraw()
    app = SentinelApp(root)
    root.update_idletasks()
    return root, app


def test_plan_panel_width_does_not_overflow_chat() -> None:
    try:
        root, app = _build_app()
    except tk.TclError:
        pytest.skip("Tkinter display not available")

    try:
        root.update_idletasks()
        assert app.plan_panel.winfo_reqwidth() <= 500
        assert app.chat.winfo_reqwidth() >= 300
    finally:
        root.destroy()
