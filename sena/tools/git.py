"""Git-aware tool for repository introspection."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from sena.core.base import BaseTool
from sena.core.models import ToolResult

logger = structlog.get_logger()


class GitTool(BaseTool):
    """Execute git commands and return structured output."""

    name = "git"
    description = (
        "Run git commands in a repository. Supported subcommands: status, diff, "
        "log, branch, show, ls-files. Returns stdout/stderr."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "Git subcommand and arguments, e.g. 'status', 'diff HEAD~1', "
                    "'log --oneline -10'. Do not include 'git' prefix."
                ),
            },
            "cwd": {
                "type": "string",
                "description": "Repository path. Defaults to current directory.",
                "default": "",
            },
        },
        "required": ["command"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        command = arguments.get("command", "")
        cwd = arguments.get("cwd") or "."
        full_command = f"git {command}"

        allowed_prefixes = (
            "git status",
            "git diff",
            "git log",
            "git branch",
            "git show",
            "git ls-files",
            "git rev-parse",
            "git remote",
            "git config",
        )
        if not any(full_command.startswith(p) for p in allowed_prefixes):
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Git command '{command}' is not in the allowed set.",
                is_error=True,
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                full_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            output = stdout
            if stderr:
                output += f"\n\n[stderr]\n{stderr}"
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=output,
                is_error=proc.returncode != 0,
            )
        except TimeoutError:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content="Git command timed out after 30 seconds.",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Git error: {e}",
                is_error=True,
            )

    @staticmethod
    async def summarize_repo(cwd: str = ".") -> str:
        """Generate a concise summary of the current repository state."""
        commands = [
            "git status --short",
            "git log --oneline -5",
            "git branch --show-current",
        ]
        parts: list[str] = []
        for cmd in commands:
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )
                stdout, _ = await proc.communicate()
                if stdout.strip():
                    parts.append(f"$ {cmd}\n{stdout.decode('utf-8', errors='replace')}")
            except Exception:
                pass
        return "\n\n".join(parts) if parts else "Not a git repository or no commits."
