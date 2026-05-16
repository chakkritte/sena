"""Snapshot management CLI commands."""

from __future__ import annotations

import asyncio

import typer
from rich.table import Table

from sena.agents.snapshot import AgentSnapshot
from sena.cli.main import app, console


@app.command()
def snapshot(
    action: str = typer.Argument(..., help="Action: list, delete, restore."),
    id: str | None = typer.Argument(None, help="Snapshot ID."),
) -> None:
    """Manage agent state snapshots."""
    mgr = AgentSnapshot()

    if action == "list":
        snapshots = mgr.list_snapshots()
        if not snapshots:
            console.print("[dim]No snapshots found.[/dim]")
            return
        table = Table()
        table.add_column("ID", style="cyan")
        table.add_column("Agent")
        table.add_column("Status")
        table.add_column("Task")
        table.add_column("Created")
        for s in snapshots:
            table.add_row(s["id"], s["agent"], s["status"], s["task"], s["created_at"])
        console.print(table)

    elif action == "delete":
        if not id:
            console.print("[red]Snapshot ID required.[/red]")
            raise typer.Exit(1)
        ok = mgr.delete(id)
        console.print("[green]Deleted[/green]" if ok else "[red]Not found[/red]")

    elif action == "restore":
        if not id:
            console.print("[red]Snapshot ID required.[/red]")
            raise typer.Exit(1)
        data = mgr.load(id)
        if data is None:
            console.print("[red]Snapshot not found.[/red]")
            raise typer.Exit(1)
        console.print(f"[bold]Snapshot {id}[/bold]")
        console.print(f"Agent: {data.get('agent')}")
        console.print(f"Created: {data.get('created_at')}")
        state = data.get("state", {})
        console.print(f"Status: {state.get('status')}")
        console.print(f"Task: {state.get('current_task', '')[:80]}")
        console.print(f"Messages: {len(state.get('messages', []))}")

    else:
        console.print(f"[red]Unknown action:[/red] {action}")
