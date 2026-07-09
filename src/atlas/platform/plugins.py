from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from atlas.exceptions import AtlasPluginError


@dataclass(frozen=True)
class PluginManifest:
    """Declarative identity for an Atlas plugin."""

    name: str
    version: str
    description: str = ""

    def validate(self) -> None:
        if not self.name.strip():
            raise AtlasPluginError("plugin name must not be blank")
        if not self.version.strip():
            raise AtlasPluginError(f"plugin {self.name!r} must declare a version")


class AtlasPlugin(Protocol):
    """Protocol every Atlas plugin must implement."""

    manifest: PluginManifest

    def initialize(self) -> None:
        """Initialize plugin resources."""

    def shutdown(self) -> None:
        """Release plugin resources."""


@dataclass
class PluginHost:
    """Kernel-owned plugin lifecycle coordinator."""

    plugins: list[AtlasPlugin] = field(default_factory=list)
    initialized: bool = False

    def register(self, plugin: AtlasPlugin) -> None:
        plugin.manifest.validate()
        if any(existing.manifest.name == plugin.manifest.name for existing in self.plugins):
            raise AtlasPluginError(f"duplicate plugin name: {plugin.manifest.name}")
        self.plugins.append(plugin)

    def initialize(self) -> None:
        for plugin in self.plugins:
            plugin.initialize()
        self.initialized = True

    def shutdown(self) -> None:
        for plugin in reversed(self.plugins):
            plugin.shutdown()
        self.initialized = False

    def manifests(self) -> list[PluginManifest]:
        return [plugin.manifest for plugin in self.plugins]
