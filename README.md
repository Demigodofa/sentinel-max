# Sentinel MAX (updated 2024-05-19)

Enterprise-grade autonomous agent framework with long-horizon governance, reflective execution, and sandboxed tooling.
Run it via CLI/GUI/API and let the conversation router hand confirmed goals to the planner/worker/reflection stack.

## Highlights

- **Long-Horizon Project Engine**: Durable project memory, dependency validation, policy-governed planning, and human-readable reporting.
- **Policy-First Execution**: Safety, permission, determinism, and autonomy constraints enforced across planning and runtime.
- **Memory Intelligence**: Symbolic + vector storage with curated contexts for planning, execution, and reflection — all persisted under the sandbox root (`F:\\Sandbox` by default).
- **Sandboxed Tooling**: Sandbox-backed tool registry plus multi-agent coordination for tool evolution; GUI and CLI both drive the same controller pipeline.
- **Structured Pipeline Telemetry**: Each ingest → plan → policy → execute → reflect stage emits correlated records so you can trace a turn end-to-end via CLI or GUI.
- **GUI resilience**: The chat input is pinned to the bottom and scales with the window, so resizing no longer hides or clips the entry field.

## Runtime pipeline

- **Controller orchestration**: `SentinelController` instantiates memory, world model, tool registry, sandbox variants, policy engine, planner, worker, reflection, autonomy loop, research engine, and hot reload/self-modification guardrails. Default tools are registered during initialization, so missing tool errors usually mean controller startup failed.
- **LLM connectivity**: Sentinel now uses the OpenAI Chat Completions API exclusively (default model `gpt-4o`). A startup health check asks the model to respond with “ok” and reports the outcome to CLI stdout, the GUI meta log, and `pipeline_events` for visibility. Structured logs include `backend=openai`, `model`, `base_url`, `request_id`, and `latency_ms`.
- **Conversation router**: `ConversationController` normalizes chat input, routes slash commands, requests confirmation when autonomy is off, and delivers accepted goals to the planner/worker/reflection loop. Slash-command flows (/auto, /tools, etc.) now retain pipeline correlation IDs so telemetry stays linked even when the intent engine is bypassed.
- **Default tools**: Filesystem list/read/write/delete, sandboxed exec, deterministic web search, internet extractor, code analyzer, microservice builder, browser agent, and a configurable echo tool registered at startup.
- **Direct tool execution**: `/tool <name> <json>` now runs the requested tool through the sandbox when available (with a registry fallback), so filesystem, sandbox exec, and web search tools execute for real rather than being simulated.
- **Plan publication for GUI**: Executed task graphs are mirrored into simplified plan records under the `plans` namespace, enabling the GUI plan panel to render current steps instead of showing “No plan available.”
- **State inspection**: `/state` in the CLI summarizes latest plan, execution, policy, and reflection records (with correlation IDs), and the GUI includes a pipeline state panel reading from `plans`, `execution*`, `reflection.*`, `policy_events`, and `pipeline_events`.

## Quickstart

1. **Install dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r sentinel/requirements.txt
   ```

2. **Configure OpenAI access (required)**

   Set the OpenAI environment variables before launching Sentinel:

   - `SENTINEL_OPENAI_API_KEY` (required)
   - `SENTINEL_OPENAI_MODEL` (default: `gpt-4o`)
   - `SENTINEL_OPENAI_BASE_URL` (default: `https://api.openai.com/v1`)
   - `SENTINEL_OPENAI_TIMEOUT_SECS` (default: `60`)

3. **Run the agent**

   CLI mode uses the shared controller and autonomy loop:

   ```bash
   python -m sentinel.main --mode cli
   ```

   - `/tools` lists registered tools; `/tool <name> <json>` runs a tool through the sandbox.
   - `/auto on` enables confirmation-free autonomy for the current session.

4. **Execute the full test suite**

   ```bash
   python -m pytest sentinel/tests
   ```

5. **Storage defaults (F:\\Sandbox)**

   The sandbox root defaults to `F:\\Sandbox` (configurable via `SENTINEL_SANDBOX_ROOT`), and both symbolic + vector memories now persist under `memory/` in that sandbox. Override with `SENTINEL_STORAGE_DIR` if you need a different memory location. External evidence (search queries, fetched pages, provenance metadata) is written to `memory/external_sources` alongside the stores for later retrieval; call `MemoryManager.load_external_source(<key>)` to read the persisted content and metadata in later sessions.

## Tool summary

Default tools registered at controller startup and run through the sandbox:

- `web_search` (deterministic): DuckDuckGo HTML search with results logged to `memory/external_sources` for provenance.
- `internet_extract` (deterministic): Scrapes, cleans, summarizes, and stores content; evidence and cleaned HTML are persisted to `memory/external_sources` and vector memory.
- Filesystem tools (`fs_list`, `fs_read`, `fs_write`, `fs_delete`), `sandbox_exec`, `code_analyzer`, `microservice_builder`, `browser_agent`, and the generated `echo` tool all retain the existing safety and policy checks.

