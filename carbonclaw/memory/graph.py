"""AST-based Knowledge Graph Memory for deep repository awareness."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import structlog

from carbonclaw.core.base import BaseMemory
from carbonclaw.core.models import MemoryEntry

logger = structlog.get_logger(__name__)


class KnowledgeGraphMemory(BaseMemory):
    """Memory backend that maintains a graph of code dependencies."""

    def __init__(self, db_path: Path | None = None) -> None:
        from carbonclaw.config.settings import CarbonClawConfig
        self.db_path = db_path or CarbonClawConfig.user_dir() / "graph.json"
        self.graph: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if self.db_path.exists():
            try:
                return json.loads(self.db_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.write_text(json.dumps(self.graph, indent=2), encoding="utf-8")

    def analyze_file(self, filepath: str | Path) -> None:
        """Parse a Python file and extract its AST structure into the graph."""
        path = Path(filepath)
        if not path.exists() or not path.suffix == ".py":
            return

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            logger.warning("graph.parse_error", file=str(path))
            return

        node_data: dict[str, Any] = {
            "classes": [],
            "functions": [],
            "imports": [],
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                node_data["classes"].append(node.name)
            elif isinstance(node, ast.FunctionDef):
                node_data["functions"].append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    node_data["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    node_data["imports"].append(node.module)

        self.graph[str(path)] = node_data
        self._save()
        logger.info("graph.analyzed", file=str(path), classes=len(node_data["classes"]))

    async def store(
        self,
        content: str,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store acts as analyze_file if content is a filepath for the graph namespace."""
        if namespace == "graph":
            self.analyze_file(content)
            return content
        return "not_supported"

    async def retrieve(
        self,
        query: str,
        namespace: str = "default",
        limit: int = 5,
    ) -> list[MemoryEntry]:
        """Query the graph for structural dependencies."""
        if namespace != "graph":
            return []

        results = []
        for path, data in self.graph.items():
            if query in data.get("classes", []) or query in data.get("functions", []):
                results.append(
                    MemoryEntry(
                        id=path,
                        namespace="graph",
                        content=f"Symbol '{query}' is defined in {path}.\nDependencies: {data.get('imports', [])}",
                        metadata=data
                    )
                )
            elif query in data.get("imports", []):
                results.append(
                    MemoryEntry(
                        id=path,
                        namespace="graph",
                        content=f"File '{path}' imports '{query}'.",
                        metadata=data
                    )
                )

        return results[:limit]

    async def get(self, entry_id: str) -> MemoryEntry | None:
        data = self.graph.get(entry_id)
        if data:
            return MemoryEntry(id=entry_id, namespace="graph", content=str(data), metadata=data)
        return None

    async def delete(self, entry_id: str) -> bool:
        if entry_id in self.graph:
            del self.graph[entry_id]
            self._save()
            return True
        return False

    async def namespaces(self) -> list[str]:
        return ["graph"]
