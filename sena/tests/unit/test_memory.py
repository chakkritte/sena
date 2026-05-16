"""Unit tests for SQLite memory backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from sena.memory.sqlite import SQLiteMemory


@pytest.mark.asyncio
async def test_memory_store_retrieve(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    mem = SQLiteMemory(str(db))

    id1 = await mem.store("hello world", namespace="test")
    id2 = await mem.store("foo bar", namespace="test")

    results = await mem.retrieve("hello", namespace="test", limit=5)
    assert len(results) >= 1
    assert any("hello world" in r.content for r in results)

    entry = await mem.get(id1)
    assert entry is not None
    assert entry.content == "hello world"

    ok = await mem.delete(id1)
    assert ok
    assert await mem.get(id1) is None

    ns = await mem.namespaces()
    assert "test" in ns
