# Sentinel MAX

Enterprise-grade autonomous agent framework with long-horizon governance, reflective execution, and sandboxed tooling.

## Highlights

- **Long-Horizon Project Engine**: Durable project memory, dependency validation, policy-governed planning, and human-readable reporting.
- **Policy-First Execution**: Safety, permission, determinism, and autonomy constraints enforced across planning and runtime.
- **Memory Intelligence**: Symbolic + vector storage with curated contexts for planning, execution, and reflection.
- **Simulation & Tooling**: Sandbox-backed tool registry, simulation sandbox, and multi-agent coordination for tool evolution.

## Quickstart

1. **Install dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r sentinel/requirements.txt
   ```

2. **Run the agent**

   CLI mode uses the shared controller and autonomy loop:

   ```bash
   python -m sentinel.main --mode cli
   ```

3. **Execute the full test suite**

   ```bash
   python -m pytest sentinel/tests
   ```

4. **Use an external drive (e.g., F:\\Sandbox)**

   Set `SENTINEL_PROJECT_STORAGE` to point long-horizon storage at your external sandbox location. All project files will be written there with atomic JSON updates.

   ```bash
   export SENTINEL_PROJECT_STORAGE="/mnt/f/Sandbox"
   python -m sentinel.main --mode cli
   ```

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

- **Policy visibility**: Policy events are persisted to memory (when configured) for auditability.
- **Sandbox execution**: Tools run inside a restricted sandbox via the worker and topological executor.
- **Autonomy guardrails**: Time, cycle, and refinement limits enforced before each loop iteration.
- **Reflection**: Structured reflections stored under typed namespaces support replanning and transparency.

## Support

For issues or contributions, open a pull request or file a ticket describing the scenario, expected behavior, and reproduction steps.
