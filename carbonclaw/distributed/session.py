"""Collaborative agent session synchronization and shared carbon caps manager."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from platformdirs import user_config_dir
from pydantic import BaseModel, Field


class SharedSessionState(BaseModel):
    """Represents a shared distributed agent session state."""

    session_id: str
    carbon_cap: float = 0.0  # 0.0 means unlimited/no cap
    carbon_consumed: float = 0.0
    members: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CollaborativeSessionManager:
    """Manages multi-agent collaborative sessions, resource locking, and carbon limits."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the collaborative session manager with a SQLite backing store."""
        if db_path is None:
            db_path = Path(user_config_dir("carbonclaw")) / "collaborative_sessions.db"
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    carbon_cap REAL NOT NULL,
                    carbon_consumed REAL NOT NULL,
                    members TEXT NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS locks (
                    session_id TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (session_id, resource)
                )
                """
            )
            conn.commit()

    def create_session(
        self, session_id: str, carbon_cap: float = 0.0, members: list[str] | None = None
    ) -> SharedSessionState:
        """Create a new shared agent session."""
        import json

        m = members or []
        state = SharedSessionState(
            session_id=session_id,
            carbon_cap=carbon_cap,
            carbon_consumed=0.0,
            members=m,
            metadata={},
        )
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO sessions (session_id, carbon_cap, carbon_consumed, members, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    state.session_id,
                    state.carbon_cap,
                    state.carbon_consumed,
                    json.dumps(state.members),
                    json.dumps(state.metadata),
                ),
            )
            conn.commit()
        return state

    def get_session(self, session_id: str) -> SharedSessionState | None:
        """Retrieve a session by its ID."""
        import json

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT carbon_cap, carbon_consumed, members, metadata FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return SharedSessionState(
                session_id=session_id,
                carbon_cap=row[0],
                carbon_consumed=row[1],
                members=json.loads(row[2]),
                metadata=json.loads(row[3]),
            )

    def join_session(self, session_id: str, agent_id: str) -> bool:
        """Add an agent to a session."""
        import json

        session = self.get_session(session_id)
        if not session:
            return False
        if agent_id not in session.members:
            session.members.append(agent_id)
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE sessions SET members = ? WHERE session_id = ?",
                    (json.dumps(session.members), session_id),
                )
                conn.commit()
        return True

    def acquire_lock(self, session_id: str, resource: str, agent_id: str) -> bool:
        """Acquire an exclusive lock on a resource inside a session."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            # Check if lock already exists
            cursor.execute(
                "SELECT agent_id FROM locks WHERE session_id = ? AND resource = ?",
                (session_id, resource),
            )
            row = cursor.fetchone()
            if row:
                # If held by the same agent, succeed
                return bool(row[0] == agent_id)

            try:
                cursor.execute(
                    "INSERT INTO locks (session_id, resource, agent_id) VALUES (?, ?, ?)",
                    (session_id, resource, agent_id),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def release_lock(self, session_id: str, resource: str, agent_id: str) -> bool:
        """Release a resource lock inside a session."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM locks WHERE session_id = ? AND resource = ? AND agent_id = ?",
                (session_id, resource, agent_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def record_carbon(self, session_id: str, grams: float) -> float:
        """Record carbon consumption and enforce the shared session limit."""
        if grams < 0:
            raise ValueError("Carbon consumption cannot be negative")

        with sqlite3.connect(self._db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT carbon_cap, carbon_consumed FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                raise ValueError(f"Session '{session_id}' not found")

            cap, consumed = row[0], row[1]
            new_consumed = consumed + grams
            if cap > 0.0 and new_consumed > cap:
                conn.rollback()
                raise ValueError(
                    f"Exceeded shared carbon cap of {cap}g CO2 (attempted to add {grams}g, totaling {new_consumed}g)"
                )

            cursor.execute(
                "UPDATE sessions SET carbon_consumed = ? WHERE session_id = ?",
                (new_consumed, session_id),
            )
            conn.commit()
            return new_consumed
