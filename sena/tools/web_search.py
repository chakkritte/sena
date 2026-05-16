"""Web search tool using DuckDuckGo."""

from __future__ import annotations

from typing import Any

import structlog
from ddgs import DDGS  # type: ignore

from sena.core.base import BaseTool
from sena.core.models import ToolResult

logger = structlog.get_logger()


class WebSearchTool(BaseTool):
    """Search the web via DuckDuckGo and return structured results."""

    name = "web_search"
    description = (
        "Search the web for a query and return top results with title, URL, and snippet. "
        "Uses DuckDuckGo API (no API key required)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (1-10).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        query = arguments.get("query", "")
        max_results = min(10, max(1, arguments.get("max_results", 5)))

        if not query:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content="No query provided.",
                is_error=True,
            )

        try:
            results = await self._search(query, max_results)
        except Exception as e:
            logger.exception("web_search.error", query=query)
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Search failed: {e}",
                is_error=True,
            )

        if not results:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content="No results found.",
                is_error=False,
            )

        lines = [f"Web search results for '{query}':"]
        for i, r in enumerate(results, 1):
            lines.append(f"\n{i}. {r['title']}\n   URL: {r['url']}\n   {r['snippet']}")

        return ToolResult(
            tool_call_id="",
            name=self.name,
            content="\n".join(lines),
            is_error=False,
        )

    async def _search(self, query: str, max_results: int) -> list[dict[str, str]]:
        """Fetch results using ddgs library."""
        results: list[dict[str, str]] = []
        
        # DDGS is synchronous, but we can run it in a thread pool to avoid blocking
        import asyncio
        from functools import partial

        def _fetch() -> list[dict[str, str]]:
            with DDGS() as ddgs:
                # Use list comprehension to consume the generator
                return [r for r in ddgs.text(query, max_results=max_results)]

        loop = asyncio.get_event_loop()
        ddg_results = await loop.run_in_executor(None, _fetch)

        for r in ddg_results:
            results.append({
                "title": r.get("title", "No title"),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })

        return results
