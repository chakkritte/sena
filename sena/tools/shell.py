"""Shell command execution tool with safety controls."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from sena.core.base import BaseTool
from sena.core.models import ToolResult

logger = structlog.get_logger()

# Commands and patterns considered dangerous without explicit approval
_DANGEROUS_PATTERNS = (
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=/dev/zero",
    "> /dev/sda",
    ":(){ :|:& };:",
    "chmod -R 000 /",
    "chown -R root /",
    "mkfs.ext",
    "mkfs.btrfs",
    "mkfs.xfs",
    "fdisk",
    "parted",
    " shred ",
)

_DANGEROUS_PREFIXES = (
    "rm -rf /",
    "mkfs",
    "dd if=",
    "chmod -R 000",
    ":(){",
)

_DANGEROUS_SUBSTRINGS = (
    "curl", "wget", "fetch",
)
_DANGEROUS_PIPES = ("| bash", "| sh", "| zsh", "|python", "| python")


class ShellTool(BaseTool):
    """Execute shell commands securely with timeout support."""

    name = "shell"
    requires_approval = True
    description = (
        "Execute a shell command and return stdout/stderr. "
        "Supports piping, redirection, and standard shell syntax. "
        "Commands run in the current working directory unless cwd is specified."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum seconds to wait for completion.",
                "default": 60,
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the command.",
                "default": "",
            },
        },
        "required": ["command"],
    }

    @staticmethod
    def is_dangerous(command: str) -> bool:
        """Heuristic check for potentially destructive commands."""
        stripped = command.strip().lower()
        if any(pattern.lower() in stripped for pattern in _DANGEROUS_PATTERNS):
            return True
        if any(stripped.startswith(prefix.lower()) for prefix in _DANGEROUS_PREFIXES):
            return True
        # Detect pipe-to-shell patterns: curl ... | bash, wget ... | sh, etc.
        for pipe in _DANGEROUS_PIPES:
            if pipe in stripped:
                return True
        return False

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        command = arguments.get("command", "")
        timeout = arguments.get("timeout", 60)
        cwd = arguments.get("cwd") or None

        if not command:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content="No command provided.",
                is_error=True,
            )

        logger.info("shell.execute", command=command[:80], cwd=cwd)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
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
                content=f"Command timed out after {timeout} seconds.",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Execution error: {e}",
                is_error=True,
            )
