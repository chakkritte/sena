"""File search tools for discovering content by name or text."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from sena.core.base import BaseTool
from sena.core.models import ToolResult


class FileSearchTool(BaseTool):
    """Search for files by name pattern or content regex."""

    name = "file_search"
    description = (
        "Search for files matching a name glob or containing text. "
        "Returns a list of matching file paths with optional line numbers."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Text to search for (treated as regex in content mode).",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: current directory).",
                "default": ".",
            },
            "mode": {
                "type": "string",
                "enum": ["name", "content"],
                "description": "Search by filename glob or file content.",
                "default": "name",
            },
            "glob": {
                "type": "string",
                "description": "Filename glob pattern (e.g. '*.py'). Used in name mode.",
                "default": "*",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return.",
                "default": 20,
            },
        },
        "required": ["query"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        query = arguments.get("query", "")
        search_path = arguments.get("path", ".")
        mode = arguments.get("mode", "name")
        glob = arguments.get("glob", "*")
        max_results = arguments.get("max_results", 20)

        if not query:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content="No query provided.",
                is_error=True,
            )

        base = Path(search_path).expanduser().resolve()
        if not base.exists():
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Path not found: {base}",
                is_error=True,
            )

        results: list[str] = []
        try:
            if mode == "name":
                results = self._search_by_name(base, query, glob, max_results)
            else:
                results = self._search_by_content(base, query, glob, max_results)
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Search error: {e}",
                is_error=True,
            )

        if not results:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content="No matches found.",
                is_error=False,
            )

        output = f"Found {len(results)} result(s):\n" + "\n".join(results)
        return ToolResult(
            tool_call_id="",
            name=self.name,
            content=output,
            is_error=False,
        )

    @staticmethod
    def _search_by_name(
        base: Path, query: str, glob: str, max_results: int
    ) -> list[str]:
        """Search for files whose names match the query (fnmatch)."""
        results: list[str] = []
        pattern = f"*{query}*" if "*" not in query else query
        for path in base.rglob(glob):
            if fnmatch.fnmatch(path.name.lower(), pattern.lower()):
                results.append(str(path.relative_to(base) if path.is_relative_to(base) else path))
                if len(results) >= max_results:
                    break
        return results

    @staticmethod
    def _search_by_content(
        base: Path, query: str, glob: str, max_results: int
    ) -> list[str]:
        """Search for files containing the query text."""
        results: list[str] = []
        try:
            regex = re.compile(query, re.IGNORECASE)
        except re.error as e:
            return [f"Invalid regex: {e}"]

        for path in base.rglob(glob):
            if not path.is_file():
                continue
            # Skip binary files by checking for null bytes in first 8KB
            try:
                data = path.read_bytes()[:8192]
                if b"\x00" in data:
                    continue
                text = data.decode("utf-8", errors="replace")
                for i, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        rel = path.relative_to(base) if path.is_relative_to(base) else path
                        results.append(f"{rel}:{i}: {line.strip()[:120]}")
                        if len(results) >= max_results:
                            return results
                        break  # one match per file for brevity
            except (OSError, UnicodeDecodeError):
                continue
        return results