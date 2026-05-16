"""Planning command."""

from __future__ import annotations

import asyncio

import typer
from rich.markdown import Markdown

from sena.agents.planner import PlannerAgent
from sena.cli.main import app, console
from sena.config.settings import SenaConfig
from sena.memory.sqlite import SQLiteMemory
from sena.providers.registry import ProviderRegistry
from sena.tools.base import ToolRegistry
from sena.tools.file import FileReadTool
from sena.tools.git import GitTool
from sena.tools.shell import ShellTool


@app.command()
def plan(
    task: str = typer.Argument(..., help="Task to plan."),
    provider: str | None = typer.Option(None, "--provider", "-p"),
    model: str | None = typer.Option(None, "--model", "-m"),
) -> None:
    """Generate a step-by-step plan for a task."""
    config = SenaConfig()
    provider_name = provider or config.default_provider
    model = model or config.default_model or "llama3.2"

    async def _execute() -> None:
        prov = ProviderRegistry.create(provider_name, config)
        mem = SQLiteMemory()
        tools = ToolRegistry()
        tools.register(ShellTool())
        tools.register(FileReadTool())
        tools.register(GitTool())

        agent = PlannerAgent(
            provider=prov,
            tools=tools.list_tools(),
            memory=mem,
            model=model,
        )

        console.print(f"[bold green]Planning:[/bold green] {task}\n")
        result = await agent.run(task)
        console.print(Markdown(result))

    asyncio.run(_execute())
