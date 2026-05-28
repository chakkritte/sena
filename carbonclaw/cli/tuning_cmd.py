"""CLI command for exporting agent session traces into fine-tuning datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import typer
import orjson as json

from carbonclaw.cli.main import app, console
from carbonclaw.telemetry.playback import TraceStore, StepTrace


@app.command(name="export-tuning")
def export_tuning(
    output: Path = typer.Option(
        Path("lora_dataset.jsonl"),
        "--output",
        "-o",
        help="Output filepath for the fine-tuning dataset.",
    ),
    format_style: str = typer.Option(
        "sharegpt",
        "--format",
        "-f",
        help="Fine-tuning dataset format: sharegpt, chatml, or alpaca.",
    ),
    min_steps: int = typer.Option(
        1,
        "--min-steps",
        "-m",
        help="Minimum number of execution steps for a session to be exported.",
    ),
) -> None:
    """Export successful agent session traces and self-healing fixes into a LoRA fine-tuning dataset."""
    style = format_style.lower()
    if style not in ("sharegpt", "chatml", "alpaca"):
        console.print(f"[bold red]Error:[/bold red] Unsupported format '{format_style}'. Supported: sharegpt, chatml, alpaca")
        raise typer.Exit(code=1)

    store = TraceStore()
    sessions = store.sessions()
    if not sessions:
        console.print("[yellow]Warning:[/yellow] No recorded session traces found to export.")
        return

    filtered_sessions = [s for s in sessions if s["total_steps"] >= min_steps]
    if not filtered_sessions:
        console.print(f"[yellow]Warning:[/yellow] No sessions found with at least {min_steps} steps.")
        return

    console.print(f"🔮 [bold green]CarbonClaw LoRA Fine-Tuning Export[/bold green]")
    console.print(f"Found [bold white]{len(filtered_sessions)}[/bold white] sessions matching filters. Exporting to [bold]{output}[/bold] in [cyan]{style}[/cyan] format...")

    exported_count = 0
    with output.open("wb") as f:
        for sess in filtered_sessions:
            session_id = sess["session_id"]
            traces = store.traces_for_session(session_id)
            if not traces:
                continue

            # Format current session traces based on style
            entry = None
            if style == "sharegpt":
                conversations = []
                # System instructions
                conversations.append({
                    "from": "system",
                    "value": f"You are a CarbonClaw {sess['agent_name'].upper()} Agent. Help the user complete tasks autonomously."
                })
                # Add task
                conversations.append({
                    "from": "human",
                    "value": traces[0].thought or "Execute current engineering task."
                })
                
                for idx, t in enumerate(traces):
                    thought_val = t.thought or ""
                    tools_val = ""
                    if t.tools_called:
                        tools_val = f"\nAction: {json.dumps(t.tools_called).decode('utf-8')}"
                    
                    conversations.append({
                        "from": "gpt",
                        "value": f"Thought: {thought_val}{tools_val}"
                    })
                    
                    if t.tool_results:
                        res_str = "\n".join(t.tool_results)
                        conversations.append({
                            "from": "tool",
                            "value": f"Response: {res_str}"
                        })
                entry = {"conversations": conversations}

            elif style == "chatml":
                messages = []
                messages.append({
                    "role": "system",
                    "content": f"You are a CarbonClaw {sess['agent_name'].upper()} Agent. Help the user complete tasks autonomously."
                })
                messages.append({
                    "role": "user",
                    "content": traces[0].thought or "Execute current engineering task."
                })
                
                for idx, t in enumerate(traces):
                    thought_val = t.thought or ""
                    tools_val = ""
                    if t.tools_called:
                        tools_val = f"\nAction: {json.dumps(t.tools_called).decode('utf-8')}"
                    
                    messages.append({
                        "role": "assistant",
                        "content": f"Thought: {thought_val}{tools_val}"
                    })
                    
                    if t.tool_results:
                        res_str = "\n".join(t.tool_results)
                        messages.append({
                            "role": "user",
                            "content": f"Response: {res_str}"
                        })
                entry = {"messages": messages}

            elif style == "alpaca":
                # Aggregate instructions and outcomes into single instruction/input/output blocks
                instruction = f"You are a CarbonClaw {sess['agent_name'].upper()} Agent."
                inp = traces[0].thought or "Execute current engineering task."
                
                out_steps = []
                for idx, t in enumerate(traces):
                    thought_val = t.thought or ""
                    tools_val = ""
                    if t.tools_called:
                        tools_val = f"\nAction: {json.dumps(t.tools_called).decode('utf-8')}"
                    out_steps.append(f"Step {idx + 1}: Thought: {thought_val}{tools_val}")
                    if t.tool_results:
                        res_str = "\n".join(t.tool_results)
                        out_steps.append(f"Response: {res_str}")
                entry = {
                    "instruction": instruction,
                    "input": inp,
                    "output": "\n".join(out_steps)
                }

            if entry:
                f.write(json.dumps(entry) + b"\n")
                exported_count += 1

    console.print(f"✨ [bold green]Success![/bold green] Exported [bold white]{exported_count}[/bold white] training records into [bold]{output}[/bold].")
