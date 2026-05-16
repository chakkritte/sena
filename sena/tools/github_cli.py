"""GitHub integration tool using the gh CLI."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sena.core.base import BaseTool
from sena.core.models import ToolResult


_GH_WHITELIST = frozenset(
    [
        "pr",
        "issue",
        "repo",
        "release",
        "workflow",
        "run",
        "status",
        "api",
        "search",
        "view",
        "list",
        "create",
        "close",
        "merge",
        "review",
        "comment",
        "checkout",
    ]
)


class GitHubTool(BaseTool):
    """Interact with GitHub via the ``gh`` CLI."""

    name = "github"
    description = (
        "Run whitelisted gh (GitHub CLI) commands for PRs, issues, "
        "releases, workflows, and repository operations."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The gh subcommand to run (e.g. 'pr list', 'issue view 42').",
            },
            "json": {
                "type": "boolean",
                "description": "Request JSON output when available.",
                "default": True,
            },
        },
        "required": ["command"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        command = arguments.get("command", "").strip()
        use_json = arguments.get("json", True)

        if not command:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content="No command provided.",
                is_error=True,
            )

        sub = command.split()[0].lower()
        if sub not in _GH_WHITELIST:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Disallowed gh subcommand: '{sub}'. Allowed: {', '.join(sorted(_GH_WHITELIST))}",
                is_error=True,
            )

        cmd_parts = ["gh"] + command.split()
        if use_json and sub in ("pr", "issue", "repo", "release", "run", "workflow"):
            # Only add --json if the subcommand supports it and user didn't already include it
            if "--json" not in command:
                cmd_parts.append("--json")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content="GitHub command timed out after 30 seconds.",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"GitHub tool error: {e}",
                is_error=True,
            )
