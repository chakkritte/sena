"""MCP (Model Context Protocol) client integration.

Exposes external MCP servers as Sena tools.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from sena.core.base import BaseTool
from sena.core.models import ToolDefinition, ToolResult

logger = structlog.get_logger()


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
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            from mcp.client.sse import sse_client
        except ImportError as e:
            raise RuntimeError("MCP support requires 'mcp' package. Run: uv add mcp") from e

        try:
            if self.transport == "stdio":
                params = StdioServerParameters(
                    command=self.command or "npx",
                    args=self.args,
                    env=None,
                )
                self._transport_ctx = stdio_client(params)
            elif self.transport == "sse":
                self._transport_ctx = sse_client(self.url or "http://localhost:3000/sse")
            else:
                raise ValueError(f"Unknown transport: {self.transport}")

            read, write = await self._transport_ctx.__aenter__()
            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            await self._session.initialize()
        except Exception:
            await self.disconnect()
            raise

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
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None
        
        if hasattr(self, "_transport_ctx"):
            try:
                await self._transport_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            delattr(self, "_transport_ctx")


async def register_mcp_tools(registry: ToolRegistry, config: SenaConfig) -> list[MCPClient]:
    """Discover and register MCP tools based on configuration.
    
    Returns:
        list[MCPClient]: The list of connected clients (to be closed later).
    """
    clients: list[MCPClient] = []
    
    # 1. Register tools from config.mcp_servers
    for name, server_config in config.mcp_servers.items():
        try:
            client = MCPClient(
                transport=server_config.get("transport", "stdio"),
                command=server_config.get("command"),
                args=server_config.get("args"),
                url=server_config.get("url"),
            )
            await client.connect()
            tools = await client.list_tools()
            for t in tools:
                registry.register(MCPTool(client, t.name, t.description, t.parameters))
            clients.append(client)
            logger.info("mcp.registered", server=name, tools=len(tools))
        except Exception as e:
            logger.error("mcp.failed", server=name, error=str(e))

    # 2. Automatically support chakkritte/ollama-web-tools-mcp if Ollama is set
    # and not already configured.
    if config.default_provider == "ollama" and "ollama-web-tools" not in config.mcp_servers:
        try:
            # This is a Python project. We use 'uv run' to run it directly from GitHub.
            client = MCPClient(
                transport="stdio",
                command="uv",
                args=[
                    "run",
                    "--with", "git+https://github.com/chakkritte/ollama-web-tools-mcp.git",
                    "python", "-m", "ollama_web_tools_mcp"
                ],
            )
            await client.connect()
            tools = await client.list_tools()
            for t in tools:
                registry.register(MCPTool(client, t.name, t.description, t.parameters))
            clients.append(client)
            logger.info("mcp.auto_registered", server="ollama-web-tools")
        except Exception as e:
            # Log as warning if auto-registration fails
            logger.warning("mcp.auto_failed", server="ollama-web-tools", error=str(e))

    return clients


from sena.config.settings import SenaConfig
from sena.tools.base import ToolRegistry
