"""One-shot task execution."""

from __future__ import annotations

import asyncio

import typer

from carbonclaw.agents.coding import CodingAgent
from carbonclaw.cli.main import app, cli_approval_callback, console
from carbonclaw.config.settings import CarbonClawConfig
from carbonclaw.memory.sqlite import SQLiteMemory
from carbonclaw.providers.registry import ProviderRegistry
from carbonclaw.tools.base import ToolRegistry
from carbonclaw.tools.browser import BrowserTool
from carbonclaw.tools.file import FilePatchTool, FileReadTool, FileWriteTool
from carbonclaw.tools.git import GitTool
from carbonclaw.tools.mcp import register_mcp_tools
from carbonclaw.tools.shell import ShellTool


@app.command()
def run(
    task: str = typer.Argument(..., help="The task for the agent to execute."),
    provider: str | None = typer.Option(None, "--provider", "-p", help="LLM provider to use."),
    model: str | None = typer.Option(None, "--model", "-m", help="Model ID to use."),
    carbon_budget: str | None = typer.Option(
        None, "--carbon-budget", help="Carbon budget limit (e.g. 5g, 500mg)."
    ),
) -> None:
    """Run a one-shot task using the coding agent."""
    config = CarbonClawConfig()
    provider_name = provider or config.default_provider
    model = model or config.default_model

    if carbon_budget:
        from carbonclaw.telemetry.carbon import parse_carbon_budget

        parsed = parse_carbon_budget(carbon_budget)
        if parsed is not None:
            config.carbon_budget = parsed
            console.print(f"🌱 [dim]Carbon Budget applied: {parsed:.3f}g CO2[/dim]")

    async def _execute() -> None:
        prov = ProviderRegistry.create(provider_name, config)
        mem = SQLiteMemory()
        tools = ToolRegistry()
        tools.register(ShellTool())
        tools.register(BrowserTool())
        tools.register(FileReadTool())
        tools.register(FileWriteTool())
        tools.register(FilePatchTool())
        tools.register(GitTool())

        # Register MCP tools
        mcp_clients = await register_mcp_tools(tools, config)

        agent = CodingAgent(
            provider=prov,
            tools=tools.list_tools(),
            memory=mem,
            model=model,
            approval_callback=cli_approval_callback,
        )

        try:
            console.print(f"[bold green]Running:[/bold green] {task}\n")
            async for text in agent.stream_run(task):
                console.print(text, end="")
            console.print()
        finally:
            # Disconnect MCP clients
            for client in mcp_clients:
                await client.disconnect()

    asyncio.run(_execute())

