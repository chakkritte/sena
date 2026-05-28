"""CLI command for running the autonomous Self-Healing CI and lint daemon."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from carbonclaw.agents.healer_daemon import HealerDaemon
from carbonclaw.agents.supervisor import SupervisorAgent
from carbonclaw.cli.main import app, console
from carbonclaw.config.settings import CarbonClawConfig


@app.command(name="healer-daemon")
def healer_daemon_cmd(
    path: str = typer.Argument(
        ".", help="The directory path to monitor for python file changes."
    ),
    command: str = typer.Option(
        "uv run ruff check",
        "--command",
        "-c",
        help="The check/lint/test command to run on save.",
    ),
) -> None:
    """Start file-watching daemon that auto-heals lint and type errors on save."""
    config = CarbonClawConfig()

    async def _run() -> None:
        console.print("🩺 [bold yellow]Starting Self-Healing CI & Lint Daemon...[/bold yellow]")
        abs_path = Path(path).absolute()  # noqa: ASYNC240
        console.print(f"📂 [dim]Monitoring directory: {abs_path}[/dim]")
        console.print(f"⚙️ [dim]Check command: {command} <filepath>[/dim]")

        supervisor = await SupervisorAgent.create_default(config.default_provider)
        daemon = HealerDaemon(supervisor, watch_path=Path(path), check_command=command)

        try:
            await daemon.start(poll_interval=1.0)
        except KeyboardInterrupt:
            daemon.stop()
            console.print("\n[bold green]Stopping Self-Healing Daemon cleanly.[/bold green]")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[bold green]Stopping Self-Healing Daemon cleanly.[/bold green]")
