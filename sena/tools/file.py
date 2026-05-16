"""File read, write, and patch tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from sena.core.base import BaseTool
from sena.core.models import ToolResult

logger = structlog.get_logger()


class FileReadTool(BaseTool):
    """Read file contents with optional line range."""

    name = "file_read"
    description = (
        "Read the contents of a file. Optionally specify an offset and limit "
        "to read a specific range of lines."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file.",
            },
            "offset": {
                "type": "integer",
                "description": "1-based starting line number.",
                "default": 1,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read.",
                "default": 200,
            },
        },
        "required": ["path"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path_str = arguments.get("path", "")
        offset = max(1, arguments.get("offset", 1))
        limit = arguments.get("limit", 200)
        path = Path(path_str).expanduser().resolve()

        try:
            if not path.exists():
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=f"File not found: {path}",
                    is_error=True,
                )
            with path.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            start = offset - 1
            end = start + limit
            selected = lines[start:end]
            # Add line numbers for context
            numbered = ""
            for i, line in enumerate(selected, start=offset):
                numbered += f"{i:4d} {line}"
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=numbered,
                is_error=False,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Error reading {path}: {e}",
                is_error=True,
            )


class FileWriteTool(BaseTool):
    """Write or overwrite a file."""

    name = "file_write"
    description = (
        "Write content to a file. Creates parent directories if needed. "
        "WARNING: this overwrites existing files."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file.",
            },
            "content": {
                "type": "string",
                "description": "Full content to write.",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path_str = arguments.get("path", "")
        content = arguments.get("content", "")
        path = Path(path_str).expanduser().resolve()

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Wrote {len(content)} characters to {path}",
                is_error=False,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Error writing {path}: {e}",
                is_error=True,
            )


class FilePatchTool(BaseTool):
    """Apply a unified diff patch to a file."""

    name = "file_patch"
    requires_approval = True
    description = (
        "Apply a unified diff patch to a file. The patch should be in standard "
        "unified diff format. If the patch fails, the original file is preserved."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to patch.",
            },
            "diff": {
                "type": "string",
                "description": "Unified diff to apply.",
            },
        },
        "required": ["path", "diff"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path_str = arguments.get("path", "")
        diff_text = arguments.get("diff", "")
        path = Path(path_str).expanduser().resolve()

        try:
            if not path.exists():
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=f"File not found: {path}",
                    is_error=True,
                )
            with path.open("r", encoding="utf-8", errors="replace") as f:
                original = f.read()
            new_content = self._apply_simple_diff(original, diff_text)
            with path.open("w", encoding="utf-8") as f:
                f.write(new_content)
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Patched {path} successfully.",
                is_error=False,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Patch failed for {path}: {e}",
                is_error=True,
            )

    @staticmethod
    def _apply_simple_diff(original: str, diff_text: str) -> str:
        """Naive unified diff applicator for single-file patches."""
        original_lines = original.splitlines(keepends=True)
        diff_lines = diff_text.splitlines(keepends=True)
        result: list[str] = []
        in_hunk = False
        orig_idx = 0
        for line in diff_lines:
            if line.startswith("---") or line.startswith("+++"):
                continue
            if line.startswith("@@"):
                in_hunk = True
                parts = line.split()
                old_range = parts[1]
                start = old_range.split(",")[0][1:]
                target_line = int(start) - 1
                result = original_lines[:target_line]
                orig_idx = target_line
                continue
            if not in_hunk:
                continue
            if line.startswith(" "):
                result.append(line[1:])
                orig_idx += 1
            elif line.startswith("-"):
                orig_idx += 1
            elif line.startswith("+"):
                result.append(line[1:])
        # Append remaining original lines after hunk
        result.extend(original_lines[orig_idx:])
        return "".join(result)
