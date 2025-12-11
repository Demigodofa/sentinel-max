"""Very small cooperative task scheduler."""
from __future__ import annotations

from collections import deque
from typing import Callable, Deque, Any


class TaskScheduler:
    def __init__(self) -> None:
        self._queue: Deque[Callable[[], Any]] = deque()

    def add(self, task: Callable[[], Any]) -> None:
        self._queue.append(task)

    def run_next(self) -> Any:
        if not self._queue:
            return None
        task = self._queue.popleft()
        return task()

    def run_all(self) -> list[Any]:
        results = []
        while self._queue:
            results.append(self.run_next())
        return results

    def clear(self) -> None:
        self._queue.clear()
