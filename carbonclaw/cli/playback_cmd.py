"""CLI commands for replaying agent execution sessions."""

from __future__ import annotations

import typer
from rich.table import Table

from carbonclaw.cli.main import app, console
from carbonclaw.telemetry.playback import TraceStore, render_session_playback


@app.command(name="playback")
def playback(
    session_id: str = typer.Argument(..., help="The unique session ID to replay."),
) -> None:
    """Replay agent execution steps for a specific session."""
    playback_group = render_session_playback(session_id)
    if playback_group is None:
        console.print(f"[bold red]Error:[/bold red] Session '{session_id}' not found.")
        raise typer.Exit(code=1)
        
    console.print(playback_group)


@app.command(name="playback-list")
def playback_list() -> None:
    """List all tracked and replayable agent execution sessions."""
    store = TraceStore()
    sessions = store.sessions()
    
    if not sessions:
        console.print("[dim]No recorded agent sessions found.[/dim]")
        return
        
    table = Table(title="🎬 Tracked Agent Sessions", show_header=True, header_style="bold green")
    table.add_column("Session ID", style="cyan", no_wrap=True)
    table.add_column("Agent Class", style="white")
    table.add_column("Total Steps", justify="right", style="magenta")
    table.add_column("Total Duration", justify="right", style="yellow")
    table.add_column("Total Emissions (g)", justify="right", style="green")
    table.add_column("Timestamp", style="dim")

    for s in reversed(sessions):
        table.add_row(
            s["session_id"],
            s["agent_name"].upper(),
            str(s["total_steps"]),
            f"{s['total_duration']:.2f}s",
            f"{s['total_emissions_kg'] * 1000.0:.3f}g",
            s["timestamp"].split("T")[0] if "T" in s["timestamp"] else s["timestamp"],
        )
    console.print(table)
