# sentinel/project/project_memory.py

import json
import os
import time
import uuid
from typing import Dict, List, Any


class ProjectMemory:
    """
    Persistent, versioned long-horizon memory store for multi-day projects.
    Stores:
        - metadata
        - goals
        - plans
        - dependency graphs
        - execution history
        - reflection history
    """

    def __init__(self, storage_path: str = "projects"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

    def _path(self, project_id: str) -> str:
        return os.path.join(self.storage_path, f"{project_id}.json")

    def _atomic_write(self, path: str, payload: Dict[str, Any]) -> None:
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp_path, path)

    def _validate_structure(self, data: Dict[str, Any]) -> None:
        required_fields = {"project_id", "name", "description", "version", "goals", "plans", "dependencies", "history", "reflections"}
        missing = required_fields.difference(data.keys())
        if missing:
            raise ValueError(f"Project data missing required fields: {', '.join(sorted(missing))}")
        if not isinstance(data.get("goals"), dict):
            raise ValueError("goals must be a dictionary keyed by goal id")
        if not isinstance(data.get("plans"), dict):
            raise ValueError("plans must be a dictionary keyed by plan id")
        if not isinstance(data.get("dependencies"), dict):
            raise ValueError("dependencies must be a dictionary")
        if not isinstance(data.get("history"), list):
            raise ValueError("history must be a list")
        if not isinstance(data.get("reflections"), list):
            raise ValueError("reflections must be a list")

    def create(self, name: str, description: str) -> Dict[str, Any]:
        project_id = str(uuid.uuid4())
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
            "history": [],
            "reflections": []
        }
        self.save(project_id, data)
        return data

    def load(self, project_id: str) -> Dict[str, Any]:
        path = self._path(project_id)
        if not os.path.exists(path):
            raise FileNotFoundError(f"No project found: {project_id}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, project_id: str, data: Dict[str, Any]) -> None:
        data["updated_at"] = time.time()
        data["version"] = data.get("version", 0) + 1
        self._validate_structure(data)
        path = self._path(project_id)
        self._atomic_write(path, data)

    def list_projects(self) -> List[Dict[str, str]]:
        results = []
        for file in os.listdir(self.storage_path):
            if file.endswith(".json"):
                with open(os.path.join(self.storage_path, file), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    results.append({
                        "project_id": data["project_id"],
                        "name": data.get("name", ""),
                        "description": data.get("description", ""),
                        "updated_at": data.get("updated_at"),
                        "version": data.get("version"),
                    })
        return sorted(results, key=lambda r: r.get("updated_at") or 0, reverse=True)

    def append_log(self, project_id: str, entry: Dict[str, Any]) -> None:
        data = self.load(project_id)
        entry["timestamp"] = time.time()
        data["history"].append(entry)
        self.save(project_id, data)

    def get_history(self, project_id: str) -> List[Dict[str, Any]]:
        data = self.load(project_id)
        return data.get("history", [])

    def append_reflection(self, project_id: str, entry: Dict[str, Any]) -> None:
        data = self.load(project_id)
        entry["timestamp"] = time.time()
        data["reflections"].append(entry)
        self.save(project_id, data)

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
        data["plans"][plan_id] = plan
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
