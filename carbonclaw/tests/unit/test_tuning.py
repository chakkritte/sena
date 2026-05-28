import pytest
from typer.testing import CliRunner
from unittest.mock import MagicMock, patch
from pathlib import Path

from carbonclaw.cli.main import app
from carbonclaw.telemetry.playback import StepTrace


def test_export_tuning_command_no_sessions(tmp_path: Path) -> None:
    """The export-tuning CLI command gracefully handles the case with no recorded sessions."""
    runner = CliRunner()
    out_file = tmp_path / "dataset.jsonl"
    
    with patch("carbonclaw.cli.tuning_cmd.TraceStore.sessions", return_value=[]):
        result = runner.invoke(app, ["export-tuning", "-o", str(out_file)])
        assert result.exit_code == 0
        assert "No recorded session traces found" in result.output
        assert not out_file.exists()


def test_export_tuning_command_success(tmp_path: Path) -> None:
    """The export-tuning CLI command successfully filters and converts step traces into fine-tuning dataset."""
    runner = CliRunner()
    out_file = tmp_path / "dataset.jsonl"
    
    mock_sessions = [
        {
            "session_id": "sess_1",
            "agent_name": "coding",
            "total_steps": 2,
            "total_duration": 15.5,
            "total_emissions_kg": 0.0004,
            "timestamp": "2026-05-28T20:00:00Z"
        }
    ]
    
    mock_traces = [
        StepTrace(
            session_id="sess_1",
            agent_name="coding",
            step_index=0,
            thought="Write a python function",
            tools_called=[{"name": "file_write", "arguments": {"path": "app.py", "content": "print('hello')"}}],
            tool_results=["Successfully wrote file"]
        )
    ]
    
    with patch("carbonclaw.cli.tuning_cmd.TraceStore.sessions", return_value=mock_sessions), \
         patch("carbonclaw.cli.tuning_cmd.TraceStore.traces_for_session", return_value=mock_traces):
        
        # Test sharegpt export
        result = runner.invoke(app, ["export-tuning", "-o", str(out_file), "-f", "sharegpt", "-m", "1"])
        assert result.exit_code == 0
        assert "Exported 1 training records" in result.output
        assert out_file.exists()
        
        # Verify content is valid JSONL and has correct fields
        lines = out_file.read_text().splitlines()
        assert len(lines) == 1
        
        import json
        entry = json.loads(lines[0])
        assert "conversations" in entry
        assert len(entry["conversations"]) == 4 # system, human, gpt, tool
        assert entry["conversations"][0]["from"] == "system"
        assert "coding" in entry["conversations"][0]["value"].lower()
        assert entry["conversations"][1]["from"] == "human"
        assert entry["conversations"][1]["value"] == "Write a python function"
        assert entry["conversations"][2]["from"] == "gpt"
        assert "file_write" in entry["conversations"][2]["value"]
        assert entry["conversations"][3]["from"] == "tool"
        assert "Successfully wrote file" in entry["conversations"][3]["value"]
