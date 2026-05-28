"""Daemon mode for the autonomous Self-Healing CI and lint checker."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from carbonclaw.agents.supervisor import SupervisorAgent
from carbonclaw.tools.shell import ShellTool

logger = structlog.get_logger(__name__)


class HealerDaemon:
    """Monitors repository files for modifications and auto-heals linting/type check errors on save."""

    def __init__(
        self,
        supervisor: SupervisorAgent,
        watch_path: Path | None = None,
        check_command: str = "uv run ruff check",
    ) -> None:
        """Initialize the healer daemon."""
        self.supervisor = supervisor
        self.watch_path = watch_path or Path(".")
        self.check_command = check_command
        self._file_mtimes: dict[Path, float] = {}
        self._running = False

    def _scan_files(self) -> dict[Path, float]:
        """Scan Python files and return a map of filepath to modification times."""
        mtimes: dict[Path, float] = {}
        for path in self.watch_path.glob("**/*.py"):
            # Ignore hidden files, venv, and cache
            if any(part.startswith(".") or part == "venv" or part == ".venv" or part == "__pycache__" for part in path.parts):
                continue
            try:
                mtimes[path] = path.stat().st_mtime
            except FileNotFoundError:
                continue
        return mtimes

    async def start(self, poll_interval: float = 1.0) -> None:
        """Start the file monitoring daemon loop."""
        self._running = True
        logger.info("healer.daemon.starting", watch_path=str(self.watch_path), cmd=self.check_command)

        # Populate initial mtimes
        self._file_mtimes = self._scan_files()

        shell = ShellTool()
        shell._sandbox_override = False

        while self._running:
            try:
                await asyncio.sleep(poll_interval)
                current_mtimes = self._scan_files()

                # Check for modified or new files
                for filepath, mtime in current_mtimes.items():
                    prev_mtime = self._file_mtimes.get(filepath)
                    if prev_mtime is not None and mtime > prev_mtime:
                        logger.info("healer.daemon.file_changed", file=str(filepath))
                        await self._heal_file(filepath, shell)

                self._file_mtimes = current_mtimes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("healer.daemon.error", error=str(e))

    def stop(self) -> None:
        """Stop the daemon loop."""
        self._running = False
        logger.info("healer.daemon.stopped")

    async def _heal_file(self, filepath: Path, shell: ShellTool) -> None:
        """Run the checker on a file and trigger autonomous healing if it fails."""
        # Execute check command for the specific file
        cmd = f"{self.check_command} {filepath}"
        result = await shell.execute({"command": cmd})

        if not result.is_error:
            logger.info("healer.daemon.file_passed", file=str(filepath))
            return

        logger.warning("healer.daemon.file_failed", file=str(filepath), errors=result.content[:150])

        fix_prompt = (
            f"The file '{filepath}' failed the lint/type checks run via command: '{cmd}'.\n"
            f"The error output was:\n\n"
            f"```\n{result.content}\n```\n\n"
            f"Please analyze the errors and modify '{filepath}' to fix them perfectly."
        )

        logger.info("healer.daemon.healing_start", file=str(filepath))
        # Delegate to coding swarm debate to solve the lint errors
        await self.supervisor.swarm_debate(fix_prompt)
        logger.info("healer.daemon.healing_complete", file=str(filepath))
