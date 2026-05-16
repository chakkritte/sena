"""Playwright-based browser automation tool."""

from __future__ import annotations

import asyncio
import base64
from typing import Any, Literal

import structlog
from playwright.async_api import async_playwright  # type: ignore

from sena.core.base import BaseTool
from sena.core.models import ToolResult

logger = structlog.get_logger()


class BrowserTool(BaseTool):
    """Automate web interactions using a headless browser."""

    name = "browser"
    requires_approval = True
    description = (
        "Interact with web pages using a headless browser. "
        "Supports navigation, clicking, typing, and scraping. "
        "Use this for web research, UI testing, or extracting data from complex sites."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["goto", "click", "fill", "evaluate", "html", "screenshot"],
                "description": "The browser action to perform.",
            },
            "url": {"type": "string", "description": "URL to navigate to (for 'goto')."},
            "selector": {
                "type": "string",
                "description": "CSS selector for the target element (for 'click' or 'fill').",
            },
            "value": {
                "type": "string",
                "description": "Value to type into the element (for 'fill').",
            },
            "script": {
                "type": "string",
                "description": "JavaScript code to execute (for 'evaluate').",
            },
            "path": {
                "type": "string",
                "description": "File path to save the screenshot (for 'screenshot').",
            },
            "timeout": {
                "type": "integer",
                "description": "Action timeout in milliseconds.",
                "default": 30000,
            },
        },
        "required": ["action"],
    }

    def __init__(self) -> None:
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None
        self._page: Any | None = None
        self._lock = asyncio.Lock()

    async def _ensure_page(self) -> Any:
        """Initialize playwright and open a page if not already active."""
        async with self._lock:
            if self._page is not None:
                return self._page

            if self._playwright is None:
                self._playwright = await async_playwright().start()

            if self._browser is None:
                self._browser = await self._playwright.chromium.launch(headless=True)

            if self._context is None:
                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Sena/0.1.1 (+https://github.com/your-org/sena)",
                )

            self._page = await self._context.new_page()
            return self._page

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        action = arguments.get("action")
        timeout = arguments.get("timeout", 30000)

        try:
            page = await self._ensure_page()
            logger.info("browser.action", action=action, url=arguments.get("url"))

            if action == "goto":
                url = arguments.get("url")
                if not url:
                    return ToolResult(
                        tool_call_id="",
                        name=self.name,
                        content="URL is required for 'goto' action.",
                        is_error=True,
                    )
                await page.goto(url, timeout=timeout, wait_until="networkidle")
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=f"Successfully navigated to {url}",
                )

            elif action == "click":
                selector = arguments.get("selector")
                if not selector:
                    return ToolResult(
                        tool_call_id="",
                        name=self.name,
                        content="Selector is required for 'click' action.",
                        is_error=True,
                    )
                await page.click(selector, timeout=timeout)
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=f"Clicked element: {selector}",
                )

            elif action == "fill":
                selector = arguments.get("selector")
                value = arguments.get("value", "")
                if not selector:
                    return ToolResult(
                        tool_call_id="",
                        name=self.name,
                        content="Selector is required for 'fill' action.",
                        is_error=True,
                    )
                await page.fill(selector, value, timeout=timeout)
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=f"Filled '{value}' into {selector}",
                )

            elif action == "evaluate":
                script = arguments.get("script")
                if not script:
                    return ToolResult(
                        tool_call_id="",
                        name=self.name,
                        content="Script is required for 'evaluate' action.",
                        is_error=True,
                    )
                result = await page.evaluate(script)
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=f"Script result: {result}",
                )

            elif action == "html":
                content = await page.content()
                # Also include text for easier agent consumption
                text = await page.evaluate("() => document.body.innerText")
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=f"HTML Content:\n{content[:1000]}...\n\nText Content:\n{text[:5000]}",
                )

            elif action == "screenshot":
                path = arguments.get("path")
                if path:
                    await page.screenshot(path=path)
                    return ToolResult(
                        tool_call_id="",
                        name=self.name,
                        content=f"Screenshot saved to {path}",
                    )
                else:
                    screenshot_bytes = await page.screenshot()
                    b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                    return ToolResult(
                        tool_call_id="",
                        name=self.name,
                        content=f"Screenshot (base64): {b64[:100]}...",
                    )

            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Unknown browser action: {action}",
                is_error=True,
            )

        except Exception as e:
            logger.exception("browser.error", action=action)
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Browser error: {e}",
                is_error=True,
            )

    async def close(self) -> None:
        """Clean up browser resources."""
        async with self._lock:
            if self._page:
                await self._page.close()
                self._page = None
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
