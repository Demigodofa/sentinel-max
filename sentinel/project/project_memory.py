"""Persistence utilities for long-horizon projects."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List


class ProjectMemory:
    """Lightweight JSON-backed storage for project metadata and logs."""

    def __init__(self, storage_path: str | Path = "projects") -> None:
        self.storage_dir = Path(os.path.expanduser(str(storage_path)))
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @property
    def storage_path(self) -> str:
        return str(self.storage_dir)

    def _project_path(self, project_id: str) -> Path:
        return self.storage_dir / f"{project_id}.json"

    def _atomic_write(self, path: Path, payload: Dict[str, Any]) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        tmp_path.replace(path)

    def _validate_structure(self, data: Dict[str, Any]) -> None:
        required_fields = {
            "project_id",
            "name",
            "description",
            "version",
            "goals",
            "plans",
            "dependencies",
            "logs",
            "reflections",
        }
        missing = required_fields.difference(data.keys())
        if missing:
            raise ValueError(f"Project data missing required fields: {', '.join(sorted(missing))}")
        if not isinstance(data.get("goals"), dict):
            raise ValueError("goals must be a dictionary keyed by goal id")
        if not isinstance(data.get("plans"), dict):
            raise ValueError("plans must be a dictionary keyed by plan id")
        if not isinstance(data.get("dependencies"), dict):
            raise ValueError("dependencies must be a dictionary")
        if not isinstance(data.get("logs"), list):
            raise ValueError("logs must be a list")
        if not isinstance(data.get("reflections"), list):
            raise ValueError("reflections must be a list")

    def _generate_project_id(self) -> str:
        import uuid

        return str(uuid.uuid4())

    def create(self, name: str, description: str) -> Dict[str, Any]:
        project_id = self._generate_project_id()
        data = {
            "project_id": project_id,
            "name": name,
            "description": description,
            "created_at": time.time(),
            "updated_at": time.time(),
            "version": 1,
            "goals": {},
            "plans": {},
            "dependencies": {},
            "logs": [],
            "reflections": [],
        }
        self._validate_structure(data)
        self._atomic_write(self._project_path(project_id), data)
        return data

    def load(self, project_id: str) -> Dict[str, Any]:
        path = self._project_path(project_id)
        if not path.exists():
            raise FileNotFoundError(f"Project not found: {project_id}")
        with path.open("r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise ValueError(f"Corrupt project file: {project_id}") from exc
        self._validate_structure(data)
        return data

    def save(self, project_id: str, project_data: Dict[str, Any]) -> None:
        project_data = dict(project_data)
        project_data["updated_at"] = time.time()
        project_data["version"] = project_data.get("version", 0) + 1
        self._validate_structure(project_data)
        self._atomic_write(self._project_path(project_id), project_data)

    def list_projects(self) -> List[Dict[str, Any]]:
        results = []
        for file in self.storage_dir.glob("*.json"):
            with file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                results.append(
                    {
                        "project_id": data["project_id"],
                        "name": data.get("name", ""),
                        "description": data.get("description", ""),
                        "updated_at": data.get("updated_at"),
                        "version": data.get("version"),
                    }
                )
        return sorted(results, key=lambda r: r.get("updated_at") or 0, reverse=True)

    def health_check(self) -> Dict[str, Any]:
        diagnostics: Dict[str, Any] = {
            "storage_path": self.storage_path,
            "writable": os.access(self.storage_path, os.W_OK),
            "readable": os.access(self.storage_path, os.R_OK),
            "projects": len(list(self.storage_dir.glob("*.json"))),
        }
        return diagnostics

    def append_log(self, project_id: str, entry: Dict[str, Any]) -> None:
        project = self.load(project_id)
        record = {**entry, "timestamp": time.time()}
        project.setdefault("logs", []).append(record)
        self.save(project_id, project)

    def append_reflection(self, project_id: str, reflection: Dict[str, Any]) -> None:
        project = self.load(project_id)
        record = {**reflection, "timestamp": time.time()}
        project.setdefault("reflections", []).append(record)
        self.save(project_id, project)

    def upsert_goals(self, project_id: str, goals: List[Dict[str, Any]]) -> Dict[str, Any]:
        data = self.load(project_id)
        for goal in goals:
            goal_id = goal["id"]
            current = data["goals"].get(goal_id, {})
            current.update(goal)
            current.setdefault("status", "pending")
            data["goals"][goal_id] = current
        self.save(project_id, data)
        return data

    def record_plan(self, project_id: str, plan_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        data = self.load(project_id)
        data.setdefault("plans", {})[plan_id] = plan
        self.save(project_id, data)
        return data

    def record_dependencies(self, project_id: str, dependency_map: Dict[str, Any]) -> Dict[str, Any]:
        data = self.load(project_id)
        data["dependencies"] = dependency_map
        self.save(project_id, data)
        return data

    def set_goal_status(self, project_id: str, goal_id: str, status: str) -> Dict[str, Any]:
        data = self.load(project_id)
        if goal_id not in data["goals"]:
            raise KeyError(f"Goal {goal_id} not found for project {project_id}")
        data["goals"][goal_id]["status"] = status
        self.save(project_id, data)
        return data

    def snapshot(self, project_id: str) -> Dict[str, Any]:
        """Return a copy of the current project state."""
        return self.load(project_id)
