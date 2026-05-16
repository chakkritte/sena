"""Remote agent worker pool."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import AsyncIterator
from typing import Any

import structlog

from sena.agents.supervisor import SupervisorAgent
from sena.config.settings import SenaConfig
from sena.distributed.queue import Task, TaskQueue, TaskStatus
from sena.distributed.rpc import RPCClient

logger = structlog.get_logger()


class Worker:
    """A single worker that consumes tasks from a queue and executes them."""

    def __init__(
        self,
        queue: TaskQueue,
        provider_name: str | None = None,
        model: str | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        self.queue = queue
        self.config = SenaConfig()
        self.provider_name = provider_name or self.config.default_provider
        self.model = model or self.config.default_model or "llama3.2"
        self.poll_interval = poll_interval
        self._running = False
        self._supervisor: SupervisorAgent | None = None
        self._task: asyncio.Task[Any] | None = None

    async def _ensure_supervisor(self) -> SupervisorAgent:
        if self._supervisor is None:
            self._supervisor = await SupervisorAgent.create_default(self.provider_name)
        return self._supervisor

    async def start(self) -> None:
        """Start consuming tasks from the queue."""
        self._running = True
        logger.info("worker.starting", provider=self.provider_name)
        while self._running:
            task = await self.queue.next_task(timeout=self.poll_interval)
            if task is None:
                continue
            await self._process_task(task)

    async def _process_task(self, task: Task) -> None:
        """Execute a single task."""
        logger.info("worker.processing", task_id=task.id, agent=task.agent_type)
        try:
            supervisor = await self._ensure_supervisor()
            if task.agent_type == "supervisor":
                result = await supervisor.run_workflow(
                    task.payload.get("task", ""),
                    auto_plan=task.payload.get("auto_plan", True),
                    auto_review=task.payload.get("auto_review", True),
                )
            else:
                result = await supervisor.delegate(
                    task.agent_type,
                    task.payload.get("task", ""),
                )
            await self.queue.complete(task.id, result)
            logger.info("worker.completed", task_id=task.id)
        except Exception as e:
            logger.exception("worker.failed", task_id=task.id)
            await self.queue.fail(task.id, str(e))

    async def stop(self) -> None:
        """Gracefully stop the worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("worker.stopped")


class WorkerPool:
    """Manage a pool of worker processes/tasks."""

    def __init__(
        self,
        num_workers: int = 2,
        queue: TaskQueue | None = None,
        provider_name: str | None = None,
    ) -> None:
        self.num_workers = num_workers
        self.queue = queue or TaskQueue()
        self.provider_name = provider_name
        self._workers: list[Worker] = []
        self._tasks: list[asyncio.Task[Any]] = []

    async def start(self) -> None:
        """Start all workers in the pool."""
        logger.info("pool.starting", num_workers=self.num_workers)
        for i in range(self.num_workers):
            worker = Worker(self.queue, provider_name=self.provider_name)
            self._workers.append(worker)
            task = asyncio.create_task(worker.start(), name=f"worker-{i}")
            self._tasks.append(task)

    async def stop(self) -> None:
        """Stop all workers."""
        logger.info("pool.stopping")
        for worker in self._workers:
            await worker.stop()
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("pool.stopped")

    async def submit(self, task: Task) -> None:
        """Submit a task to the shared queue."""
        await self.queue.submit(task)

    async def status(self) -> dict[str, Any]:
        """Return pool status."""
        return {
            "num_workers": self.num_workers,
            "running": len(self._workers),
            "pending": len(await self.queue.pending()),
            "active": len(await self.queue.active()),
        }


class RemoteWorkerClient:
    """Client for submitting tasks to a remote worker pool via RPC."""

    def __init__(self, base_url: str) -> None:
        self.rpc = RPCClient(base_url)

    async def submit(self, agent_type: str, task: str, priority: int = 0) -> str:
        resp = await self.rpc.call(
            "submit_task",
            {"agent": agent_type, "task": task, "priority": priority},
        )
        if resp.error:
            raise RuntimeError(resp.error)
        res = resp.result or {}
        return str(res["id"])

    async def get_status(self, task_id: str) -> dict[str, Any]:
        resp = await self.rpc.call("get_task", {"task_id": task_id})
        if resp.error:
            raise RuntimeError(resp.error)
        return resp.result or {}

    async def health(self) -> bool:
        return await self.rpc.health()

    async def close(self) -> None:
        await self.rpc.close()


async def run_worker(
    provider: str | None = None,
    num_workers: int = 1,
) -> None:
    """Run a standalone worker process."""
    pool = WorkerPool(num_workers=num_workers, provider_name=provider)

    def _signal_handler(sig: int) -> None:
        asyncio.create_task(pool.stop())

    for s in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(s, _signal_handler, s)

    await pool.start()
    # Keep running until stopped
    while any(not t.done() for t in pool._tasks):
        await asyncio.sleep(1)
