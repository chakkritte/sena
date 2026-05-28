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

    def analyze_git_churn(self, filepath: str | Path) -> dict[str, Any]:
        """Query Git history for churn, modification frequency, and authors to calculate refactor risk."""
        import subprocess
        path = Path(filepath)
        if not path.exists():
            return {"error": "File does not exist."}

        try:
            # 1. Get commit count (frequency of change)
            commits_res = subprocess.run(
                ["git", "log", "--follow", "--format=%H", "--", str(path)],
                capture_output=True, text=True, check=True
            )
            commit_hashes = [h.strip() for h in commits_res.stdout.splitlines() if h.strip()]
            commit_count = len(commit_hashes)

            # 2. Get author count (contributor count)
            authors_res = subprocess.run(
                ["git", "log", "--follow", "--format=%an", "--", str(path)],
                capture_output=True, text=True, check=True
            )
            authors = set(a.strip() for a in authors_res.stdout.splitlines() if a.strip())
            author_count = len(authors)

            # 3. Get lines added/deleted (lines of code churn)
            lines_res = subprocess.run(
                ["git", "log", "--follow", "--numstat", "--format=", "--", str(path)],
                capture_output=True, text=True, check=True
            )
            lines_added = 0
            lines_deleted = 0
            for line in lines_res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        lines_added += int(parts[0])
                        lines_deleted += int(parts[1])
                    except ValueError:
                        pass # Handles binary or '-' fields

            # Calculate risk score
            # A simple heuristic risk score (0 to 100):
            # risk = (commits * 1.2) + (authors * 2.5) + ((lines_added + lines_deleted) * 0.02)
            # Capped at 100.
            complexity_factor = 1.0
            ast_data = self.graph.get(str(path))
            if ast_data:
                # Highly complex code structures (many functions/classes) scale up the risk
                ast_elements = len(ast_data.get("classes", [])) + len(ast_data.get("functions", []))
                if ast_elements > 10:
                    complexity_factor = 1.3
                elif ast_elements > 20:
                    complexity_factor = 1.6

            base_risk = (commit_count * 1.2) + (author_count * 2.5) + ((lines_added + lines_deleted) * 0.02)
            risk_score = min(100.0, base_risk * complexity_factor)

            # Get hot spots or blast radius: other files that import symbols from this file
            blast_radius = []
            if ast_data:
                symbols = ast_data.get("classes", []) + ast_data.get("functions", [])
                for other_path, other_data in self.graph.items():
                    if other_path == str(path):
                        continue
                    for sym in symbols:
                        if sym in other_data.get("imports", []):
                            blast_radius.append(other_path)
                            break

            return {
                "filepath": str(path),
                "commits_count": commit_count,
                "author_count": author_count,
                "lines_added": lines_added,
                "lines_deleted": lines_deleted,
                "risk_score": round(risk_score, 2),
                "blast_radius": list(set(blast_radius)),
            }
        except Exception as e:
            return {"error": f"Failed to retrieve git history: {e}"}

    async def delete(self, entry_id: str) -> bool:
        if entry_id in self.graph:
            del self.graph[entry_id]
            self._save()
            return True
        return False

    async def namespaces(self) -> list[str]:
        return ["graph"]
