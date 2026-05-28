"""CarbonClaw CLI entry point."""

from __future__ import annotations

from typing import Any

import structlog
import typer
from rich.console import Console, Group

app = typer.Typer(
    name="carbonclaw",
    help="CarbonClaw — AI-native runtime for autonomous software engineering",
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
    """CarbonClaw — AI-native runtime for autonomous software engineering."""
    if version:
        from carbonclaw import __version__

        console.print(f"CarbonClaw {__version__}")
        raise typer.Exit()
    _setup_logging()
    from carbonclaw.config.settings import CarbonClawConfig
    from carbonclaw.telemetry.otel import setup_telemetry
    setup_telemetry(CarbonClawConfig())

    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


# Global session state for auto-accept
_SESSION_AUTO_ACCEPT = False


def _get_impact_analysis(name: str, arguments: dict[str, Any]) -> str:
    """Provide a human-readable summary of the potential impact."""
    if name == "shell":
        cmd = arguments.get("command", "")
        if any(kw in cmd for kw in ["rm ", "mv ", "delete", "kill"]):
            return "[bold red]CRITICAL:[/bold red] This command may delete or move system/project files."
        return "[bold yellow]MODERATE:[/bold yellow] Executes a shell command that may change system state."
    elif name == "file_write":
        return f"[bold blue]INFO:[/bold blue] Overwrites the file at [bold]{arguments.get('path')}[/bold]."
    elif name == "file_patch":
        return f"[bold blue]INFO:[/bold blue] Applies changes to [bold]{arguments.get('path')}[/bold]."
    elif name == "browser":
        return f"[bold cyan]INFO:[/bold cyan] Interacts with the web at [bold]{arguments.get('url', 'current page')}[/bold]."
    return "[bold white]UNKNOWN:[/bold white] Review the arguments carefully."


async def cli_approval_callback(name: str, arguments: dict[str, Any]) -> bool:
    """Consolidated CLI approval callback for all tools."""
    global _SESSION_AUTO_ACCEPT
    
    if _SESSION_AUTO_ACCEPT:
        return True

    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.syntax import Syntax
    from rich.text import Text
    from rich.columns import Columns
    import json

    impact = _get_impact_analysis(name, arguments)
    title = f" Approve action: [bold]{name}?[/bold] "
    
    if name == "file_patch":
        path = arguments.get("path", "")
        diff_text = arguments.get("diff", "")
        title = f" Approve patch: [bold]{path}?[/bold] "
        content = Syntax(diff_text, "diff", theme="monokai", padding=0)
    elif name == "file_write":
        path = arguments.get("path", "")
        content_text = arguments.get("content", "")
        title = f" Approve write: [bold]{path}?[/bold] "
        content = Syntax(content_text, "python", theme="monokai", padding=0)
    else:
        args_json = json.dumps(arguments, indent=2)
        content = Text(args_json, style="cyan")

    console.print()
    console.print(
        Panel(
            Group(
                Text.from_markup(f"[bold]Impact Analysis:[/bold] {impact}"),
                Text(""),
                content,
            ),
            title=title,
            title_align="center",
            border_style="dim",
            padding=(1, 2),
        )
    )
    
    # Modern Selection UI
    options = [
        "[bold green](y)es[/bold green]",
        "[bold yellow](a)uto-accept[/bold yellow]",
        "[bold red](n)o[/bold red]",
    ]
    console.print(f"  [bold white]Proceed?[/bold white]  { '  '.join(options) }")
    
    try:
        choice = Prompt.ask(
            "  [bold cyan]Selection[/bold cyan]", 
            choices=["y", "a", "n"], 
            default="y", 
            show_choices=False
        )
        final_choice = choice.lower()
    except (KeyboardInterrupt, EOFError):
        final_choice = "n"
    
    if final_choice == "a":
        _SESSION_AUTO_ACCEPT = True
        return True
    
    return final_choice == "y"


# Import command modules to register them
from carbonclaw.cli import (  # noqa: E402, F401
    carbon_cmd,
    chat,
    config_cmd,
    doctor,
    doc_cmd,
    init,
    memory_cmd,
    models,
    plan,
    playback_cmd,
    run,
    schedule_cmd,
    snapshot,
    status,
    telemetry_cmd,
    template_cmd,
    tui_cmd,
    update,
    web,
    worker,
)
