"""CLI commands for managing carbon-aware task schedules."""

from __future__ import annotations

import asyncio
import datetime
import time

import typer
from rich.table import Table

from carbonclaw.cli.main import app, console
from carbonclaw.telemetry.scheduler import SchedulerStore, execute_task


@app.command(name="schedule-add")
def schedule_add(
    task: str = typer.Argument(..., help="The task instructions/command to schedule."),
    mode: str = typer.Option(
        "code", "--mode", "-m", help="Agent mode to use (code, research, swarm)."
    ),
) -> None:
    """Schedule a task for carbon-aware execution."""
    store = SchedulerStore()
    scheduled_task = store.add_task(task, mode)

    console.print("🌱 [bold green]Task Scheduled Successfully![/bold green]")
    console.print(f"[bold]Task ID:[/bold] {scheduled_task.id}")
    console.print(f"[bold]Instruction:[/bold] {scheduled_task.command}")
    console.print(f"[bold]Scheduled Execution Time:[/bold] {scheduled_task.scheduled_at}")
    console.print(
        f"[bold]Estimated Carbon Savings:[/bold] "
        f"[bold white]{scheduled_task.carbon_savings_grams:.2f}g CO2[/bold white]"
    )
    console.print(
        "[dim]Run 'carbonclaw schedule-run-due' or 'carbonclaw schedule-daemon' "
        "to process queued tasks.[/dim]"
    )


@app.command(name="schedule-list")
def schedule_list() -> None:
    """List all queued and completed scheduled tasks."""
    store = SchedulerStore()
    tasks = store.tasks()

    if not tasks:
        console.print("[dim]No scheduled tasks found.[/dim]")
        return

    table = Table(
        title="🌱 Carbon-Aware Task Schedule", show_header=True, header_style="bold green"
    )
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Task / Instruction", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Scheduled At", style="dim")
    table.add_column("Est. Savings", justify="right", style="green")
    table.add_column("Emissions (kg CO2)", justify="right", style="bold red")

    for t in tasks:
        status_color = "yellow"
        if t.status == "completed":
            status_color = "green"
        elif t.status == "failed":
            status_color = "red"
        elif t.status == "running":
            status_color = "blue"

        status_str = f"[{status_color}]{t.status}[/{status_color}]"

        table.add_row(
            t.id,
            t.command if len(t.command) < 50 else t.command[:47] + "...",
            status_str,
            t.scheduled_at.split("T")[1][:5] if "T" in t.scheduled_at else t.scheduled_at,
            f"{t.carbon_savings_grams:.1f}g",
            f"{t.emissions_kg:.6f}" if t.status == "completed" else "-",
        )
    console.print(table)


@app.command(name="schedule-now")
def schedule_now(
    task_id: str = typer.Argument(..., help="The ID of the task to execute immediately."),
) -> None:
    """Execute a queued task immediately (bypassing carbon-aware delay)."""
    store = SchedulerStore()
    tasks = store.tasks()
    task = next((t for t in tasks if t.id == task_id), None)

    if not task:
        console.print(f"[bold red]Error:[/bold red] Task '{task_id}' not found.")
        raise typer.Exit(code=1)

    if task.status in ["completed", "running"]:
        console.print(f"[yellow]Task is already in status '{task.status}'.[/yellow]")
        return

    console.print(f"🚀 [bold yellow]Executing task '{task_id}' immediately...[/bold yellow]")
    store.update_task_status(task_id, "running")

    try:
        emissions = asyncio.run(execute_task(task))
        store.update_task_status(task_id, "completed", emissions)
        console.print(f"[bold green]✅ Task '{task_id}' successfully completed.[/bold green]")
        console.print(f"[green]Emissions:[/green] [white]{emissions:.6f} kg CO2[/white]")
    except Exception as e:
        store.update_task_status(task_id, "failed")
        console.print(f"[bold red]❌ Task execution failed:[/bold red] {e}")
        raise typer.Exit(code=1) from e


@app.command(name="schedule-run-due")
def schedule_run_due() -> None:
    """Run all queued tasks that are past their scheduled execution time."""
    store = SchedulerStore()
    tasks = store.tasks()

    now_iso = datetime.datetime.now(datetime.UTC).isoformat()
    due_tasks = [t for t in tasks if t.status == "queued" and t.scheduled_at <= now_iso]

    if not due_tasks:
        console.print("[dim]No due scheduled tasks to run.[/dim]")
        return

    console.print(f"🌱 [bold green]Running {len(due_tasks)} due tasks...[/bold green]")

    for task in due_tasks:
        console.print(f"⏳ Processing [cyan]{task.id}[/cyan]: '{task.command}'")
        store.update_task_status(task.id, "running")
        try:
            emissions = asyncio.run(execute_task(task))
            store.update_task_status(task.id, "completed", emissions)
            console.print(f"  [bold green]Success[/bold green] (Emissions: {emissions:.6f} kg CO2)")
        except Exception as e:
            store.update_task_status(task.id, "failed")
            console.print(f"  [bold red]Failed:[/bold red] {e}")


@app.command(name="schedule-daemon")
def schedule_daemon(
    interval: int = typer.Option(60, "--interval", "-i", help="Polling interval in seconds."),
) -> None:
    """Start a persistent background daemon polling for due scheduled tasks."""
    console.print(
        f"⏰ [bold green]CarbonClaw Scheduler Daemon Started[/bold green] (interval: {interval}s)"
    )
    console.print("[dim]Press Ctrl+C to terminate the daemon.[/dim]")

    store = SchedulerStore()

    try:
        while True:
            tasks = store.tasks()
            now_iso = datetime.datetime.now(datetime.UTC).isoformat()
            due_tasks = [t for t in tasks if t.status == "queued" and t.scheduled_at <= now_iso]

            if due_tasks:
                console.print(
                    f"\n[bold yellow]Found {len(due_tasks)} due tasks at {now_iso}...[/bold yellow]"
                )
                for task in due_tasks:
                    console.print(f"⚡ Running task [cyan]{task.id}[/cyan]...")
                    store.update_task_status(task.id, "running")
                    try:
                        emissions = asyncio.run(execute_task(task))
                        store.update_task_status(task.id, "completed", emissions)
                        console.print(
                            f"  [bold green]Task {task.id} Completed.[/bold green] "
                            f"Emissions: {emissions:.6f} kg CO2"
                        )
                    except Exception as e:
                        store.update_task_status(task.id, "failed")
                        console.print(f"  [bold red]Task {task.id} Failed:[/bold red] {e}")
            else:
                # Print a subtle heartbeat to show the daemon is alive
                print(".", end="", flush=True)

            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]Daemon stopped by user.[/yellow]")
