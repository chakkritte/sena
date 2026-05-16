"""In-memory task queue for distributed agent coordination.

Future: Redis-backed implementation for multi-node deployments.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A unit of work in the distributed queue."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    result: Any | None = None
    error: str | None = None
    assignee: str | None = None


class TaskQueue:
    """Async priority task queue with worker pool support."""

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: asyncio.PriorityQueue[tuple[int, str, Task]] = asyncio.PriorityQueue(
            maxsize=maxsize
        )
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._event = asyncio.Event()

    async def submit(self, task: Task) -> None:
        async with self._lock:
            self._tasks[task.id] = task
        await self._queue.put((-task.priority, task.id, task))
        self._event.set()

    async def next_task(self, timeout: float | None = None) -> Task | None:
        """Get the highest-priority pending task."""
        try:
            _, _, task = await asyncio.wait_for(
                self._queue.get(), timeout=timeout
            )
            async with self._lock:
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now(timezone.utc).isoformat()
            return task
        except asyncio.TimeoutError:
            return None

    async def complete(self, task_id: str, result: Any) -> None:
        async with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                t.status = TaskStatus.COMPLETED
                t.result = result
                t.completed_at = datetime.now(timezone.utc).isoformat()

    async def fail(self, task_id: str, error: str) -> None:
        async with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                t.status = TaskStatus.FAILED
                t.error = error
                t.completed_at = datetime.now(timezone.utc).isoformat()

    async def cancel(self, task_id: str) -> bool:
        async with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                    t.status = TaskStatus.CANCELLED
                    return True
        return False

    async def get(self, task_id: str) -> Task | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def pending(self) -> list[Task]:
        async with self._lock:
            return [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]

    async def active(self) -> list[Task]:
        async with self._lock:
            return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]

    def __len__(self) -> int:
        return len(self._tasks)
