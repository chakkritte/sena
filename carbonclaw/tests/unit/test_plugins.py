"""Unit tests for the custom plugin ecosystem."""

from __future__ import annotations

import unittest.mock
import pytest

from carbonclaw.plugins.base import CarbonClawPlugin, PluginRegistry
from carbonclaw.core.base import BaseTool, BaseProvider
from carbonclaw.core.models import ToolResult
from carbonclaw.tools.base import ToolRegistry
from carbonclaw.providers.registry import ProviderRegistry
from carbonclaw.core.events import EventBus, Event


class MockTool(BaseTool):
    name = "plugin_test_tool"
    description = "A test tool provided by a plugin"
    
    async def execute(self, arguments: dict) -> ToolResult:
        return ToolResult(tool_call_id="", name=self.name, content="plugin-success")


class MockProvider(BaseProvider):
    async def complete(self, request):
        return None
    async def stream(self, request):
        return None
    async def list_models(self):
        return ["plugin-model"]


class MyTestPlugin(CarbonClawPlugin):
    name = "my-test-plugin"
    version = "1.0.0"

    def __init__(self):
        self.activated = False
        self.deactivated = False

    def activate(self) -> None:
        self.activated = True

    def deactivate(self) -> None:
        self.deactivated = True

    def register_tools(self) -> list[BaseTool]:
        return [MockTool()]

    def register_providers(self) -> dict[str, type[BaseProvider]]:
        return {"plugin-provider": MockProvider}

    def register_commands(self) -> dict[str, callable]:
        def plugin_cmd():
            return "cmd-result"
        return {"plugin-command": plugin_cmd}

    def register_hooks(self) -> dict[str, callable]:
        def plugin_hook(event):
            event.payload["hook_run"] = True
        return {"test_event": plugin_hook}


def test_plugin_lifecycle_and_registries() -> None:
    # 1. Test direct loading and unloading
    registry = PluginRegistry()
    plugin = MyTestPlugin()
    
    registry.load(plugin)
    assert plugin.activated is True
    assert "my-test-plugin" in registry.list_plugins()
    assert len(registry.tools()) == 1
    assert "plugin-provider" in registry.providers()
    assert "plugin-command" in registry.commands()
    assert "test_event" in registry.hooks()

    registry.unload("my-test-plugin")
    assert plugin.deactivated is True
    assert "my-test-plugin" not in registry.list_plugins()


def test_tool_registry_discovers_plugins() -> None:
    # Mock PluginRegistry.tools to return our mock tool
    tool = MockTool()
    with unittest.mock.patch("carbonclaw.plugins.base.PluginRegistry.tools", return_value=[tool]):
        registry = ToolRegistry(discover_plugins=True)
        assert registry.get("plugin_test_tool") is not None


@pytest.mark.asyncio
async def test_event_bus_discovers_plugins() -> None:
    hook_called = False
    def mock_hook(event):
        nonlocal hook_called
        hook_called = True

    with unittest.mock.patch("carbonclaw.plugins.base.PluginRegistry.hooks", return_value={"test_event": mock_hook}):
        bus = EventBus(discover_plugins=True)
        event = Event(type="test_event", payload={})
        bus._dispatch_sync(event)
        assert hook_called is True
