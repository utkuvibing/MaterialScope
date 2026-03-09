"""In-memory project state store for tranche-1 backend routes."""

from __future__ import annotations

import threading
import uuid
from typing import Any


class ProjectStore:
    """Thread-safe in-memory project state store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._projects: dict[str, dict[str, Any]] = {}

    def put(self, project_state: dict[str, Any]) -> str:
        project_id = uuid.uuid4().hex
        with self._lock:
            self._projects[project_id] = project_state
        return project_id

    def get(self, project_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._projects.get(project_id)

    def set(self, project_id: str, project_state: dict[str, Any]) -> bool:
        with self._lock:
            if project_id not in self._projects:
                return False
            self._projects[project_id] = project_state
            return True
