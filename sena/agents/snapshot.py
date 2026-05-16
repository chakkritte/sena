"""Agent state snapshot persistence and resume."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from sena.agents.base import ReactAgent
from sena.core.models import AgentState, Message
from sena.distributed.serialization import StateSerializer

logger = structlog.get_logger()


class AgentSnapshot:
    """Disk-based snapshot manager for agent execution state."""

    def __init__(self, snapshot_dir: Path | None = None) -> None:
        if snapshot_dir is None:
            from sena.config.settings import SenaConfig
            snapshot_dir = SenaConfig.user_dir() / "snapshots"
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def _snapshot_path(self, snapshot_id: str) -> Path:
        return self.snapshot_dir / f"{snapshot_id}.json"

    def save(
        self,
        state: AgentState,
        agent_name: str = "react",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Save an agent state to disk and return the snapshot ID."""
        snapshot_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "id": snapshot_id,
            "agent": agent_name,
            "created_at": now,
            "state": json.loads(StateSerializer.serialize_agent_state(state)),
            "metadata": metadata or {},
        }
        path = self._snapshot_path(snapshot_id)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("snapshot.saved", id=snapshot_id, path=str(path))
        return snapshot_id

    def load(self, snapshot_id: str) -> dict[str, Any] | None:
        """Load a raw snapshot payload by ID."""
        path = self._snapshot_path(snapshot_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except Exception:
            logger.exception("snapshot.load_failed", id=snapshot_id)
            return None

    def restore_state(self, snapshot_id: str) -> AgentState | None:
        """Restore an AgentState from a snapshot."""
        payload = self.load(snapshot_id)
        if payload is None:
            return None
        try:
            return StateSerializer.deserialize_agent_state(
                json.dumps(payload["state"])
            )
        except Exception:
            logger.exception("snapshot.restore_failed", id=snapshot_id)
            return None

    def list_snapshots(self) -> list[dict[str, Any]]:
        """List all available snapshots."""
        snapshots: list[dict[str, Any]] = []
        for path in sorted(self.snapshot_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                snapshots.append({
                    "id": data.get("id", path.stem),
                    "agent": data.get("agent", "unknown"),
                    "created_at": data.get("created_at", ""),
                    "status": data.get("state", {}).get("status", "unknown"),
                    "task": data.get("state", {}).get("current_task", "")[:60],
                })
            except Exception:
                pass
        return snapshots

    def delete(self, snapshot_id: str) -> bool:
        """Delete a snapshot by ID."""
        path = self._snapshot_path(snapshot_id)
        if path.exists():
            path.unlink()
            logger.info("snapshot.deleted", id=snapshot_id)
            return True
        return False


class ResumableAgent(ReactAgent):
    """ReactAgent with snapshot save/resume capabilities."""

    def __init__(self, *args: Any, snapshot: AgentSnapshot | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.snapshot = snapshot or AgentSnapshot()

    async def run(self, task: str, context: dict[str, Any] | None = None) -> str:
        result = await super().run(task, context)
        # Capture state after execution
        from sena.core.models import AgentState
        state = AgentState(
            status="done",
            current_task=task,
            messages=self._last_messages(),
        )
        self.snapshot.save(state, agent_name=self.name)
        return result

    async def run_with_snapshot(self, task: str, context: dict[str, Any] | None = None) -> str:
        """Run and always save a snapshot, even on error."""
        try:
            result = await self.run(task, context)
            return result
        except Exception as e:
            from sena.core.models import AgentState
            state = AgentState(
                status="error",
                current_task=task,
                messages=self._last_messages(),
            )
            self.snapshot.save(state, agent_name=self.name, metadata={"error": str(e)})
            raise

    def _last_messages(self) -> list[Message]:
        """Return the last known message list for snapshotting."""
        # This is a best-effort snapshot. In a full implementation,
        # AgentContext would expose its message list directly.
        return []

    async def resume(self, snapshot_id: str, new_task: str | None = None) -> str:
        """Resume from a snapshot with an optional new task."""
        state = self.snapshot.restore_state(snapshot_id)
        if state is None:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        logger.info("snapshot.resuming", id=snapshot_id, status=state.status)
        task = new_task or state.current_task or "Continue"
        # Prepend the restored memory context as a system reminder
        if state.memory_context:
            from sena.core.models import Message
            # In a full implementation, we'd hydrate the agent's message list
            pass
        return await self.run(task)
