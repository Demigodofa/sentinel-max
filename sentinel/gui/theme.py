"""Shared theme definitions for the Sentinel MAX GUI."""
from __future__ import annotations

import sys


def load_theme() -> dict:
    """
    Windows-safe high-contrast defaults.

    NOTE: On Windows, native ttk themes often ignore Entry background/fieldbackground.
    We force a styleable theme ('clam') in app.py, and use tk.Entry for the input box.
    """
    is_windows = sys.platform.startswith("win")

    # Dark-ish, high contrast, readable on Windows.
    colors = {
        "app_bg": "#111315",
        "panel_bg": "#171A1D",
        "panel_border": "#2A2F36",
        "text": "#E8E8E8",
        "muted": "#B7BDC6",
        "accent": "#4EA1FF",
        "user_bubble": "#1F2A36",
        "agent_bubble": "#1B1E22",
        "selection_bg": "#2D5D9F",
        "selection_fg": "#FFFFFF",
        "entry_bg": "#0F1113",
        "entry_fg": "#FFFFFF",
        "entry_insert": "#4EA1FF",
        "error": "#FF5A5A",
    }

    # Slightly larger font helps legibility on Windows scaling.
    fonts = {
        "body": ("Segoe UI", 11 if is_windows else 10),
        "mono": ("Consolas", 10) if is_windows else ("Menlo", 10),
    }

    return {
        "colors": colors,
        "fonts": fonts,
        "spacing": {"pad": 10, "pad_small": 6, "pad_tiny": 4},
        "border": {"width": 1, "relief": "flat"},
    }
