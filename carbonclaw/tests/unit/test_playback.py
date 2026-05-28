"""Unit tests for the Session Playback and Debugger."""

from __future__ import annotations

from pathlib import Path

import pytest

from carbonclaw.cli.slash import Message, SlashRegistry
from carbonclaw.telemetry.playback import StepTrace, TraceStore, render_session_playback


def test_playback_logging_and_loading(tmp_path: Path) -> None:
    """Test recording, loading, and sorting steps in the TraceStore."""
    db_file = tmp_path / "session_traces.jsonl"
    store = TraceStore(db_file)

    # Assert store is empty
    assert len(store.sessions()) == 0

    # Add a mock trace step
    trace = StepTrace(
        session_id="session123",
        agent_name="coding",
        step_index=1,
        thought="I will read base.py",
        tools_called=[{"name": "file_read", "arguments": {"path": "base.py"}}],
        tool_results=["File contents here"],
        duration_secs=1.5,
        carbon_emissions_kg=0.0001,
    )
    store.record_step(trace)

    # Load traces and verify
    traces = store.traces_for_session("session123")
    assert len(traces) == 1
    assert traces[0].thought == "I will read base.py"
    assert traces[0].duration_secs == 1.5

    # Load unique sessions list
    sessions = store.sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "session123"
    assert sessions[0]["total_steps"] == 1


def test_playback_visual_timeline_rendering(tmp_path: Path) -> None:
    """Test that playback rendering correctly constructs rich Groups."""
    db_file = tmp_path / "session_traces.jsonl"
    store = TraceStore(db_file)

    # Record step
    trace = StepTrace(
        session_id="session123",
        agent_name="coding",
        step_index=1,
        thought="Testing playback rendering",
        tools_called=[{"name": "shell", "arguments": {"command": "ls"}}],
        tool_results=["file1.py\nfile2.py"],
        duration_secs=0.5,
        carbon_emissions_kg=0.00005,
    )
    store.record_step(trace)

    # Patch store for rendering
    original_store_init = TraceStore.__init__

    def mock_init(self, path=None):
        original_store_init(self, db_file)

    TraceStore.__init__ = mock_init

    try:
        render_group = render_session_playback("session123")
        assert render_group is not None
        assert len(render_group.renderables) == 2  # Header Panel + Step 1 Panel
    finally:
        TraceStore.__init__ = original_store_init


@pytest.mark.asyncio
async def test_playback_slash_command(tmp_path: Path) -> None:
    """Test replaying sessions using the interactive chat slash command."""
    db_file = tmp_path / "session_traces.jsonl"
    store = TraceStore(db_file)

    # Record trace
    trace = StepTrace(
        session_id="session123",
        agent_name="coding",
        step_index=1,
        thought="Test chat replaying",
        duration_secs=0.1,
    )
    store.record_step(trace)

    # Patch stores
    original_store_init = TraceStore.__init__

    def mock_init(self, path=None):
        original_store_init(self, db_file)

    TraceStore.__init__ = mock_init

    try:
        registry = SlashRegistry()
        messages: list[Message] = []

        # Test replaying a non-existent session
        res_fail = await registry.dispatch(messages, "/playback non_existent")
        assert res_fail is not None
        assert "not found" in res_fail.output

        # Test replaying an existing session
        res_ok = await registry.dispatch(messages, "/playback session123")
        assert res_ok is not None
        assert res_ok.output is not None  # Renders the Group object successfully
    finally:
        TraceStore.__init__ = original_store_init
