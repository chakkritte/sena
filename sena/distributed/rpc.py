"""Lightweight RPC layer for distributed agent communication."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class RPCRequest:
    """A remote procedure call request."""

    method: str
    params: dict[str, Any]
    request_id: str
    agent_id: str | None = None


@dataclass
class RPCResponse:
    """A remote procedure call response."""

    result: Any | None = None
    error: str | None = None
    request_id: str = ""


class RPCClient:
    """HTTP-based RPC client for dispatching tasks to remote agents."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def call(self, method: str, params: dict[str, Any]) -> RPCResponse:
        import uuid

        req = RPCRequest(
            method=method,
            params=params,
            request_id=uuid.uuid4().hex[:12],
        )
        try:
            resp = await self._client.post(
                f"{self.base_url}/rpc",
                json={
                    "jsonrpc": "2.0",
                    "method": req.method,
                    "params": req.params,
                    "id": req.request_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                return RPCResponse(
                    error=data["error"].get("message", "Unknown error"),
                    request_id=data.get("id", ""),
                )
            return RPCResponse(
                result=data.get("result"),
                request_id=data.get("id", ""),
            )
        except httpx.HTTPStatusError as e:
            return RPCResponse(
                error=f"HTTP {e.response.status_code}: {e.response.text}",
                request_id=req.request_id,
            )
        except Exception as e:
            return RPCResponse(error=str(e), request_id=req.request_id)

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            resp = await self._client.get(f"{self.base_url}/health")
            return resp.status_code == 200
        except Exception:
            return False


class RPCServer:
    """Async RPC server for handling remote agent requests.

    Uses a simple register/handler pattern. Can be integrated with
    any ASGI-compatible server (uvicorn, hypercorn, etc.).
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Any] = {}

    def register(self, method: str, handler: Any) -> None:
        self._handlers[method] = handler

    async def handle(self, body: dict[str, Any]) -> dict[str, Any]:
        method = body.get("method")
        params = body.get("params", {})
        req_id = body.get("id", "")

        if method not in self._handlers:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": req_id,
            }

        handler = self._handlers[method]
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**params)
            else:
                result = handler(**params)
            return {"jsonrpc": "2.0", "result": result, "id": req_id}
        except Exception as e:
            logger.exception("rpc.handler_error", method=method)
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": req_id,
            }