## Sandbox walkthrough
Want to exercise every major capability in a single session? Follow [docs/sandbox_walkthrough.md](docs/sandbox_walkthrough.md) for a start-to-finish checklist that covers CLI planning/execution, autonomy gating, policy visibility, memory recall, tool coverage (including web/code/microservice/browser agents), GUI/server expectations, and prioritized follow-up fixes. The guide now includes a coverage matrix and dead-path detection tips so you can confirm conversational commands route correctly and that no part of the pipeline sits idle.

### Applying patches on Windows/PowerShell

If you receive a diff in chat, pasting it directly into PowerShell will raise errors because the shell attempts to execute each
diff line as a command (for example, interpreting `---` and `+++` as operators). Instead, save the diff to a file and let `git`
apply it:

```powershell
# Save the diff text to a file, then apply it
Set-Content patch.diff "<paste the diff content here>"
git apply patch.diff
```

If `git apply` reports problems, check that the repo files match the versions referenced in the diff (look at the `index` hash
lines) or re-run `git status` to ensure you are on the correct branch with no local changes.

### Resolving merge conflicts after pulling

If you pull upstream changes and see conflicts (for example in `sentinel/dialog/dialog_manager.py`), keep the version that includes the newer long-horizon reporting helpers rather than deleting sections. A safe resolution workflow:

1. Run `git status` to list conflicted files.
2. Open each file with conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).
3. Keep the section that preserves composite reporting (e.g., `show_full_report`) and the long-horizon policy/dependency wiring; remove the markers and any duplicated legacy snippets.
4. Re-run the relevant tests (`python -m pytest sentinel/tests/block6`) to confirm the resolved file still passes synthetic coverage for policy, dialog, dependency handling, and the long-horizon engine.
5. Stage and commit once all conflicts are cleared.

These steps ensure the governed long-horizon features remain intact when merging upstream work.

## Long-Horizon Project Engine

The `LongHorizonProjectEngine` orchestrates durable project records, dependency-aware planning, policy enforcement, and dialog outputs.

```python
from sentinel.project.long_horizon_engine import LongHorizonProjectEngine
from sentinel.project.project_memory import ProjectMemory

engine = LongHorizonProjectEngine(memory=ProjectMemory())
project = engine.create_project(
    name="Website Refresh",
    description="End-to-end redesign with staged rollout",
    goals=[{"id": "g-home", "text": "Ship new homepage"}],
)

engine.register_plan(project["project_id"], [
    {"id": "design", "action": "Design hero and layout", "depends_on": []},
    {"id": "build", "action": "Implement responsive components", "depends_on": ["design"]},
])

engine.record_step_result(project["project_id"], "design", "completed")
print(engine.progress_report(project["project_id"]))
print(engine.dependency_issues(project["project_id"]))
```

### Safety & Governance

- **PolicyEngine** guards project limits (goals, dependency depth, duration, refinement rounds) and blocks forbidden actions.
- **Structured policy outcomes**: Policy decisions now return an allow/block record with reasons and rewrites that flow into reflections and final responses for guided replanning.
- **ProjectDependencyGraph** validates cycles, unresolved nodes, and computes depth before plans are persisted.
- **ProjectMemory** provides atomic, versioned persistence with schema validation for goals, plans, histories, and reflections.
- **DialogManager** surfaces overviews, progress, dependency issues, and milestones for human operators.
- **Health checks**: `LongHorizonProjectEngine.health_report()` reports storage readiness (including external drives) and current policy limits.

## Repository Layout

- `sentinel/controller.py`: Central wiring for planner, worker, policy, memory, dialog, and autonomy loop.
- `sentinel/policy/policy_engine.py`: Safety, preference, execution, and long-horizon governance rules.
- `sentinel/project/long_horizon_engine.py`: Project orchestrator combining memory, policy, dependencies, and dialog outputs.
- `sentinel/project/project_memory.py`: Versioned persistent storage for long-running projects.
- `sentinel/project/dependency_graph.py`: Dependency normalization, validation, and depth computation.
- `sentinel/dialog/dialog_manager.py`: Human-facing summaries and composite reports.
- `sentinel/tests/`: Unit tests for planning, execution, autonomy, and long-horizon behaviors.

## Operations

- **Policy visibility**: Policy events are persisted as structured facts with mirrored text entries in `policy_events` (when configured) for auditability.
- **Sandbox execution**: Tools run inside a restricted sandbox via the worker and topological executor.
- **Autonomy guardrails**: Time, cycle, and refinement limits enforced before each loop iteration with per-cycle metadata persisted for review. Use `/auto until done` to keep autonomy running without timing out; `/auto on|off` toggles bounded runs.
- **Reflection**: Structured reflections stored under typed namespaces support replanning and transparency.
- **Tool gaps**: When planning cannot map a subgoal to a registered tool, a tool-gap request is persisted to `plans` and `policy_events` so follow-up tooling can be generated with sandbox context.
- **Tool-aware context windows**: Memory contexts now embed a concise tool registry summary so adaptive planning can ground tool selection without falling back to deterministic planning when no prior memories are available.

## Self-augmentation feedback

After each autonomous run the agent surfaces optimization hints (critic feedback, plan optimizations, and detected tool gaps). When gaps are found, the system proposes new agents/tools and records these suggestions in memory for follow-up.

## Support

For issues or contributions, open a pull request or file a ticket describing the scenario, expected behavior, and reproduction steps.
