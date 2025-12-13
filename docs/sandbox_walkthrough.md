# Sandbox Walkthrough and Feature Coverage

This guide walks from zero-to-hero in a local sandbox so you can exercise the Sentinel MAX stack end-to-end, observe current behaviors, and capture gaps to address.

## 1) Environment bring-up
- Create a fresh virtual environment and install dependencies:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r sentinel/requirements.txt
  ```
- Export a sandbox root if you want a non-default location (defaults to `F:\\Sandbox`):
  ```bash
  export SENTINEL_SANDBOX_ROOT="$PWD/.sandbox"
  mkdir -p "$SENTINEL_SANDBOX_ROOT"
  ```
- Optional: point long-term storage elsewhere by setting `SENTINEL_STORAGE_DIR`.

## 2) Kick the tires in CLI mode
- Launch the agent:
  ```bash
  python -m sentinel.main --mode cli
  ```
- Start with low-risk tooling:
  - `/tools` to confirm registry contents and permissions.
  - `/tool echo {"text": "hello"}` to verify the sandbox path.
  - `/tool ls {"path": "."}` to confirm sandboxed filesystem visibility.
- Exercise planning without execution:
  - Enter a goal like "draft a plan to summarize project risks" and confirm the returned plan (execution will be held until approved).
  - Use `/run` to execute a pending plan once you are comfortable with the steps and policy metadata.

## 3) Autonomy and policy checks
- Toggle bounded autonomy to observe policy gating and loop behavior:
  - `/auto 2` grants two autonomous cycles (default 1-hour timer) and should show planner→worker→reflection transitions.
  - `/auto until done` runs until the goal completes or policy stops it; watch for policy events if steps violate constraints.
- Inspect governance artifacts:
  - Policy events should appear in logs under `policy_events` in the sandbox.
  - Execution traces and reflections land under `execution/` and `reflection.*` namespaces.

## 4) Memory + reflection validation
- Submit a few related goals (e.g., "research GUI gap", then "list open GUI tasks") and ensure responses mention prior context, showing the vector/symbolic recall path.
- Check that reflection summaries propose plan adjustments and tool-gap suggestions after autonomous runs.

## 5) Tooling breadth
- Web and code tools:
  - `/tool web_search {"query": "structured logging best practices"}` to exercise deterministic web search (requires `requests`).
  - `/tool code_analyzer {"code": "import os\nos.system('echo hi')"}` to see safety scoring and recommendations.
- Microservice builder:
  - Provide a minimal spec ("build a FastAPI hello-world") and ensure the builder runs inside the sandbox; verify artifacts are written under `artifacts/` without escaping the sandbox root.
- Browser agent:
  - Trigger the `browser_agent` tool to validate registration and sandboxed execution; ensure it respects policy limits and does not execute arbitrary system commands.

## 6) GUI/server sanity check
- Run GUI mode and confirm it routes through the full pipeline:
  ```bash
  python -m sentinel.main --mode gui
  ```
- Expected behavior (today): GUI widgets should stream outputs from `SentinelController.process_input()` via `ControllerBridge`. If you only see static placeholder responses, the GUI wiring is incomplete.
- For server mode, ensure FastAPI handlers instantiate `SentinelController` once and reuse it per process.

## 7) What to change / add next
- **Wire the GUI to the real pipeline**: Replace the `_process()` placeholder in `sentinel/gui/app.py` with `ControllerBridge` calls so GUI input flows through the same planner/worker/policy stack as CLI/server.
- **Defer tool registration side effects**: Move `DEFAULT_TOOL_REGISTRY` population out of import time and behind the controller bootstrap to avoid global state leakage and optional-dependency crashes.
- **Make web tools optional**: Guard `requests` imports and surface a clearer error or disable web tools when the dependency is missing so CLI/GUI startup does not fail on fresh environments.
- **Harmonize dialog managers**: Remove or alias the unused dialog manager variants so only `sentinel/conversation/dialog_manager.py` remains authoritative.
- **Improve autonomy UX**: Add visible counters/timers for `/auto` runs and surface policy stops in the user-facing transcript, not just logs.
- **Add sandbox smoke tests**: Provide a slim pytest module that runs echo, ls, web_search (if available), and code_analyzer in a temporary sandbox to detect registry regressions.

## 8) Exit and cleanup
- Stop the CLI/GUI process with `Ctrl+C`.
- Remove the temporary sandbox if desired:
  ```bash
  rm -rf "$SENTINEL_SANDBOX_ROOT"
  ```

Following the sequence above exercises planning, autonomy, policy enforcement, memory recall, tool execution, and GUI/server gaps so you can prioritize fixes with concrete observations.
