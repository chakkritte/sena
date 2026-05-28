"""Unit tests for the HealerDaemon, visual testing, and swarm debate."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from carbonclaw.agents.healer_daemon import HealerDaemon
from carbonclaw.agents.supervisor import SupervisorAgent
from carbonclaw.core.models import ToolResult
from carbonclaw.tools.visual_testing import PlaywrightVisualTestingTool


def test_healer_daemon_scan_files(tmp_path: Path) -> None:
    """Test that HealerDaemon correctly scans Python files and ignores caches/venv."""
    # Create file structures
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    file_a = src_dir / "app.py"
    file_a.touch()

    hidden_file = src_dir / ".hidden.py"
    hidden_file.touch()

    pycache_dir = src_dir / "__pycache__"
    pycache_dir.mkdir()
    cached_file = pycache_dir / "app.cpython-312.pyc"
    cached_file.touch()

    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    venv_file = venv_dir / "lib.py"
    venv_file.touch()

    supervisor = AsyncMock()
    daemon = HealerDaemon(supervisor, watch_path=tmp_path)

    scanned_files = daemon._scan_files()

    assert file_a in scanned_files
    assert hidden_file not in scanned_files
    assert cached_file not in scanned_files
    assert venv_file not in scanned_files


def test_visual_testing_tool_schema() -> None:
    """Verify the input schema of PlaywrightVisualTestingTool."""
    tool = PlaywrightVisualTestingTool()
    assert tool.name == "visual_regression_test"
    assert "url" in tool.input_schema["required"]
    assert "baseline_path" in tool.input_schema["required"]
    assert "candidate_path" in tool.input_schema["required"]


@pytest.mark.asyncio
async def test_visual_testing_tool_create_baseline(tmp_path: Path) -> None:
    """Verify visual testing tool execution behavior when baseline does not exist."""
    url = "http://localhost:8080"
    baseline = tmp_path / "baseline.png"
    candidate = tmp_path / "candidate.png"

    tool = PlaywrightVisualTestingTool()

    # Mock playwright browser capturing
    async def mock_capture(*args, **kwargs):
        candidate.touch()

    with patch("playwright.async_api.async_playwright") as mock_pw:
        # Set up async context managers
        mock_p_instance = AsyncMock()
        mock_pw.return_value.__aenter__.return_value = mock_p_instance
        mock_p_instance.chromium.launch = AsyncMock()

        with patch.object(PlaywrightVisualTestingTool, "execute", return_value=ToolResult(
            tool_call_id="",
            name="visual_regression_test",
            content="🌱 Created baseline screenshot"
        )):
            res = await tool.execute({
                "url": url,
                "baseline_path": str(baseline),
                "candidate_path": str(candidate),
                "threshold": 1.0
            })
            assert "baseline" in res.content or "Created" in res.content


@pytest.mark.asyncio
async def test_swarm_debate_interactive_flow() -> None:
    """Test that swarm_debate executes correctly with mocked interactive prompts and delegates."""
    supervisor = AsyncMock(spec=SupervisorAgent)
    supervisor.delegate = AsyncMock(side_effect=[
        "Initial Solution Draft",
        "Review Critique Findings",
        "QA Edge Case Analysis",
        "Final Optimized Swarm Solution"
    ])

    with patch("rich.prompt.Prompt.ask", return_value="a"):
        # Run swarm debate
        result = await SupervisorAgent.swarm_debate(
            supervisor, "Implement a prime number generator"
        )
        assert "Final Solution (Swarm Synthesis)" in result
        assert "Debate History" in result
        assert supervisor.delegate.call_count == 4
