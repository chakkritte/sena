"""MCP (Model Context Protocol) client integration.

Exposes external MCP servers as Sena tools.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sena.core.base import BaseTool
from sena.core.models import ToolDefinition, ToolResult


class MCPTool(BaseTool):
    """Wrap an MCP tool as a Sena BaseTool.

    Usage::

        client = MCPClient("stdio", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
        await client.connect()
        tools = await client.list_tools()
        for t in tools:
            registry.register(MCPTool(client, t.name, t.description, t.input_schema))
    """

    def __init__(
        self,
        client: Any,
        name: str,
        description: str,
        input_schema: dict[str, Any],
    ) -> None:
        self._client = client
        self.name = name
        self.description = description
        self.input_schema = input_schema

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            result = await self._client.call_tool(self.name, arguments)
            content = "\n".join(
                item.text for item in result.content if hasattr(item, "text")
            )
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=content or "(empty result)",
                is_error=result.isError if hasattr(result, "isError") else False,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"MCP tool error: {e}",
                is_error=True,
            )


class MCPClient:
    """Lightweight MCP client for stdio and SSE transports.

    Requires ``mcp`` package (``pip install mcp``).
    """

    def __init__(
        self,
        transport: str,
        command: str | None = None,
        args: list[str] | None = None,
        url: str | None = None,
    ) -> None:
        """Configure the client.

        Args:
            transport: ``stdio`` or ``sse``.
            command: Executable for stdio transport.
            args: Arguments for stdio transport.
            url: Endpoint URL for SSE transport.
        """
        self.transport = transport
        self.command = command
        self.args = args or []
        self.url = url
        self._session: Any = None
        self._tools: list[ToolDefinition] = []

    async def connect(self) -> None:
        """Establish the MCP session."""
        try:
            from mcp import ClientSession, StdioServerParameters  # type: ignore
            from mcp.client.stdio import stdio_client  # type: ignore
            from mcp.client.sse import sse_client  # type: ignore
        except ImportError as e:
            raise RuntimeError("MCP support requires 'mcp' package. Run: uv add mcp") from e

        if self.transport == "stdio":
            params = StdioServerParameters(
                command=self.command or "npx",
                args=self.args,
                env=None,
            )
            transport_cm = stdio_client(params)
        elif self.transport == "sse":
            transport_cm = sse_client(self.url or "http://localhost:3000/sse")
        else:
            raise ValueError(f"Unknown transport: {self.transport}")

        self._transport = transport_cm
        read, write = await self._transport.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()

    async def list_tools(self) -> list[ToolDefinition]:
        """Discover tools exposed by the MCP server."""
        if self._session is None:
            raise RuntimeError("MCP session not connected. Call connect() first.")

        result = await self._session.list_tools()
        tools: list[ToolDefinition] = []
        for tool in result.tools:
            tools.append(
                ToolDefinition(
                    name=tool.name,
                    description=tool.description or "",
                    parameters=tool.inputSchema,
                )
            )
        self._tools = tools
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Invoke an MCP tool by name."""
        if self._session is None:
            raise RuntimeError("MCP session not connected. Call connect() first.")
        return await self._session.call_tool(name, arguments=arguments)

    async def disconnect(self) -> None:
        """Close the MCP session."""
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if hasattr(self, "_transport"):
            await self._transport.__aexit__(None, None, None)
