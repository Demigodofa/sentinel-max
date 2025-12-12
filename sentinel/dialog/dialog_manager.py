from __future__ import annotations
from typing import Dict, Any, List


class DialogManager:
    """
    Provides formatted human-readable dialog outputs for:
    - project overview
    - progress reports
    - dependency issues
    - milestones
    """

    # ------------------------------------------------------------
    # PROJECT OVERVIEW
    # ------------------------------------------------------------

    def show_project_overview(self, project_data: Dict[str, Any]) -> str:
        goals = project_data.get("goals", [])
        name = project_data.get("name")
        desc = project_data.get("description")

        lines = [
            f"📦 PROJECT: {name}",
            f"📝 Description: {desc}",
            f"🎯 Goals ({len(goals)}):"
        ]
        for g in goals:
            gid = g["id"]
            status = g.get("status", "pending")
            lines.append(f"  - [{status}] {gid}: {g['text']}")

        return "\n".join(lines)

    # ------------------------------------------------------------
    # PROGRESS REPORT
    # ------------------------------------------------------------

    def show_project_progress(self, progress: Dict[str, Any]) -> str:
        pct = progress.get("pct", 0)
        completed = progress.get("completed_goals", 0)
        total = progress.get("total_goals", 0)

        return (
            f"📊 PROGRESS: {pct}%\n"
            f"Completed {completed} / {total} goals."
        )

    # ------------------------------------------------------------
    # DEPENDENCY ISSUES
    # ------------------------------------------------------------

    def show_dependency_issues(self, issues: Dict[str, Any]) -> str:
        cycles = issues.get("cycles", [])
        unresolved = issues.get("unresolved", [])

        out = ["⚠ DEPENDENCY ISSUES:"]
        if cycles:
            out.append(f"  🔁 Cycles detected: {cycles}")
        if unresolved:
            out.append(f"  ❓ Unresolved: {unresolved}")

        if len(out) == 1:
            return "✔ No dependency issues."

        return "\n".join(out)

    # ------------------------------------------------------------
    # MILESTONE NOTIFICATION
    # ------------------------------------------------------------

    def notify_milestone(self, milestone_data: Dict[str, Any]) -> str:
        title = milestone_data.get("title")
        desc = milestone_data.get("description")
        return f"🏁 MILESTONE REACHED: {title}\n{desc}"

    # ------------------------------------------------------------
    # COMPOSITE STATUS
    # ------------------------------------------------------------

    def show_full_report(self, project: Dict[str, Any], progress: Dict[str, Any], issues: Dict[str, Any]) -> str:
        sections = [self.show_project_overview(project), self.show_project_progress(progress)]
        dependency_section = self.show_dependency_issues(issues)
        if dependency_section:
            sections.append(dependency_section)
        return "\n\n".join(sections)

    # ------------------------------------------------------------
    # HEALTH SUMMARY
    # ------------------------------------------------------------

    def show_health(self, health: Dict[str, Any]) -> str:
        lines = ["🩺 SYSTEM HEALTH"]
        storage = health.get("storage", {})
        lines.append(f"  📂 Storage path: {storage.get('storage_path')}")
        lines.append(f"  ✅ Readable: {storage.get('readable')}")
        lines.append(f"  ✅ Writable: {storage.get('writable')}")
        lines.append(f"  📁 Projects: {storage.get('projects')}")
        policy = health.get("policy", {})
        if policy:
            lines.append("  🔒 Policy limits:")
            lines.append(f"    - Max goals: {policy.get('max_goals')}")
            lines.append(f"    - Max depth: {policy.get('max_dependency_depth')}")
            lines.append(f"    - Max days: {policy.get('max_project_duration_days')}")
            lines.append(f"    - Max refinement rounds: {policy.get('max_refinement_rounds')}")
        return "\n".join(lines)

    # ------------------------------------------------------------
    # SAFE FALLBACKS
    # ------------------------------------------------------------

    def respond_conversationally(self, text: str) -> str:
        return "I hear you. What would you like to work on?"

    def acknowledge_information(self, text: str) -> str:
        return "Got it — I've noted that."

    def propose_plan(self, goal) -> str:
        return (
            "I can plan this:\n"
            f"{goal}\n\n"
            "Execute? (y/n) — or say `/auto` to run automatically."
        )
