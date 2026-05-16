"""FastAPI web dashboard for Sena."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog

logger = structlog.get_logger()

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles

    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

from sena.agents.supervisor import SupervisorAgent
from sena.config.settings import SenaConfig
from sena.core.models import Message
from sena.distributed.queue import Task, TaskQueue

if not _FASTAPI_AVAILABLE:
    raise ImportError(
        "FastAPI is not installed. Install with: uv add fastapi uvicorn"
    )


HTML_DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <title>Sena Dashboard</title>
    <meta charset="utf-8">
    <style>
        body { font-family: system-ui, sans-serif; max-width: 960px; margin: 0 auto; padding: 2rem; }
        h1 { color: #2563eb; }
        .card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
        .log { background: #f3f4f6; padding: 0.5rem; border-radius: 4px; font-family: monospace; white-space: pre-wrap; }
        input, button { padding: 0.5rem; font-size: 1rem; }
        #stream { height: 400px; overflow-y: auto; background: #111827; color: #e5e7eb; padding: 1rem; border-radius: 8px; }
        .msg-user { color: #60a5fa; }
        .msg-assistant { color: #34d399; }
        .msg-tool { color: #fbbf24; }
    </style>
</head>
<body>
    <h1>Sena Dashboard</h1>
    <div class="card">
        <h2>Chat</h2>
        <div id="stream"></div>
        <form id="chat-form" style="margin-top:1rem;">
            <input id="prompt" type="text" placeholder="Enter a task..." style="width:70%;">
            <button type="submit">Send</button>
        </form>
    </div>
    <div class="card">
        <h2>Status</h2>
        <div id="status" class="log">Idle</div>
    </div>
    <script>
        const stream = document.getElementById('stream');
        const form = document.getElementById('chat-form');
        const prompt = document.getElementById('prompt');
        const status = document.getElementById('status');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = prompt.value.trim();
            if (!text) return;
            prompt.value = '';
            stream.innerHTML += '<div class="msg-user">[you] ' + escapeHtml(text) + '</div>';
            stream.scrollTop = stream.scrollHeight;

            const source = new EventSource('/chat/stream?prompt=' + encodeURIComponent(text));
            source.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'text') {
                    stream.innerHTML += escapeHtml(data.content);
                } else if (data.type === 'tool') {
                    stream.innerHTML += '<div class="msg-tool">[' + escapeHtml(data.name) + '] ' + escapeHtml(data.content.substring(0,200)) + '</div>';
                } else if (data.type === 'done') {
                    stream.innerHTML += '<div style="color:#9ca3af;">--- done ---</div>';
                    source.close();
                }
                stream.scrollTop = stream.scrollHeight;
            };
            source.onerror = () => {
                source.close();
                status.textContent = 'Connection closed';
            };
        });

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
"""


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    config = SenaConfig()
    queue = TaskQueue()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> "AsyncIterator[None]":
        logger.info("web.starting")
        yield
        logger.info("web.shutting_down")

    app = FastAPI(title="Sena", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        return HTML_DASHBOARD

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/chat/stream")
    async def chat_stream(request: Request, prompt: str) -> StreamingResponse:
        """SSE endpoint for streaming chat with the supervisor agent."""
        async def event_generator() -> AsyncIterator[str]:
            try:
                supervisor = await SupervisorAgent.create_default(config.default_provider)
                async for text in supervisor.stream_delegate("coding", prompt):
                    yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                logger.exception("web.stream_error")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @app.post("/tasks")
    async def submit_task(payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a task to the queue."""
        task = Task(
            agent_type=payload.get("agent", "coding"),
            payload=payload,
            priority=payload.get("priority", 0),
        )
        await queue.submit(task)
        return {"id": task.id, "status": task.status}

    @app.get("/tasks/{task_id}")
    async def get_task(task_id: str) -> dict[str, Any] | None:
        t = await queue.get(task_id)
        if t is None:
            return None
        return {
            "id": t.id,
            "status": t.status,
            "result": t.result,
            "error": t.error,
            "created_at": t.created_at,
        }

    @app.get("/tasks")
    async def list_tasks() -> list[dict[str, Any]]:
        return [
            {"id": t.id, "status": t.status, "created_at": t.created_at}
            for t in await queue.pending()
        ] + [
            {"id": t.id, "status": t.status, "created_at": t.created_at}
            for t in await queue.active()
        ]

    return app


async def serve(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run the web server."""
    import uvicorn

    app = create_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
