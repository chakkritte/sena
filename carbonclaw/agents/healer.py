"""Autonomous Self-Healing CI Daemon."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from carbonclaw.agents.supervisor import SupervisorAgent
from carbonclaw.core.base import BaseProvider, BaseMemory
from carbonclaw.tools.shell import ShellTool

logger = structlog.get_logger(__name__)

class HealerAgent:
    """Watches a command (like pytest) and autonomously fixes failures."""

    def __init__(
        self,
        supervisor: SupervisorAgent,
        test_command: str = "uv run pytest",
    ) -> None:
        self.supervisor = supervisor
        self.test_command = test_command

    async def heal_loop(self, max_attempts: int = 3) -> bool:
        """Run tests and try to fix them if they fail."""
        shell = ShellTool()

        for attempt in range(1, max_attempts + 1):
            logger.info("healer.run_tests", attempt=attempt)
            
            # For automation, disable sandbox override explicitly or trust local
            setattr(shell, "_sandbox_override", False)
            result = await shell.execute({"command": self.test_command})

            if not result.is_error:
                logger.info("healer.tests_passed")
                return True

            logger.warning("healer.tests_failed", error=result.content[:200])
            
            # Construct fix prompt
            fix_task = (
                f"The test suite failed with the following output:\n\n"
                f"```\n{result.content}\n```\n\n"
                "Please analyze the failure, find the relevant code files, and apply a fix."
            )

            logger.info("healer.fixing", attempt=attempt)
            # Use swarm debate for a robust fix
            await self.supervisor.swarm_debate(fix_task)

        logger.error("healer.failed", attempts=max_attempts)
        return False
