from __future__ import annotations

from collections import deque
import threading
from typing import Any


class EventPusher:
    def __init__(self, *, max_queue_size: int = 4000) -> None:
        self._window: Any | None = None
        self._lock = threading.Lock()
        self._queue: deque[dict[str, Any]] = deque()
        self._max_queue_size = max(200, int(max_queue_size))

    def attach_window(self, window: Any) -> None:
        self._window = window

    def push(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._queue.append(event)
            overflow = len(self._queue) - self._max_queue_size
            for _ in range(max(0, overflow)):
                self._queue.popleft()

    def drain(self, limit: int = 200) -> list[dict[str, Any]]:
        batch_size = max(1, int(limit))
        items: list[dict[str, Any]] = []
        with self._lock:
            while self._queue and len(items) < batch_size:
                items.append(self._queue.popleft())
        return items
