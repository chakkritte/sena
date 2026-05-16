"""Agent state serialization for distributed execution."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

import structlog

from sena.core.models import AgentState, Message, MemoryEntry, ToolCall

logger = structlog.get_logger()


class StateSerializer:
    """Serialize and deserialize agent execution state."""

    @staticmethod
    def message_to_dict(msg: Message) -> dict[str, Any]:
        return {
            "role": msg.role,
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                }
                for tc in (msg.tool_calls or [])
            ],
            "tool_call_id": msg.tool_call_id,
            "name": msg.name,
        }

    @staticmethod
    def message_from_dict(data: dict[str, Any]) -> Message:
        tool_calls = None
        if data.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["name"],
                    arguments=tc.get("arguments", {}),
                )
                for tc in data["tool_calls"]
            ]
        return Message(
            role=data["role"],
            content=data.get("content"),
            tool_calls=tool_calls,
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
        )

    @staticmethod
    def memory_entry_to_dict(entry: MemoryEntry) -> dict[str, Any]:
        return {
            "id": entry.id,
            "namespace": entry.namespace,
            "content": entry.content,
            "metadata": entry.metadata,
            "created_at": entry.created_at,
            "score": entry.score,
        }

    @staticmethod
    def memory_entry_from_dict(data: dict[str, Any]) -> MemoryEntry:
        return MemoryEntry(
            id=data.get("id"),
            namespace=data.get("namespace", "default"),
            content=data["content"],
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at"),
            score=data.get("score"),
        )

    @classmethod
    def serialize_agent_state(cls, state: AgentState) -> str:
        payload = {
            "status": state.status,
            "current_task": state.current_task,
            "messages": [cls.message_to_dict(m) for m in state.messages],
            "memory_context": state.memory_context,
        }
        return json.dumps(payload, separators=(",", ":"))

    @classmethod
    def deserialize_agent_state(cls, raw: str) -> AgentState:
        data = json.loads(raw)
        return AgentState(
            status=data.get("status", "idle"),
            current_task=data.get("current_task"),
            messages=[cls.message_from_dict(m) for m in data.get("messages", [])],
            memory_context=data.get("memory_context"),
        )
