"""Async event bus for multi-agent communication."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class Event:
    """A message on the event bus."""

    type: str
    payload: Any
    source: str = "unknown"
    target: str | None = None  # broadcast if None
    id: str = field(default_factory=lambda: "")

    def __post_init__(self) -> None:
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:12]


class EventBus:
    """In-memory async event bus for agent coordination.

    Supports broadcast and targeted messaging. Subscribers receive
    events matching a type filter (or all events if filter is "*").
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[Event]]] = {}
        self._handlers: list[tuple[str, Callable[[Event], Any]]] = []
        self._lock = asyncio.Lock()

    async def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers."""
        async with self._lock:
            queues = list(self._queues.get("*", []))
            queues.extend(self._queues.get(event.type, []))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("event_bus.queue_full", event_type=event.type)

    def subscribe(self, event_type: str = "*") -> asyncio.Queue[Event]:
        """Subscribe to events of a given type. Use '*' for all."""
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
        self._queues.setdefault(event_type, []).append(q)
        return q

    def unsubscribe(self, event_type: str, q: asyncio.Queue[Event]) -> None:
        """Remove a queue subscription."""
        subs = self._queues.get(event_type, [])
        if q in subs:
            subs.remove(q)

    async def stream(self, event_type: str = "*") -> AsyncIterator[Event]:
        """Async iterator over events of a given type."""
        q = self.subscribe(event_type)
        try:
            while True:
                yield await q.get()
        finally:
            self.unsubscribe(event_type, q)

    def on(self, event_type: str, handler: Callable[[Event], Any]) -> None:
        """Register a synchronous handler."""
        self._handlers.append((event_type, handler))

    def _dispatch_sync(self, event: Event) -> None:
        """Dispatch to synchronous handlers (fire-and-forget)."""
        for et, handler in self._handlers:
            if et in ("*", event.type):
                try:
                    handler(event)
                except Exception:
                    logger.exception("event_bus.handler_error", event_type=event.type)
