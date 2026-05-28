"""Unit tests for collaborative agent sessions."""

from __future__ import annotations

from pathlib import Path

import pytest

from carbonclaw.distributed.session import CollaborativeSessionManager


def test_create_and_get_session(tmp_path: Path) -> None:
    db_path = tmp_path / "collab.db"
    manager = CollaborativeSessionManager(db_path=db_path)

    session = manager.create_session("session-123", carbon_cap=100.0, members=["agent-1"])
    assert session.session_id == "session-123"
    assert session.carbon_cap == 100.0
    assert session.members == ["agent-1"]

    retrieved = manager.get_session("session-123")
    assert retrieved is not None
    assert retrieved.session_id == "session-123"
    assert retrieved.carbon_cap == 100.0
    assert retrieved.members == ["agent-1"]


def test_join_session(tmp_path: Path) -> None:
    db_path = tmp_path / "collab.db"
    manager = CollaborativeSessionManager(db_path=db_path)

    manager.create_session("session-123", carbon_cap=50.0, members=["agent-1"])
    assert manager.join_session("session-123", "agent-2")

    retrieved = manager.get_session("session-123")
    assert retrieved is not None
    assert retrieved.members == ["agent-1", "agent-2"]

    # Try joining non-existent session
    assert not manager.join_session("session-unknown", "agent-2")


def test_resource_locking(tmp_path: Path) -> None:
    db_path = tmp_path / "collab.db"
    manager = CollaborativeSessionManager(db_path=db_path)

    session_id = "session-lock"
    manager.create_session(session_id)

    # Acquire lock for agent-1
    assert manager.acquire_lock(session_id, "file_a.py", "agent-1")

    # Re-acquire same lock for agent-1 (should succeed)
    assert manager.acquire_lock(session_id, "file_a.py", "agent-1")

    # Try to acquire lock for agent-2 on same file (should fail)
    assert not manager.acquire_lock(session_id, "file_a.py", "agent-2")

    # Release lock by agent-2 (should fail/return False because agent-2 doesn't own it)
    assert not manager.release_lock(session_id, "file_a.py", "agent-2")

    # Release lock by agent-1 (should succeed)
    assert manager.release_lock(session_id, "file_a.py", "agent-1")

    # Acquire lock for agent-2 now (should succeed)
    assert manager.acquire_lock(session_id, "file_a.py", "agent-2")


def test_carbon_recording_and_cap_enforcement(tmp_path: Path) -> None:
    db_path = tmp_path / "collab.db"
    manager = CollaborativeSessionManager(db_path=db_path)

    session_id = "session-carbon"
    manager.create_session(session_id, carbon_cap=10.0)

    # Record carbon within cap
    consumed = manager.record_carbon(session_id, 4.5)
    assert consumed == 4.5

    # Record more carbon within cap
    consumed = manager.record_carbon(session_id, 4.0)
    assert consumed == 8.5

    # Try recording carbon exceeding cap
    with pytest.raises(ValueError, match="Exceeded shared carbon cap"):
        manager.record_carbon(session_id, 2.0)

    # Check that consumed was not updated to exceeded value
    session = manager.get_session(session_id)
    assert session is not None
    assert session.carbon_consumed == 8.5
