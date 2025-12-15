# Agent Notes

## Orchestration pipeline
- Natural-language turns can bypass the legacy confirmation loop when `AUTO_MODE` is enabled. The `sentinel.orchestration.Orchestrator` runs tool calls automatically, publishes plan steps to the `plans` namespace, and asks for confirmation before destructive tools (`fs_delete`, `fs_write`, `pip_install`, `kill_process`).
- The plan publisher (`sentinel/orchestration/plan_publisher.py`) keeps the GUI Plan panel up to date. Update the plan steps' `status` and `note` fields to reflect queued/running/done/failed/awaiting_confirmation states.
- Post-run optimization persists alias drops and intent rules via `sentinel/orchestration/optimizer.py`; review `memory/tool_aliases.json` and `intent_rules.json` when adjusting tool schemas.
- GUI input now supports an injected command queue (`SentinelApp(..., injected_command_queue=...)`) so watchers like `sentinel/watchers/browser_command_relay.py` can feed `<START>...<STOP>` blocks from a ChatGPT tab straight into the controller without bypassing the GUI pipeline. The helper runner lives at `scripts/browser_chatgpt_relay.py`.
- The Windows launcher (`start_sentinel_max.bat`) starts the ChatGPT browser relay watcher by default when `START_BROWSER_RELAY` normalizes to `1`/`true`/`yes`/`on`. The relay is Selenium-based (Chrome window + chromedriver on PATH). Relay startup status is logged to `logs/launcher_last.log` and surfaces in a dedicated window.

## Testing and docs
- New orchestration tests live in `sentinel/tests/test_orchestrator_plan_publishes.py`, `test_orchestrator_confirmation_gate.py`, and `test_optimizer_persists_rules.py`. Keep them passing when changing routing, plan publishing, confirmation gates, or optimizer behavior.
- Update this file and `README.md` whenever orchestration behavior, plan publishing semantics, or safety confirmations change.
