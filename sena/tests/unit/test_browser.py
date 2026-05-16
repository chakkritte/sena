"""Unit tests for the BrowserTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sena.tools.browser import BrowserTool


@pytest.mark.asyncio
async def test_browser_goto() -> None:
    """BrowserTool should navigate to a URL."""
    with patch("sena.tools.browser.async_playwright") as mock_pw:
        mock_instance = MagicMock()
        mock_pw.return_value.start = AsyncMock(return_value=mock_instance)
        mock_instance.stop = AsyncMock()
        
        mock_browser = AsyncMock()
        mock_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        tool = BrowserTool()
        result = await tool.execute({"action": "goto", "url": "https://example.com"})

        assert not result.is_error
        assert "Successfully navigated" in result.content
        mock_page.goto.assert_called_once()
        await tool.close()


@pytest.mark.asyncio
async def test_browser_click() -> None:
    """BrowserTool should click an element."""
    with patch("sena.tools.browser.async_playwright") as mock_pw:
        mock_instance = MagicMock()
        mock_pw.return_value.start = AsyncMock(return_value=mock_instance)
        mock_instance.stop = AsyncMock()
        
        mock_browser = AsyncMock()
        mock_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        tool = BrowserTool()
        result = await tool.execute({"action": "click", "selector": "#btn"})

        assert not result.is_error
        assert "Clicked element: #btn" in result.content
        mock_page.click.assert_called_once()
        await tool.close()


@pytest.mark.asyncio
async def test_browser_html() -> None:
    """BrowserTool should extract HTML and text."""
    with patch("sena.tools.browser.async_playwright") as mock_pw:
        mock_instance = MagicMock()
        mock_pw.return_value.start = AsyncMock(return_value=mock_instance)
        mock_instance.stop = AsyncMock()
        
        mock_browser = AsyncMock()
        mock_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_page.content = AsyncMock(return_value="<html><body>Hello</body></html>")
        mock_page.evaluate = AsyncMock(return_value="Hello")

        tool = BrowserTool()
        result = await tool.execute({"action": "html"})

        assert not result.is_error
        assert "Hello" in result.content
        assert "<html>" in result.content
        await tool.close()


@pytest.mark.asyncio
async def test_browser_error_handling() -> None:
    """BrowserTool should catch and return errors."""
    with patch("sena.tools.browser.async_playwright") as mock_pw:
        mock_instance = MagicMock()
        mock_pw.return_value.start = AsyncMock(return_value=mock_instance)
        mock_instance.stop = AsyncMock()
        
        mock_browser = AsyncMock()
        mock_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_page.goto.side_effect = Exception("Connection failed")

        tool = BrowserTool()
        result = await tool.execute({"action": "goto", "url": "https://fail.com"})

        assert result.is_error
        assert "Browser error: Connection failed" in result.content
        await tool.close()
