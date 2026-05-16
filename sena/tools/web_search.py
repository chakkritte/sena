"""Web search tool using DuckDuckGo."""

from __future__ import annotations

import re
from typing import Any

import httpx

from sena.core.base import BaseTool
from sena.core.models import ToolResult


class WebSearchTool(BaseTool):
    """Search the web via DuckDuckGo and return structured results."""

    name = "web_search"
    description = (
        "Search the web for a query and return top results with title, URL, and snippet. "
        "Uses DuckDuckGo HTML API (no API key required)."
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
        """Fetch HTML from DuckDuckGo and parse results."""
        url = "https://html.duckduckgo.com/html/"
        params = {"q": query}
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            html = resp.text

        results: list[dict[str, str]] = []
        # Parse DuckDuckGo HTML result blocks
        result_blocks = re.findall(
            r'<div class="result__body">(.*?</div>\s*</div>)',
            html,
            re.DOTALL,
        )

        for block in result_blocks[:max_results]:
            title_match = re.search(
                r'<a[^>]*class="result__a"[^>]*>(.*?)</a>', block, re.DOTALL
            )
            url_match = re.search(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"', block
            )
            snippet_match = re.search(
                r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )

            title = self._strip_tags(title_match.group(1)) if title_match else "No title"
            result_url = (
                "https://duckduckgo.com" + url_match.group(1)
                if url_match and url_match.group(1).startswith("/")
                else (url_match.group(1) if url_match else "")
            )
            snippet = (
                self._strip_tags(snippet_match.group(1)) if snippet_match else ""
            )

            if result_url:
                results.append({"title": title, "url": result_url, "snippet": snippet})

        return results

    @staticmethod
    def _strip_tags(text: str) -> str:
        """Remove HTML tags and decode entities."""
        clean = re.sub(r"<[^>]+>", "", text)
        clean = clean.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        clean = clean.replace("&quot;", '"').replace("&#39;", "'")
        return " ".join(clean.split())
