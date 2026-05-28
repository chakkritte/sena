"""SQLite-backed persistent memory."""

from __future__ import annotations

import orjson
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from carbonclaw.core.base import BaseMemory
from carbonclaw.core.models import MemoryEntry

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

-- Full-text search table
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    content,
    content='entries',
    content_rowid='rowid'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
  INSERT INTO entries_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
  INSERT INTO entries_fts(entries_fts, rowid, content) VALUES('delete', old.rowid, old.content);
END;
CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
  INSERT INTO entries_fts(entries_fts, rowid, content) VALUES('delete', old.rowid, old.content);
  INSERT INTO entries_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""


class SQLiteMemory(BaseMemory):
    """Async SQLite memory backend with FTS5 support."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from carbonclaw.config.settings import CarbonClawConfig
            db_path = CarbonClawConfig.user_dir() / "memory.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def _init(self) -> None:
        if self._initialized:
            return
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.execute("PRAGMA synchronous=NORMAL;")
                await db.executescript(SCHEMA)
                await db.commit()
            self._initialized = True
        except Exception as e:
            logger.error("memory.sqlite.init_failed", error=str(e))
            # If corrupted, try to move and start fresh in production? 
            # For now just raise to prevent silent failure
            raise RuntimeError(f"Failed to initialize SQLite memory: {e}") from e

    async def store(
        self,
        content: str,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        await self._init()
        entry_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO entries (id, namespace, content, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        entry_id,
                        namespace,
                        content,
                        orjson.dumps(metadata or {}).decode("utf-8"),
                        now,
                        now,
                    ),
                )
                await db.commit()
            return entry_id
        except Exception as e:
            logger.exception("memory.sqlite.store_failed")
            raise

    async def retrieve(
        self,
        query: str,
        namespace: str = "default",
        limit: int = 5,
    ) -> list[MemoryEntry]:
        """Retrieve relevant memories using Full-Text Search or simple pattern match."""
        await self._init()
        
        # If query is empty, just return latest
        if not query:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, namespace, content, metadata, created_at FROM entries WHERE namespace = ? ORDER BY created_at DESC LIMIT ?",
                    (namespace, limit),
                ) as cursor:
                    rows = await cursor.fetchall()
            return [self._row_to_entry(r) for r in rows]

        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                # Use FTS5 for efficient searching
                sql = """
                SELECT e.id, e.namespace, e.content, e.metadata, e.created_at
                FROM entries e
                JOIN entries_fts f ON e.rowid = f.rowid
                WHERE e.namespace = ? AND f.content MATCH ?
                ORDER BY rank
                LIMIT ?
                """
                async with db.execute(sql, (namespace, query, limit)) as cursor:
                    rows = await cursor.fetchall()
                
                # Fallback to simple LIKE if FTS returns nothing or for complex queries
                if not rows:
                    pattern = f"%{query}%"
                    async with db.execute(
                        "SELECT id, namespace, content, metadata, created_at FROM entries WHERE namespace = ? AND content LIKE ? ORDER BY created_at DESC LIMIT ?",
                        (namespace, pattern, limit),
                    ) as cursor:
                        rows = await cursor.fetchall()
                        
            return [self._row_to_entry(r) for r in rows]
        except Exception as e:
            logger.warning("memory.sqlite.retrieve_failed", error=str(e))
            return []

    def _row_to_entry(self, row: aiosqlite.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            namespace=row["namespace"],
            content=row["content"],
            metadata=orjson.loads(row["metadata"] or "{}"),
            created_at=row["created_at"],
        )

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
            metadata=orjson.loads(row["metadata"]),
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
