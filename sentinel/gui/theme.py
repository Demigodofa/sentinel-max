"""Shared theme definitions for the Sentinel MAX GUI."""
from __future__ import annotations

from typing import Dict, Any


DEFAULT_THEME: Dict[str, Any] = {
    "fonts": {
        "heading": ("Arial", 12, "bold"),
        "body": ("Arial", 10),
        "mono": ("Courier New", 10),
    },
    "colors": {
        "bg": "#0f172a",
        "panel_bg": "#111827",
        "panel_border": "#1f2937",
        "text": "#e5e7eb",
        "muted_text": "#9ca3af",
        "accent": "#22c55e",
        "log_info": "#38bdf8",
        "log_warning": "#fbbf24",
        "log_error": "#f87171",
    },
    "spacing": {
        "pad": 8,
        "pad_small": 4,
    },
    "border": {
        "width": 1,
        "relief": "ridge",
    },
}


def load_theme() -> Dict[str, Any]:
    """Return a copy of the default theme dictionary."""

    return {
        key: (value.copy() if isinstance(value, dict) else value)
        for key, value in DEFAULT_THEME.items()
    }
