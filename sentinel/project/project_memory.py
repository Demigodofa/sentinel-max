"""Persistence utilities for long-horizon projects."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict


class ProjectMemory:
    """Lightweight JSON-backed storage for project metadata and logs."""

    def __init__(self, storage_path: str | Path = "projects") -> None:
        self.storage_dir = Path(storage_path)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _project_path(self, project_id: str) -> Path:
        return self.storage_dir / f"{project_id}.json"

    def create(self, name: str, description: str) -> Dict[str, Any]:
        project_id = self._generate_project_id()
        data = {
            "project_id": project_id,
            "name": name,
            "description": description,
            "created_at": time.time(),
            "updated_at": time.time(),
            "goals": {},
            "plans": {},
            "dependencies": {},
            "logs": [],
            "reflections": [],
        }
        self.save(project_id, data)
        return data

    def load(self, project_id: str) -> Dict[str, Any]:
        path = self._project_path(project_id)
        if not path.exists():
            raise FileNotFoundError(f"Project not found: {project_id}")
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    def save(self, project_id: str, project_data: Dict[str, Any]) -> None:
        project_data["updated_at"] = time.time()
        path = self._project_path(project_id)
        with path.open("w", encoding="utf-8") as f:
            json.dump(project_data, f, indent=2)

    def append_log(self, project_id: str, entry: Dict[str, Any]) -> None:
        project = self.load(project_id)
        entry = {**entry, "timestamp": time.time()}
        project.setdefault("logs", []).append(entry)
        self.save(project_id, project)

    def append_reflection(self, project_id: str, reflection: Dict[str, Any]) -> None:
        project = self.load(project_id)
        record = {**reflection, "timestamp": time.time()}
        project.setdefault("reflections", []).append(record)
        self.save(project_id, project)

    def _generate_project_id(self) -> str:
        import uuid

        return str(uuid.uuid4())
