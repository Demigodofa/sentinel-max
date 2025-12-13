"""
Sentinel MAX — Unified Launcher

This file is the single entry point for running Sentinel in:
 - CLI mode
 - GUI mode
 - Server (FastAPI) mode

All core functionality is delegated to:
 - Controller
 - GUI app
 - FastAPI backend
"""

import argparse
import sys

from sentinel.conversation import MessageDTO
from sentinel.controller import SentinelController
from sentinel.gui.app import run_gui_app
from sentinel.server.main import app as fastapi_app


APP_NAME = "Sentinel MAX"


def run_cli() -> int:
    """Start the agent in CLI mode."""
    print(f"{APP_NAME} — CLI mode\n")
    controller = SentinelController()

    print("Type your commands. Type 'exit' to quit.\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye.")
            return 0

        response = controller.process_input(MessageDTO(text=user_input, mode="cli"))
        print("Agent:", response)

    return 0


def run_server() -> int:
    """Start the FastAPI server."""
    print(f"{APP_NAME} — Server mode")
    print("Launching FastAPI backend at http://127.0.0.1:8000 ...")

    import uvicorn

    uvicorn.run(
        "sentinel.server.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )

    return 0


def run_gui() -> int:
    """Start the Tkinter GUI."""
    print(f"{APP_NAME} — GUI mode")
    run_gui_app()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(description="Launch Sentinel MAX")
    parser.add_argument(
        "--mode",
        choices=("cli", "gui", "server"),
        default="cli",
        help="Run mode (cli/gui/server)",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.mode == "cli":
        return run_cli()
    if args.mode == "gui":
        return run_gui()
    if args.mode == "server":
        return run_server()

    raise ValueError(f"Unknown mode: {args.mode}")


if __name__ == "__main__":
    sys.exit(main())
