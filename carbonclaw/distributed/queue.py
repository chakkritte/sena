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


import aiosqlite
import json
from pathlib import Path

class TaskQueue:
    """Async priority task queue with worker pool support and SQLite persistence."""

    def __init__(self, db_path: str | Path | None = None, maxsize: int = 0) -> None:
        if db_path is None:
            from carbonclaw.config.settings import CarbonClawConfig
            db_path = CarbonClawConfig.user_dir() / "tasks.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._queue: asyncio.PriorityQueue[tuple[int, str, Task]] = asyncio.PriorityQueue(
            maxsize=maxsize
        )
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._event = asyncio.Event()
        self._initialized = False

    async def _init(self) -> None:
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    agent_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    priority INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    result TEXT,
                    error TEXT,
                    assignee TEXT
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)")
            await db.commit()
            
            # Restore pending tasks into in-memory queue
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tasks WHERE status = 'pending'") as cursor:
                async for row in cursor:
                    task = Task(
                        id=row["id"],
                        agent_type=row["agent_type"],
                        payload=json.loads(row["payload"]),
                        priority=row["priority"],
                        status=TaskStatus(row["status"]),
                        created_at=row["created_at"]
                    )
                    self._tasks[task.id] = task
                    await self._queue.put((-task.priority, task.id, task))
                    
        self._initialized = True

    async def submit(self, task: Task) -> None:
        await self._init()
        async with self._lock:
            self._tasks[task.id] = task
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO tasks (id, agent_type, payload, priority, created_at, status) VALUES (?, ?, ?, ?, ?, ?)",
                    (task.id, task.agent_type, json.dumps(task.payload), task.priority, task.created_at, task.status.value),
                )
                await db.commit()
        await self._queue.put((-task.priority, task.id, task))
        self._event.set()

    async def next_task(self, timeout: float | None = None) -> Task | None:
        """Get the highest-priority pending task and mark it running in DB."""
        await self._init()
        try:
            _, _, task = await asyncio.wait_for(
                self._queue.get(), timeout=timeout
            )
            async with self._lock:
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now(timezone.utc).isoformat()
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "UPDATE tasks SET status = ?, started_at = ? WHERE id = ?",
                        (task.status.value, task.started_at, task.id),
                    )
                    await db.commit()
            return task
        except asyncio.TimeoutError:
            return None

    async def complete(self, task_id: str, result: Any) -> None:
        await self._init()
        async with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                t.status = TaskStatus.COMPLETED
                t.result = result
                t.completed_at = datetime.now(timezone.utc).isoformat()
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?",
                        (t.status.value, json.dumps(result), t.completed_at, task_id),
                    )
                    await db.commit()

    async def fail(self, task_id: str, error: str) -> None:
        await self._init()
        async with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                t.status = TaskStatus.FAILED
                t.error = error
                t.completed_at = datetime.now(timezone.utc).isoformat()
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "UPDATE tasks SET status = ?, error = ?, completed_at = ? WHERE id = ?",
                        (t.status.value, error, t.completed_at, task_id),
                    )
                    await db.commit()

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
