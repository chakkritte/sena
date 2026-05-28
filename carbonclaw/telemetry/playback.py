"""Agent session playback logging and visualization for CarbonClaw."""

from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir
from pydantic import BaseModel, Field
from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table


class StepTrace(BaseModel):
    """A trace record for a single execution step of a ReAct loop."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    session_id: str
    agent_name: str
    step_index: int
    thought: str | None = None
    tools_called: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[str] = Field(default_factory=list)
    duration_secs: float = 0.0
    carbon_emissions_kg: float = 0.0
    timestamp: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat()
    )


class TraceStore:
    """Persistent storage for agent execution traces."""

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the trace store."""
        if path is None:
            data_dir = Path(user_data_dir("carbonclaw", "carbonclaw"))
            data_dir.mkdir(parents=True, exist_ok=True)
            path = data_dir / "session_traces.jsonl"
        self._path = path

    def record_step(self, trace: StepTrace) -> None:
        """Append a step execution trace to the store."""
        line = trace.model_dump_json()
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def traces_for_session(self, session_id: str) -> list[StepTrace]:
        """Load and filter all traces belonging to a specific session."""
        results: list[StepTrace] = []
        if not self._path.exists():
            return results
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    trace = StepTrace.model_validate_json(line)
                    if trace.session_id == session_id:
                        results.append(trace)
                except Exception:
                    continue
        # Sort by step index to ensure sequential playback
        results.sort(key=lambda t: t.step_index)
        return results

    def sessions(self) -> list[dict[str, Any]]:
        """Retrieve list of unique tracked sessions with summary metadata."""
        sessions_map: dict[str, dict[str, Any]] = {}
        if not self._path.exists():
            return []
            
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    trace = StepTrace.model_validate_json(line)
                    s_id = trace.session_id
                    if s_id not in sessions_map:
                        sessions_map[s_id] = {
                            "session_id": s_id,
                            "agent_name": trace.agent_name,
                            "total_steps": 1,
                            "total_duration": trace.duration_secs,
                            "total_emissions_kg": trace.carbon_emissions_kg,
                            "timestamp": trace.timestamp,
                        }
                    else:
                        sessions_map[s_id]["total_steps"] += 1
                        sessions_map[s_id]["total_duration"] += trace.duration_secs
                        sessions_map[s_id]["total_emissions_kg"] += trace.carbon_emissions_kg
                except Exception:
                    continue
                    
        return list(sessions_map.values())


def render_session_playback(session_id: str) -> Group | None:
    """Renders a beautiful step-by-step trace timeline for a given session."""
    store = TraceStore()
    traces = store.traces_for_session(session_id)
    if not traces:
        return None

    elements: list[Any] = []
    
    # Render Session Header
    t_start = traces[0]
    duration_total = sum(t.duration_secs for t in traces)
    emissions_total = sum(t.carbon_emissions_kg for t in traces)
    
    header_table = Table.grid(padding=1)
    header_table.add_column("Key", style="bold green")
    header_table.add_column("Value", style="cyan")
    header_table.add_row("Session ID:", t_start.session_id)
    header_table.add_row("Agent Class:", t_start.agent_name.upper())
    header_table.add_row("Total Steps:", str(len(traces)))
    header_table.add_row("Total Duration:", f"{duration_total:.2f}s")
    header_table.add_row("Total Emissions:", f"{emissions_total:.6f} kg CO2")
    
    elements.append(
        Panel(
            header_table,
            title="🎬 CarbonClaw Agent Playback Dashboard",
            border_style="bold green",
            padding=(1, 2)
        )
    )

    # Render individual steps
    for trace in traces:
        step_elements = []
        
        # 1. Thought block
        if trace.thought:
            step_elements.append(
                Panel(
                    trace.thought.strip(),
                    title="🧠 Thought/Reasoning",
                    border_style="dim white",
                    padding=(0, 1)
                )
            )
            
        # 2. Tool calls
        if trace.tools_called:
            for idx, tool in enumerate(trace.tools_called):
                args_str = json.dumps(tool.get("arguments", {}), indent=2)
                tool_panel = Panel(
                    Syntax(args_str, "json", theme="monokai"),
                    title=f"🔧 Tool Invocation: {tool.get('name')}",
                    border_style="yellow",
                    padding=(0, 1)
                )
                step_elements.append(tool_panel)
                
                # Associated tool result
                if idx < len(trace.tool_results):
                    res_text = trace.tool_results[idx]
                    res_panel = Panel(
                        res_text if len(res_text) < 1000 else res_text[:997] + "...",
                        title=f"📥 Tool Output: {tool.get('name')}",
                        border_style="green",
                        padding=(0, 1)
                    )
                    step_elements.append(res_panel)
                    
        # Metric Footer
        footer_stats = (
            f"⏱️ Duration: {trace.duration_secs:.2f}s | "
            f"🌱 Emissions: {trace.carbon_emissions_kg * 1000.0:.3f}g CO2"
        )
        
        elements.append(
            Panel(
                Group(*step_elements),
                title=f"✨ Step {trace.step_index}",
                subtitle=footer_stats,
                subtitle_align="right",
                border_style="blue",
                padding=(1, 1)
            )
        )
        
    return Group(*elements)
