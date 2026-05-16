"""Plugin base class and registry for dynamic tool/provider/agent discovery."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable
from typing import Any

import structlog

from sena.core.base import BaseTool

logger = structlog.get_logger()


class SenaPlugin:
    """Base class for Sena plugins.

    Plugins are discovered via Python entry points under the group
    ``sena.plugins``. Each entry point should return a plugin instance
    that implements the hooks below.
    """

    name: str = ""
    version: str = "0.1.0"

    def activate(self) -> None:
        """Called when the plugin is loaded."""

    def deactivate(self) -> None:
        """Called when the plugin is unloaded."""

    def register_tools(self) -> list[BaseTool]:
        """Return tools to register in the global tool registry."""
        return []

    def register_providers(self) -> dict[str, type[Any]]:
        """Return provider classes to register in the provider registry."""
        return {}

    def register_commands(self) -> dict[str, Callable[..., Any]]:
        """Return CLI command functions to attach to the Typer app."""
        return {}

    def register_hooks(self) -> dict[str, Callable[..., Any]]:
        """Return event hooks for the event bus."""
        return {}


class PluginRegistry:
    """Dynamic plugin discovery and lifecycle management."""

    def __init__(self) -> None:
        self._plugins: dict[str, SenaPlugin] = {}
        self._tools: list[BaseTool] = []
        self._providers: dict[str, type[Any]] = {}
        self._commands: dict[str, Callable[..., Any]] = {}
        self._hooks: dict[str, Callable[..., Any]] = {}

    def discover(self) -> None:
        """Discover plugins via ``sena.plugins`` entry points."""
        eps: Any
        try:
            # Type ignore because entry_points returns EntryPoints in 3.10+,
            # but is treated as a dict-like or SelectableGroups in different mypy/python versions.
            eps = importlib.metadata.entry_points(group="sena.plugins")
        except (AttributeError, TypeError):
            # Fallback for older metadata API
            all_eps = importlib.metadata.entry_points()
            if hasattr(all_eps, "select"):
                eps = all_eps.select(group="sena.plugins")
            else:
                eps = getattr(all_eps, "get", lambda k, default: [])("sena.plugins", [])

        for ep in eps:
            try:
                factory = ep.load()
                plugin = factory() if callable(factory) else factory
                if isinstance(plugin, SenaPlugin):
                    self.load(plugin)
                    logger.info("plugin.loaded", name=plugin.name, entry_point=ep.name)
                else:
                    logger.warning(
                        "plugin.invalid_type",
                        entry_point=ep.name,
                        type=type(plugin).__name__,
                    )
            except Exception:
                logger.exception("plugin.load_failed", entry_point=ep.name)

    def load(self, plugin: SenaPlugin) -> None:
        """Activate a plugin and register its contributions."""
        if plugin.name in self._plugins:
            logger.warning("plugin.already_loaded", name=plugin.name)
            return

        plugin.activate()
        self._plugins[plugin.name] = plugin

        for tool in plugin.register_tools():
            self._tools.append(tool)

        self._providers.update(plugin.register_providers())
        self._commands.update(plugin.register_commands())
        self._hooks.update(plugin.register_hooks())

    def unload(self, name: str) -> None:
        """Deactivate a plugin by name."""
        plugin = self._plugins.pop(name, None)
        if plugin:
            plugin.deactivate()

    def tools(self) -> list[BaseTool]:
        return list(self._tools)

    def providers(self) -> dict[str, type[Any]]:
        return dict(self._providers)

    def commands(self) -> dict[str, Callable[..., Any]]:
        return dict(self._commands)

    def hooks(self) -> dict[str, Callable[..., Any]]:
        return dict(self._hooks)

    def list_plugins(self) -> list[str]:
        return list(self._plugins.keys())
