"""Carbon-Aware Task Scheduler and Queue for CarbonClaw."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Any, Literal

from platformdirs import user_data_dir
from pydantic import BaseModel, Field

from carbonclaw.telemetry.grid import estimate_carbon_savings


class ScheduledTask(BaseModel):
    """A task queued for execution at a carbon-efficient time."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    command: str
    mode: str = "code"
    scheduled_at: str
    carbon_savings_grams: float
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    emissions_kg: float = 0.0
    created_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat()
    )


class SchedulerStore:
    """Persistent store for scheduled tasks."""

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the scheduler store."""
        if path is None:
            data_dir = Path(user_data_dir("carbonclaw", "carbonclaw"))
            data_dir.mkdir(parents=True, exist_ok=True)
            path = data_dir / "scheduled_tasks.jsonl"
        self._path = path

    def add_task(self, command: str, mode: str = "code") -> ScheduledTask:
        """Schedule a new task at the optimal carbon-friendly time."""
        now = datetime.datetime.now()
        scheduled_dt, savings = estimate_carbon_savings(command, now)

        task = ScheduledTask(
            command=command,
            mode=mode,
            scheduled_at=scheduled_dt.isoformat(),
            carbon_savings_grams=savings,
            status="queued"
        )

        line = task.model_dump_json()
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

        return task

    def tasks(self) -> list[ScheduledTask]:
        """Load all scheduled tasks."""
        results: list[ScheduledTask] = []
        if not self._path.exists():
            return results
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(ScheduledTask.model_validate_json(line))
                except Exception:
                    continue
        return results

    def save_tasks(self, tasks: list[ScheduledTask]) -> None:
        """Overwrite the task store with the updated task list."""
        lines = [task.model_dump_json() for task in tasks]
        with self._path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def update_task_status(
        self,
        task_id: str,
        status: Literal["queued", "running", "completed", "failed"],
        emissions_kg: float = 0.0,
    ) -> bool:
        """Update the status of a specific task."""
        all_tasks = self.tasks()
        updated = False
        for t in all_tasks:
            if t.id == task_id:
                t.status = status
                t.emissions_kg = emissions_kg
                updated = True
                break
        if updated:
            self.save_tasks(all_tasks)
        return updated


async def execute_task(task: ScheduledTask) -> float:
    """Execute a scheduled task using the agent runtime.

    Returns:
        Emitted carbon in kg CO2.
    """
    from carbonclaw.agents.coding import CodingAgent
    from carbonclaw.agents.supervisor import SupervisorAgent
    from carbonclaw.config.settings import CarbonClawConfig
    from carbonclaw.memory.sqlite import SQLiteMemory
    from carbonclaw.providers.registry import ProviderRegistry
    from carbonclaw.telemetry.carbon import track_carbon
    from carbonclaw.tools.base import ToolRegistry
    from carbonclaw.tools.browser import BrowserTool
    from carbonclaw.tools.file import FilePatchTool, FileReadTool, FileWriteTool
    from carbonclaw.tools.git import GitTool
    from carbonclaw.tools.mcp import register_mcp_tools
    from carbonclaw.tools.shell import ShellTool

    config = CarbonClawConfig()

    # Run with carbon tracking
    with track_carbon(f"scheduled_task_{task.id}") as ct:
        prov = ProviderRegistry.create(config.default_provider, config)
        mem = SQLiteMemory()

        if task.mode == "research":
            from carbonclaw.agents.research import ResearchAgent
            agent = ResearchAgent(prov, [], mem)
            await agent.research(task.command)
        elif task.mode == "swarm":
            supervisor = SupervisorAgent(prov, [], mem)
            await supervisor.swarm_debate(task.command)
        else:
            tools = ToolRegistry()
            tools.register(ShellTool())
            tools.register(BrowserTool())
            tools.register(FileReadTool())
            tools.register(FileWriteTool())
            tools.register(FilePatchTool())
            tools.register(GitTool())

            # Autoconfigure to auto-approve safe tasks in scheduling mode
            original_auto_approve = config.auto_approve_safe_commands
            config.auto_approve_safe_commands = True

            mcp_clients = await register_mcp_tools(tools, config)

            # Simple approval callback that always accepts safe commands
            # but fails dangerous ones in non-interactive batch/daemon mode
            async def non_interactive_approval(name: str, arguments: dict[str, Any]) -> bool:
                if name == "shell":
                    cmd = arguments.get("command", "")
                    if any(kw in cmd for kw in ["rm ", "mv ", "delete", "kill"]):
                        return False
                return True

            agent = CodingAgent(
                provider=prov,
                tools=tools.list_tools(),
                memory=mem,
                model=config.default_model,
                approval_callback=non_interactive_approval,
            )

            try:
                async for _ in agent.stream_run(task.command):
                    pass
            finally:
                config.auto_approve_safe_commands = original_auto_approve
                for client in mcp_clients:
                    await client.disconnect()

    return ct.last_emissions
