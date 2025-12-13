# GUI + Autonomy updates

## GUI wiring
- The Tkinter GUI now instantiates a single `SentinelController` at startup and routes all input through `ControllerBridge` on a background thread.
- Chat responses, plan updates, and recent logs are streamed back into the GUI without blocking the UI thread.
- Chat, plan, and log panels allow text selection, keyboard shortcuts (Ctrl/Cmd + A/C/V/X), and right-click context menus for copy/paste/cut.

## Autonomy gating
- Default behavior is **plan-only**. The agent will not execute tools unless the user explicitly approves or enables `/auto` mode.
- Approvals can be given via `/auto on`, bounded `/auto` commands (e.g., `/auto 5`, `/auto 1h`), or natural confirmations such as “run it”, “keep going”, or “continue until done or 1 hour”.
- `/auto <number>` grants up to N autonomous turns (1-hour timer by default). `/auto <duration>` grants time-bounded autonomy with an unlimited turn budget within that window.
- Autonomy automatically stops when the turn budget is exhausted or the timer expires; subsequent inputs revert to plan-only proposals.

## Failure visibility
- LLM failures now include backend, endpoint, model, status, and a response snippet in both logs and user-visible messages.
