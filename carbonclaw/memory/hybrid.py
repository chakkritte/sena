"""Hybrid memory backend fusing keyword and semantic search."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from carbonclaw.core.base import BaseMemory
from carbonclaw.core.models import MemoryEntry

logger = structlog.get_logger(__name__)


class HybridMemory(BaseMemory):
    """Combines a primary (e.g., SQLite) and secondary (e.g., ChromaDB) memory."""

    def __init__(self, primary: BaseMemory, secondary: BaseMemory | None = None) -> None:
        self.primary = primary
        self.secondary = secondary

    async def store(
        self,
        content: str,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        # Store in primary
        primary_id = await self.primary.store(content, namespace, metadata)
        
        # Store in secondary if available
        if self.secondary:
            try:
                sec_meta = dict(metadata or {})
                sec_meta["primary_id"] = primary_id
                await self.secondary.store(content, namespace, sec_meta)
            except Exception as e:
                logger.warning("memory.hybrid.secondary_store_failed", error=str(e))
                
        return primary_id

    async def retrieve(
        self,
        query: str,
        namespace: str = "default",
        limit: int = 5,
    ) -> list[MemoryEntry]:
        if not self.secondary:
            return await self.primary.retrieve(query, namespace, limit)

        # Retrieve from both concurrently
        try:
            primary_results, secondary_results = await asyncio.gather(
                self.primary.retrieve(query, namespace, limit * 2),
                self.secondary.retrieve(query, namespace, limit * 2),
                return_exceptions=True
            )
        except Exception as e:
            logger.error("memory.hybrid.retrieve_failed", error=str(e))
            return await self.primary.retrieve(query, namespace, limit)

        p_res = primary_results if not isinstance(primary_results, Exception) else []
        s_res = secondary_results if not isinstance(secondary_results, Exception) else []

        # Reciprocal Rank Fusion (RRF) scoring
        k = 60
        scores: dict[str, float] = {}
        entries: dict[str, MemoryEntry] = {}

        for rank, entry in enumerate(p_res):
            key = entry.content  # deduplicate by content
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            entries[key] = entry

        for rank, entry in enumerate(s_res):
            key = entry.content
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            entries[key] = entry

        # Sort by combined RRF score
        sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        # Return top N
        return [entries[key] for key in sorted_keys[:limit]]

    async def get(self, entry_id: str) -> MemoryEntry | None:
        return await self.primary.get(entry_id)

    async def delete(self, entry_id: str) -> bool:
        # Proper deletion from secondary would require a reverse mapping lookup, 
        # but for simplicity we only delete from primary which acts as the source of truth.
        return await self.primary.delete(entry_id)

    async def namespaces(self) -> list[str]:
        return await self.primary.namespaces()
