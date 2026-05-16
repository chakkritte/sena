"""SQLite-backed persistent memory."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from sena.core.base import BaseMemory
from sena.core.models import MemoryEntry

logger = structlog.get_logger()

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_namespace ON entries(namespace);
CREATE INDEX IF NOT EXISTS idx_created ON entries(created_at);
"""


class SQLiteMemory(BaseMemory):
    """Async SQLite memory backend with namespace support."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from sena.config.settings import SenaConfig
            db_path = SenaConfig.user_dir() / "memory.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def _init(self) -> None:
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()
        self._initialized = True

    async def store(
        self,
        content: str,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        await self._init()
        entry_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO entries (id, namespace, content, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    entry_id,
                    namespace,
                    content,
                    json.dumps(metadata or {}),
                    now,
                    now,
                ),
            )
            await db.commit()
        return entry_id

    async def retrieve(
        self,
        query: str,
        namespace: str = "default",
        limit: int = 5,
    ) -> list[MemoryEntry]:
        await self._init()
        pattern = f"%{query}%"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, namespace, content, metadata, created_at FROM entries WHERE namespace = ? AND content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (namespace, pattern, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            MemoryEntry(
                id=r["id"],
                namespace=r["namespace"],
                content=r["content"],
                metadata=json.loads(r["metadata"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def get(self, entry_id: str) -> MemoryEntry | None:
        await self._init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, namespace, content, metadata, created_at FROM entries WHERE id = ?",
                (entry_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return MemoryEntry(
            id=row["id"],
            namespace=row["namespace"],
            content=row["content"],
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
        )

    async def delete(self, entry_id: str) -> bool:
        await self._init()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def namespaces(self) -> list[str]:
        await self._init()
        async with aiosqlite.connect(self.db_path) as db, db.execute(
            "SELECT DISTINCT namespace FROM entries ORDER BY namespace"
        ) as cursor:
            rows = await cursor.fetchall()
        return [r[0] for r in rows]
