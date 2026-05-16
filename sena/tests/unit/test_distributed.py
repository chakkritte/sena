"""Unit tests for distributed runtime components."""

from __future__ import annotations

import pytest

from sena.core.models import AgentState, Message
from sena.distributed.serialization import StateSerializer
from sena.distributed.queue import TaskQueue, Task, TaskStatus


def test_serializer_roundtrip() -> None:
    state = AgentState(
        status="running",
        current_task="fix bug",
        messages=[Message(role="user", content="hello")],
    )
    raw = StateSerializer.serialize_agent_state(state)
    restored = StateSerializer.deserialize_agent_state(raw)
    assert restored.status == "running"
    assert restored.current_task == "fix bug"
    assert len(restored.messages) == 1
    assert restored.messages[0].content == "hello"


@pytest.mark.asyncio
async def test_task_queue_submit_complete() -> None:
    queue = TaskQueue()
    task = Task(agent_type="coding", payload={"task": "hello"})
    await queue.submit(task)
    assert len(queue) == 1

    next_task = await queue.next_task(timeout=1)
    assert next_task is not None
    assert next_task.status == TaskStatus.RUNNING

    await queue.complete(task.id, "done")
    t = await queue.get(task.id)
    assert t is not None
    assert t.status == TaskStatus.COMPLETED
    assert t.result == "done"


@pytest.mark.asyncio
async def test_task_queue_fail() -> None:
    queue = TaskQueue()
    task = Task(agent_type="coding")
    await queue.submit(task)

    t = await queue.next_task(timeout=1)
    assert t is not None

    await queue.fail(task.id, "timeout")
    t = await queue.get(task.id)
    assert t is not None
    assert t.status == TaskStatus.FAILED
    assert t.error == "timeout"


@pytest.mark.asyncio
async def test_task_queue_cancel() -> None:
    queue = TaskQueue()
    task = Task(agent_type="coding")
    await queue.submit(task)

    ok = await queue.cancel(task.id)
    assert ok
    t = await queue.get(task.id)
    assert t is not None
    assert t.status == TaskStatus.CANCELLED
