"""ChromaDB vector memory backend."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from sena.core.base import BaseMemory
from sena.core.models import MemoryEntry

logger = structlog.get_logger()


try:
    import chromadb  # type: ignore
    from chromadb.config import Settings as ChromaSettings  # type: ignore

    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False


class ChromaMemory(BaseMemory):
    """ChromaDB-backed vector memory with semantic retrieval."""

    def __init__(
        self,
        path: str | Path | None = None,
        collection_name: str = "sena_memory",
        embedding_function: Any | None = None,
    ) -> None:
        if not _CHROMA_AVAILABLE:
            raise ImportError(
                "ChromaDB is not installed. Install with: uv add chromadb"
            )

        if path is None:
            from sena.config.settings import SenaConfig
            path = SenaConfig.user_dir() / "chroma"

        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self._ef = embedding_function

        self.client = chromadb.PersistentClient(
            path=str(self.path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    async def store(
        self,
        content: str,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        entry_id = uuid.uuid4().hex
        meta = dict(metadata or {})
        meta["namespace"] = namespace
        meta["created_at"] = datetime.now(timezone.utc).isoformat()

        self._collection.add(
            ids=[entry_id],
            documents=[content],
            metadatas=[meta],
        )
        return entry_id

    async def retrieve(
        self,
        query: str,
        namespace: str = "default",
        limit: int = 5,
    ) -> list[MemoryEntry]:
        results = self._collection.query(
            query_texts=[query],
            n_results=limit,
            where={"namespace": namespace},
        )
        entries: list[MemoryEntry] = []
        if not results["ids"] or not results["ids"][0]:
            return entries

        for i, entry_id in enumerate(results["ids"][0]):
            score = results["distances"][0][i] if results["distances"] else None
            doc = results["documents"][0][i] if results["documents"] else ""
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            entries.append(
                MemoryEntry(
                    id=entry_id,
                    namespace=namespace,
                    content=doc,
                    metadata={k: v for k, v in (meta or {}).items() if k != "namespace"},
                    created_at=meta.get("created_at") if meta else None,
                    score=score,
                )
            )
        return entries

    async def get(self, entry_id: str) -> MemoryEntry | None:
        try:
            result = self._collection.get(ids=[entry_id])
            if not result["ids"]:
                return None
            meta = result["metadatas"][0] if result["metadatas"] else {}
            return MemoryEntry(
                id=entry_id,
                namespace=meta.get("namespace", "default") if meta else "default",
                content=result["documents"][0] if result["documents"] else "",
                metadata={k: v for k, v in (meta or {}).items() if k not in ("namespace", "created_at")},
                created_at=meta.get("created_at") if meta else None,
            )
        except Exception:
            return None

    async def delete(self, entry_id: str) -> bool:
        try:
            self._collection.delete(ids=[entry_id])
            return True
        except Exception:
            return False

    async def namespaces(self) -> list[str]:
        # ChromaDB does not have a distinct namespace API; we track via metadata
        all_meta = self._collection.get(include=["metadatas"])
        ns_set: set[str] = set()
        for meta in all_meta.get("metadatas", []) or []:
            if meta:
                ns_set.add(meta.get("namespace", "default"))
        return sorted(ns_set)
