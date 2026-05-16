"""Sena CLI entry point."""

from __future__ import annotations

from typing import Any

import structlog
import typer
from rich.console import Console

app = typer.Typer(
    name="sena",
    help="Sena — AI-native runtime for autonomous software engineering",
    pretty_exceptions_show_locals=False,
    invoke_without_command=True,
)
console = Console()


def _setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit.", is_eager=True),
) -> None:
    """Sena — AI-native runtime for autonomous software engineering."""
    if version:
        from sena import __version__

        console.print(f"Sena {__version__}")
        raise typer.Exit()
    _setup_logging()
    from sena.config.settings import SenaConfig
    from sena.telemetry.otel import setup_telemetry
    setup_telemetry(SenaConfig())

    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


async def cli_approval_callback(name: str, arguments: dict[str, Any]) -> bool:
    """Consolidated CLI approval callback for all tools."""
    from rich.panel import Panel
    from rich.prompt import Confirm
    from rich.text import Text
    import json

    args_json = json.dumps(arguments, indent=2)
    console.print(
        Panel(
            Text(args_json, style="cyan"),
            title=f"[bold yellow]Approve action: {name}?[/bold yellow]",
            border_style="yellow",
            padding=(0, 1),
        )
    )
    return Confirm.ask("Proceed?")


# Import command modules to register them
from sena.cli import init, update, chat, config_cmd, doctor, memory_cmd, models, plan, run, snapshot, tui_cmd, web, worker  # noqa: E402, F401
