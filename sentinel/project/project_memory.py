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
        path = self._path(project_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def list_projects(self) -> List[Dict[str, str]]:
        results = []
        for file in os.listdir(self.storage_path):
            if file.endswith(".json"):
                with open(os.path.join(self.storage_path, file), "r") as f:
                    d = json.load(f)
                    results.append({
                        "project_id": d["project_id"],
                        "name": d.get("name", ""),
                        "description": d.get("description", "")
                    })
        return results

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
